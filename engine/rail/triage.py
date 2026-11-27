"""The triage step: a closed question the engine raises from a fact it produced, answered by a fresh run that did
not write the change (rail docs triage).

`QUESTIONS` is the one table of question types. A type says what raises it, what the run is shown, the two to four
answers allowed with what each means and what the engine then does, and, for an answer that lets the change
through, the evidence it must name and how the engine checks it. A new question is an entry here and its test.

In the journal a `question` event holds the type, the patch and the fact; an `answered` event holds the answer, its
evidence and whether the evidence passed its check. Every run is a `step` event named `triage`, with its cost.
"""

import json
import os
import tempfile

from . import gitx, schema
from .project import event
from .util import could_not_run, run_shell, tail

GO, STOP = "go", "stop"   # what the engine does on an answer: the ticket goes on, or the step `triage` fails

QUESTIONS = {}


def question(id, raised, ask, answers, find, show):
    """Add a type to the table.

    `raised`: the fact that raises it, in a sentence for the docs. `ask`: the question the run answers. `answers`:
    {name: {means, then, evidence, check, told}}: what the answer means; GO or STOP; for an answer that lets the change
    through, what its evidence must be (text for the brief) and `check(project, f, fact, evidence)`, which returns
    what is wrong with it or None; for an answer that stops, what the worker is told to do. `find(project, f, ref,
    patch_id)`: the facts that raise it for this patch at ship, each a dict of plain values with a `key`, which tells
    one fact from another, and `said`, the fact in one line. `show(project, f, fact)`: the lines of the brief that
    show the fact, and nothing else of the change."""
    assert 2 <= len(answers) <= 4, id
    for name, a in answers.items():
        assert a["then"] in (GO, STOP) and a["means"], (id, name)
        assert a["then"] == STOP or not a.get("evidence") or a.get("check"), (id, name)
    QUESTIONS[id] = {"id": id, "raised": raised, "ask": ask, "answers": answers, "find": find, "show": show}


# --- what the journal holds -------------------------------------------------------------------


def asked(events):
    """Every question of a ticket, in order: its `question` event with `at_index`, `answers` (its `answered` events,
    each with `at_index`) and `answer` (the last one whose evidence passed its check, or None while it is open)."""
    found = {}
    for i, e in enumerate(events):
        if e.get("event") == "question":
            found[e.get("id")] = dict(e, at_index=i, answers=[], answer=None)
        elif e.get("event") == "answered" and e.get("id") in found:
            q = found[e["id"]]
            q["answers"].append(dict(e, at_index=i))
            if e.get("evidence_ok") is not False:
                q["answer"] = q["answers"][-1]
    return list(found.values())


def open_questions(events, patch_id):
    """The questions about this patch that have no answer yet. A question about an earlier patch is over: the patch
    it asked about is gone, and a fact that still holds raised a new one at the ship."""
    return [q for q in asked(events) if q.get("patch_id") == patch_id and not q["answer"]]


def then(q):
    """GO or STOP for an answered question, None for an open one or a type this engine no longer has."""
    kind = QUESTIONS.get(q.get("type"))
    if not q["answer"] or not kind or q["answer"].get("answer") not in kind["answers"]:
        return None
    return kind["answers"][q["answer"]["answer"]]["then"]


def stopped(events, patch_id):
    """The questions about this patch whose answer stops the change."""
    return [q for q in asked(events) if q.get("patch_id") == patch_id and then(q) == STOP]


def stop_facts(events, qid):
    """What a worker is told about a stopping answer, as plain values: the question, the fact, the answer with what it
    means, the run's reason, and what to do. None when the journal has no such answer."""
    q = next((q for q in asked(events) if q.get("id") == qid), None)
    kind = QUESTIONS.get((q or {}).get("type"))
    if not q or not q["answer"] or not kind:
        return None
    a = kind["answers"].get(q["answer"].get("answer")) or {}
    return {key: value for key, value in {
        "question": q["id"], "type": q["type"], "ask": kind["ask"], "fact": (q.get("fact") or {}).get("said"),
        "answer": q["answer"].get("answer"), "means": a.get("means"), "reason": q["answer"].get("reason"),
        "evidence": q["answer"].get("evidence"), "told": a.get("told")}.items() if value}


def stop_said(x):
    """A stopping answer in the words a failed step shows, from stop_facts."""
    return "\n".join(line for line in [
        f"The engine asked a run that did not write this change: {x.get('ask', '')}",
        f"What raised the question: {x['fact']}" if x.get("fact") else "",
        f"Its answer: `{x.get('answer')}`, {x.get('means', '')}",
        f"Its reason: {x['reason']}" if x.get("reason") else "",
        f"What the answer names: {x['evidence']}" if x.get("evidence") else "",
        x.get("told") or ""] if line)


def count(events, rows):
    """Add one ticket's questions to the rows `rail stats` shows, {type: {questions, answers, runs, no_answer,
    cost_usd}}: each question, the answer it ended with, every run, the runs that gave no answer, and what the runs
    reported they cost."""
    def row(name):
        return rows.setdefault(name, {"questions": 0, "answers": {}, "runs": 0, "no_answer": 0, "cost_usd": 0.0})

    for q in asked(events):
        found = row(q.get("type") or "?")
        found["questions"] += 1
        if q["answer"] and q["answer"].get("answer"):
            found["answers"][q["answer"]["answer"]] = found["answers"].get(q["answer"]["answer"], 0) + 1
    for e in events:
        if e.get("event") == "step" and e.get("step") == "triage" and e.get("type") and "duration_ms" in e:
            found = row(e["type"])  # a step with no duration is an answer that stood, with no run
            found["runs"] += 1
            found["no_answer"] += e.get("counted") is False or e.get("status") == "could_not_run"
            found["cost_usd"] += e.get("cost_usd") or 0


LAST, SAME = 20, 19   # a type whose last LAST questions got one answer SAME times or more is a rule, not a question


def settled(project):
    """[(type, answer, times)] for each type whose last LAST answered questions, in every journal on the base branch,
    got the same answer SAME times or more. Such a type is a rule the engine can apply with no run."""
    from .project import parse_events
    names = gitx.out(["ls-tree", "--name-only", project.base_ref, ".rail/journal/"], project.root).splitlines()
    refs = [f"{project.base_ref}:{name}" for name in names if name.endswith("-events.jsonl")]
    held = gitx.read_blobs(refs, project.root)
    answers = {}
    for ref in refs:
        for q in asked(parse_events(held.get(ref))):
            if q["answer"] and q["answer"].get("answer"):
                answers.setdefault(q.get("type"), []).append((q["answer"].get("at") or "", q["answer"]["answer"]))
    found = []
    for name, rows in sorted(answers.items()):
        last = [answer for _, answer in sorted(rows)[-LAST:]]
        top = max(set(last), key=last.count)
        if len(last) == LAST and last.count(top) >= SAME:
            found.append((name, top, last.count(top)))
    return found


# --- raising a question at ship ---------------------------------------------------------------


def raise_at_ship(project, f, run, ref, patch_id):
    """After a ship's checks passed: one `question` event for each fact a type finds about this patch and has not
    asked about yet. Returns False when an answer that stops the change still stands for this patch: the step `triage`
    fails again with no run, because nothing the answer was about has changed. An amend of the contract after the
    answer raises the question again, since the contract is part of what was asked."""
    t = f.t
    before = asked(t.events)
    amended = max((i for i, e in enumerate(t.events) if e.get("event") == "amended"), default=-1)
    number = len(before)
    for kind in QUESTIONS.values():
        for fact in kind["find"](project, f, ref, patch_id):
            same = [q for q in before if (q.get("type"), q.get("patch_id"), q.get("key")) == (kind["id"], patch_id, fact["key"])]
            last = same[-1] if same else None
            if last and then(last) == STOP and last["answer"]["at_index"] > amended:
                x = stop_facts(t.events, last["id"])
                run.record("triage", False, patch_id, f"{last['id']} {kind['id']}: {x['answer']}", output=stop_said(x),
                           signed=f"{kind['id']}: {x['answer']}", question=last["id"], type=kind["id"])
                return False
            if last and (not last["answer"] or then(last) == GO):
                continue  # asked about this patch already: open, or let through
            number += 1
            run.events.append(event(t.id, "question", id=f"Q{number}", type=kind["id"], patch_id=patch_id,
                                    key=fact["key"], fact={k: v for k, v in fact.items() if k != "key"}))
    return True


# --- the run ----------------------------------------------------------------------------------

# Not tested with a model run: this prompt and the brief below are a first wording.
PROMPT = """\
You answer one closed question about a change you did not write. The engine raised the question from a fact it
produced itself, such as a test that fails or a line the change added. The brief shows that fact and what you need
to judge it.

- Choose one of the answers the brief lists, and no other. Each says what it means.
- You may read any file in this folder and run commands here. Nothing you change is kept, and you never push.
- Where an answer asks for evidence, give it word for word: the engine looks it up, and an answer whose evidence is
  not where you say it is counts as no answer.
- When no answer that lets the change through holds, give the answer that stops it. Stopping costs one more attempt;
  a wrong pass costs more.
- Do not review the change. Whether it is good is the reviewer's question, and the reviewer comes after you.

Reply with JSON only: `answer`, `reason` (one or two sentences on what you read or ran that decides it), and
`evidence` where the answer asks for it.
"""


def answer_schema(kind):
    """The JSON a run answers a question of this type with."""
    return {"title": "triage/v1", "type": "object", "additionalProperties": False, "required": ["answer", "reason"],
            "properties": {
                "answer": {"type": "string", "enum": list(kind["answers"]),
                           "description": "One of the answers the brief lists."},
                "reason": {"type": "string", "description": "One or two sentences: what you read or ran that decides it."},
                "evidence": {"type": "string", "description": "What the answer asks for, word for word."}}}


def brief(project, f, q):
    """What the run reads: the question, its answers, the fact, and only what the type says to show."""
    kind = QUESTIONS[q["type"]]
    answers = [f"- `{name}`: {a['means']}" + (f" Evidence: {a['evidence']}" if a.get("evidence") else "")
               for name, a in kind["answers"].items()]
    return "\n".join([
        f"# One question about ticket {f.id} ({q['id']}, {q['type']})", "",
        kind["ask"], "",
        "## The answers", *answers, "",
        "## What raised the question", (q.get("fact") or {}).get("said") or "", "",
        *kind["show"](project, f, dict(q.get("fact") or {}, key=q.get("key"))),
    ]).rstrip() + "\n"


def command(project):
    """The command and the model of a triage run: [triage]'s, and the review seat's where that is empty."""
    config = project.config
    return config["triage"]["command"] or config["review"]["command"], config["triage"]["model"] or config["review"]["model"]


def run(project, f, receipt):
    """One run for the first open question about the ticket's patch: its `answered` event and its `triage` step go
    into `receipt`. A run that timed out, could not start or answered with something invalid records the step alone,
    not counted against the author, as a review run with no verdict is."""
    from .review import _structured, model_env
    from .steps import keep_alive

    t, wt = f.t, f.t.worktree
    q = open_questions(t.events, f.patch_id)[0]
    kind = QUESTIONS.get(q["type"])
    named = {"question": q["id"], "type": q["type"]}
    if not kind:
        # A type this engine no longer has: nothing can answer it, and nothing depends on it any more.
        receipt.events.append(event(t.id, "answered", id=q["id"], type=q["type"], patch_id=f.patch_id, answer="",
                                    reason="this engine has no such question type"))
        receipt.record("triage", True, f.patch_id, f"{q['id']} {q['type']}: no such type", **named)
        return
    keep_alive(project, t)
    head = gitx.rev(t.ref, project.root)
    text = brief(project, f, q)
    line, model = command(project)
    timeout = project.config["commands"]["timeout_secs"]
    with tempfile.TemporaryDirectory(prefix="rail-triage-") as held:
        files = {"RAIL_REVIEW_PROMPT": ("triage.md", PROMPT),
                 "RAIL_REVIEW_SCHEMA": ("triage-v1.json", json.dumps(answer_schema(kind), indent=2) + "\n")}
        env = {"RAIL_TICKET": t.id, "RAIL_TRIAGE": q["type"], **model_env(model)}
        for var, (name, body) in files.items():
            env[var] = os.path.join(held, name)
            with open(env[var], "w") as fh:
                fh.write(body)
        code, output, ms = run_shell(line, wt, env, timeout, stdin=text)
    # The run may read and run, and nothing it changed is kept.
    gitx.git(["reset", "--quiet", "--hard", head], wt)
    gitx.git(["clean", "-fdq"], wt)
    if code is None:
        receipt.record("triage", False, f.patch_id, "timeout", ms, counted=False,
                       output=f"The triage run passed timeout_secs ({timeout}s).", **named)
        return
    if could_not_run(code):
        receipt.record("triage", False, f.patch_id, could_not_run(code), ms, status="could_not_run",
                       output=f"The triage command could not start, so nothing was answered. Its command:\n$ {line}\n"
                              f"{tail(output, 30)}", **named)
        return
    try:
        data, meta = _structured(output)
        errors = schema.check(data, answer_schema(kind)) if code == 0 else [f"exit {code}"]
    except ValueError:
        data, meta, errors = None, {}, ["the output is not JSON"]
    if errors:
        receipt.record("triage", False, f.patch_id, f"invalid output: {errors[0]}", ms, counted=False,
                       output="The triage run's output was invalid:\n- " + "\n- ".join(errors) + f"\n\n{tail(output, 30)}",
                       cost_usd=meta.get("cost_usd"), **named)
        return
    a = kind["answers"][data["answer"]]
    fields = {"id": q["id"], "type": q["type"], "patch_id": f.patch_id, "answer": data["answer"],
              "reason": data["reason"]}
    if data.get("evidence"):
        fields["evidence"] = data["evidence"]
    if meta.get("model"):
        fields["model"] = meta["model"]
    wrong = None
    if a["then"] == GO and a.get("check"):
        wrong = (a["check"](project, f, dict(q.get("fact") or {}, key=q.get("key")), data.get("evidence") or "")
                 if data.get("evidence") else "the answer names no evidence")
        fields["evidence_ok"] = not wrong
    receipt.events.append(event(t.id, "answered", **fields))
    detail = f"{q['id']} {q['type']}: {data['answer']}"
    if wrong:
        # An answer whose evidence is not where it says is no answer: the run is started once more, as after any
        # invalid output.
        receipt.record("triage", False, f.patch_id, f"invalid output: {wrong}", ms, counted=False,
                       output=f"The triage run answered `{data['answer']}`, and its evidence did not pass the engine's"
                              f" check: {wrong}", cost_usd=meta.get("cost_usd"), **named)
    elif a["then"] == STOP:
        x = stop_facts([*t.events, *receipt.events], q["id"])
        receipt.record("triage", False, f.patch_id, detail, ms, output=stop_said(x), cost_usd=meta.get("cost_usd"),
                       signed=f"{q['type']}: {data['answer']}", **named)
    else:
        receipt.record("triage", True, f.patch_id, detail, ms, cost_usd=meta.get("cost_usd"), **named)


# --- checks of evidence, for the types to use ---------------------------------------------------


def _plain(text):
    return " ".join(str(text).replace("`", "").split()).strip(" .-*").lower()


def quoted_in_ticket(project, f, fact, evidence):
    """The evidence is a line of the Done Contract or a sentence of ## Why, word for word but for spacing and
    backticks. Returns what is wrong, or None."""
    ticket = f.ticket
    held = _plain("\n".join([ticket.sections.get("Done Contract", ""), ticket.sections.get("Why", "")]))
    quoted = _plain(evidence)
    if len(quoted) < 8:
        return "the quoted line is too short to be looked up"
    return None if quoted in held else "the quoted line is in neither the Done Contract nor ## Why of the ticket"
