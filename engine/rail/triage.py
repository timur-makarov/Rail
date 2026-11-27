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

# What the engine does on an answer: the ticket goes on, the step `triage` fails and the worker mends the change,
# the ticket waits for a person, or the engine does what the answer's own `does` names (a row of the table reads it).
GO, STOP, WAIT, ACT = "go", "stop", "wait", "act"

QUESTIONS = {}


def question(id, raised, ask, answers, find, show, once=False, at="ship", model=None):
    """Add a type to the table.

    `raised`: the fact that raises it, in a sentence for the docs. `ask`: the question the run answers. `answers`:
    {name: {means, then, evidence, check, optional, told, wait}}: what the answer means; GO, STOP or WAIT; for an
    answer that lets the change through, what its evidence must be (text for the brief) and `check(project, f, fact,
    evidence)`, which returns what is wrong with it or None (`optional`: the answer may come with no evidence, and
    what it gives is still checked); for an answer that stops, what the worker is told to do, where `{nn}` stands for
    the ticket; for an answer that waits, `wait`, the reason code of the wait for a person. `find(project, f, ref,
    patch_id, run)`: the facts that raise it for this patch at ship, each a dict of plain values with a `key`, which
    tells one fact from another, and `said`, the fact in one line; `run` is the ship's receipt, whose events are not
    in the journal yet. `show(project, f, fact)`: the lines of the brief that show the fact, and nothing else of the
    change. `once`: the fact is a line the author wrote, not what the patch does, so an answer that lets it through
    stands for the ticket's later patches too, until the contract is amended.

    `at`: "ship" for a question about a shipped patch, which `find` raises; "cap" for the one question about a ticket
    at its retry cap, which the table raises (`find` is not called). An answer of such a type has `then` ACT, with
    `does`, the name the table reads, and `effect`, what the brief says the engine then does. `model(project)`: the
    model the run uses where it is not the triage step's own."""
    assert 2 <= len(answers) <= 5, id
    for name, a in answers.items():
        assert a["then"] in (GO, STOP, WAIT, ACT) and a["means"], (id, name)
        assert a["then"] not in (GO, ACT) or not a.get("evidence") or a.get("check"), (id, name)
        assert (a["then"] == WAIT) == bool(a.get("wait")), (id, name)
        assert (a["then"] == ACT) == bool(a.get("does") and a.get("effect")), (id, name)
    QUESTIONS[id] = {"id": id, "raised": raised, "ask": ask, "answers": answers, "find": find, "show": show,
                     "once": once, "at": at, "model": model}


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


def _at_ship(q):
    """Whether a question is about a shipped patch. The one about a ticket at its retry cap is the table's."""
    return (QUESTIONS.get(q.get("type")) or {}).get("at", "ship") == "ship"


def open_questions(events, patch_id):
    """The questions about this patch that have no answer yet. A question about an earlier patch is over: the patch
    it asked about is gone, and a fact that still holds raised a new one at the ship."""
    return [q for q in asked(events) if _at_ship(q) and q.get("patch_id") == patch_id and not q["answer"]]


def then(q):
    """GO, STOP or WAIT for an answered question, None for an open one or a type this engine no longer has."""
    kind = QUESTIONS.get(q.get("type"))
    if not q["answer"] or not kind or q["answer"].get("answer") not in kind["answers"]:
        return None
    return kind["answers"][q["answer"]["answer"]]["then"]


def stopped(events, patch_id):
    """The questions about this patch whose answer stops the change, or holds it for a person."""
    return [q for q in asked(events) if _at_ship(q) and q.get("patch_id") == patch_id and then(q) in (STOP, WAIT)]


def waiting(events):
    """(question, where it stands) for the last question whose answer waits for a person, or (None, None). It stands
    at "wait" until a person continues that wait, then at "restart" until the engine has started the ticket's branch
    again from the base, then at None."""
    for q in reversed(asked(events)):
        if then(q) != WAIT:
            continue
        code = QUESTIONS[q["type"]]["answers"][q["answer"]["answer"]]["wait"]
        after = events[q["answer"]["at_index"] + 1:]
        if not any(e.get("event") == "continued" and e.get("wait") == code for e in after):
            return q, "wait"
        if not any(e.get("event") == "restarted" and e.get("question") == q["id"] for e in after):
            return q, "restart"
        return q, None
    return None, None


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
        "evidence": q["answer"].get("evidence"),
        "told": (a.get("told") or "").replace("{nn}", str(q.get("ticket") or ""))}.items() if value}


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
        if kind["at"] != "ship":
            continue
        for fact in kind["find"](project, f, ref, patch_id, run):
            every = [q for q in before if (q.get("type"), q.get("key")) == (kind["id"], fact["key"])]
            same = [q for q in every if q.get("patch_id") == patch_id]
            last = same[-1] if same else None
            if last and then(last) in (STOP, WAIT) and last["answer"]["at_index"] > amended:
                x = stop_facts(t.events, last["id"])
                run.record("triage", False, patch_id, f"{last['id']} {kind['id']}: {x['answer']}", output=stop_said(x),
                           signed=f"{kind['id']}: {x['answer']}", question=last["id"], type=kind["id"])
                return False
            if last and (not last["answer"] or then(last) == GO):
                continue  # asked about this patch already: open, or let through
            if kind["once"] and any(then(q) == GO and q["answer"]["at_index"] > amended for q in every):
                continue  # the same line was let through on an earlier patch, under the contract as it stands
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
    effect = {GO: "It lets the change through.", STOP: "It stops the change.", WAIT: "It holds the ticket for a person."}
    answers = [f"- `{name}`: {a['means']}" + (f" Evidence: {a['evidence']}" if a.get("evidence") else "")
               + " " + (a.get("effect") or effect[a["then"]])
               for name, a in kind["answers"].items()]
    return "\n".join([
        f"# One question about ticket {f.id} ({q['id']}, {q['type']})", "",
        kind["ask"], "",
        "## The answers", *answers, "",
        "## What raised the question", (q.get("fact") or {}).get("said") or "", "",
        *kind["show"](project, f, dict(q.get("fact") or {}, key=q.get("key"))),
    ]).rstrip() + "\n"


def command(project, kind=None):
    """The command and the model of a triage run: [triage]'s, and the review seat's where that is empty. A type may
    name its own model."""
    config = project.config
    own = kind["model"](project) if kind and kind.get("model") else ""
    return (config["triage"]["command"] or config["review"]["command"],
            own or config["triage"]["model"] or config["review"]["model"])


def run(project, f, receipt, q=None):
    """One run for a question: `q`, or the first open question about the ticket's patch. Its `answered` event and its
    `triage` step go into `receipt`. A run that timed out, could not start or answered with something invalid records
    the step alone, not counted against the author, as a review run with no verdict is."""
    from .review import _structured, model_env
    from .steps import keep_alive

    t, wt = f.t, f.t.worktree
    q = q or open_questions(t.events, f.patch_id)[0]
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
    line, model = command(project, kind)
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
    if a["then"] in (GO, ACT) and a.get("check"):
        if data.get("evidence"):
            wrong = a["check"](project, f, dict(q.get("fact") or {}, key=q.get("key")), data["evidence"])
        else:
            wrong = None if a.get("optional") else "the answer names no evidence"
        fields["evidence_ok"] = not wrong
    receipt.events.append(event(t.id, "answered", **fields))
    detail = f"{q['id']} {q['type']}: {data['answer']}"
    if wrong:
        # An answer whose evidence is not where it says is no answer: the run is started once more, as after any
        # invalid output.
        receipt.record("triage", False, f.patch_id, f"invalid output: {wrong}", ms, counted=False,
                       output=f"The triage run answered `{data['answer']}`, and its evidence did not pass the engine's"
                              f" check: {wrong}", cost_usd=meta.get("cost_usd"), **named)
    elif a["then"] in (STOP, WAIT):
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


def file_in_change(globs_of):
    """A check of evidence: it names a file the change touches that matches the globs `globs_of(project)` gives."""
    def check(project, f, fact, evidence):
        from .util import match_any
        named = evidence.strip().strip("`").strip()
        if named not in project.changed_files(f.t.ref):
            return f"'{named}' is not a file the change touches"
        return None if match_any(globs_of(project), named) else f"'{named}' is not under [tests] paths"
    return check


# --- the question types -----------------------------------------------------------------------

SHOWN = 30000  # characters of a diff a brief shows


def base_tests_of(events, patch_id):
    """The base_tests event of a patch, or None."""
    return next((e for e in reversed(events) if e.get("event") == "base_tests" and e.get("patch_id") == patch_id), None)


def _find_old_test(project, f, ref, patch_id, run):
    found = base_tests_of([*f.t.events, *run.events], patch_id)
    red = [c["command"] for c in (found or {}).get("commands") or [] if c.get("result") == "red"]
    if not red:
        return []
    files = found["files"]
    return [{"key": " ".join(files), "files": files, "base": found.get("base"), "commands": red,
             "said": f"{', '.join(f'`{command}`' for command in red)} passed with the change's tests and failed with"
                     f" the base branch's version of {', '.join(files)}."}]


def _show_old_test(project, f, fact):
    from .steps import test_changes
    base, files = fact.get("base") or project.base_ref, fact["files"]
    # A renamed file's new path too, so that the diff shows the rename and not a deletion.
    now = [new for _, old, new in test_changes(project, f.t.ref) if old in files and new and new != old]
    diff = gitx.out(["diff", "--no-color", "--no-ext-diff", "-U10", "-M", f"{project.base_ref}...{f.t.ref}", "--",
                     *files, *now], project.root)
    if len(diff) > SHOWN:
        diff = diff[:SHOWN] + f"\n(cut at {SHOWN} characters)"
    lines = ["## What the change does to the tests the base had", "```diff", diff.rstrip(), "```",
             "The old version of each file, whole: " + "; ".join(f"`git show {base}:{path}`" for path in files), ""]
    ran = {c["command"]: c for c in (base_tests_of(f.t.events, f.patch_id) or {}).get("commands") or []}
    for command in fact["commands"]:
        lines += ["## The command, with the old tests in place", f"$ {command}",
                  (ran.get(command) or {}).get("output") or "(no output)", ""]
    ticket = f.ticket
    return [*lines, "## The ticket's Why", ticket.sections.get("Why", "").strip() or "(none)", "",
            "## The ticket's Done Contract", ticket.sections.get("Done Contract", "").strip() or "(none)"]


question(
    "old-test",
    "A command that passed at ship fails once the test files the change edited, deleted or renamed are put back as"
    " the base branch has them.",
    "The change edits tests the base branch had, and a command that passes with the edited tests fails with the old"
    " ones. Does the contract ask for what the old tests no longer accept?",
    {"contract": {"means": "the contract asks for this change in behaviour.", "then": GO,
                  "evidence": "the Done Contract line or the sentence of ## Why that asks for it, word for word.",
                  "check": quoted_in_ticket},
     "moved": {"means": "the behaviour is kept; the test was moved, renamed or rewritten, and the old one fails for"
                        " that reason alone.", "then": GO,
               "evidence": "the path of the test file in the change that tests the behaviour now.",
               "check": file_in_change(lambda project: project.config["tests"]["paths"])},
     "lost": {"means": "behaviour is lost that the contract does not ask for.", "then": STOP,
              "told": "Keep the behaviour the old tests check: put back what the change took out of them and make it"
                      " pass. If the contract should ask for the new behaviour, amend it so that it says so (rail"
                      " amend {nn} \"why\"), and the question is asked again."}},
    _find_old_test, _show_old_test)


# --- an exemption the author writes ---------------------------------------------------------------
#
# Three lines an author can write excuse the change from a check. Each raises a question, and each is `once`: the
# line is what is asked about, so an answer that lets it through stands while the line and the contract do.


def _contract(f):
    ticket = f.ticket
    return ["## The ticket's Why", ticket.sections.get("Why", "").strip() or "(none)", "",
            "## The ticket's Done Contract", ticket.sections.get("Done Contract", "").strip() or "(none)"]


def _numbered(text, first, last):
    """The lines first..last of a file's text, each with its number."""
    rows = text.splitlines()
    return [f"{n:>5}  {rows[n - 1]}" for n in range(max(1, first), min(len(rows), last) + 1)]


def _find_sensor_exempt(project, f, ref, patch_id, run):
    from . import sensors
    step = next((e for e in reversed(run.events) if e.get("event") == "step" and e.get("step") == "sensors"), None)
    excused = (step or {}).get("excused") or []
    if not excused:
        return []
    added = sensors.added_lines(project, ref, f.t.worktree or project.root)
    found = {}
    for x in excused:
        # A comment the base already had, or one git shows as moved, is not this change's.
        if (added.get(x["path"]) or {}).get(x["marker_line"]) is not False:
            continue
        key = f"{x['path']}: {x['marker']}"
        fact = found.setdefault(key, {"key": key, "path": x["path"], "line": x["marker_line"], "marker": x["marker"],
                                      "violations": []})
        said = f"{x['path']}:{x['line']}: {x['message']} (sensor {x['sensor']})"
        if said not in fact["violations"]:
            fact["violations"].append(said)
    for fact in found.values():
        fact["said"] = (f"The change adds the comment `{fact['marker']}` at {fact['path']}:{fact['line']}, and it"
                        f" excuses {len(fact['violations'])} violation(s) of a sensor.")
    return list(found.values())


def _show_sensor_exempt(project, f, fact):
    ref = f"{f.t.ref}:{fact['path']}"
    text = gitx.read_blobs([ref], project.root).get(ref) or ""
    fixes = {s["id"]: s.get("fix") for s in project.config["sensors"] if s.get("fix")}
    named = sorted({v.rsplit("(sensor ", 1)[-1].rstrip(")") for v in fact["violations"]})
    return ["## What the sensor reported, and the comment excuses", *[f"- {v}" for v in fact["violations"]],
            *[f"What sensor {name} asks for: {fixes[name]}" for name in named if name in fixes], "",
            f"## {fact['path']}, around line {fact['line']}", "```", *_numbered(text, fact["line"] - 8, fact["line"] + 12),
            "```", "", *_contract(f)]


question(
    "sensor-exempt",
    "The change adds a `SENSOR(NN): why` comment, and the comment excuses a sensor's violation on a line the change"
    " adds.",
    "A sensor reported the line, and the author's comment says the sensor is wrong about it. Does the comment's"
    " reason hold?",
    {"holds": {"means": "the sensor misreads the line, or the contract requires the line as it is.", "then": GO,
               "evidence": "where the contract requires the line, the Done Contract line or the sentence of ## Why"
                           " that requires it, word for word; none where the sensor misreads the line.",
               "check": quoted_in_ticket, "optional": True},
     "does-not-hold": {"means": "the sensor is right about the line, and the contract does not require it.",
                       "then": STOP,
                       "told": "Take the comment out and mend the line so that the sensor passes."}},
    _find_sensor_exempt, _show_sensor_exempt, once=True)


def _find_decided(project, f, ref, patch_id, run):
    from .project import ticket_path
    from .ticket import Ticket
    now, base = f"{ref}:{ticket_path(f.id)}", f"{project.base_ref}:{ticket_path(f.id)}"
    held = gitx.read_blobs([now, base], project.root)
    if not held.get(now):
        return []
    # A row the base branch's copy of the ticket has came with a contract a person merged: it is not this change's.
    before = set(Ticket(held[base]).decided()) if held.get(base) else set()
    return [{"key": row, "row": row,
             "said": f"The ticket's ## Assumptions holds a row its author decided and did not check: {row}"}
            for row in dict.fromkeys(Ticket(held[now]).decided()) if row not in before]


def _show_decided(project, f, fact):
    return ["## The row", f"VERIFIED: decided, not checked: {fact['row']}", "", *_contract(f), "",
            "## Where the ticket may change", ", ".join(f.ticket.scope) or "(no scope)"]


question(
    "decided",
    "The ticket gains a `VERIFIED: decided, not checked:` row in `## Assumptions`.",
    "The author wrote that this was a choice nobody could check. Is it one?",
    {"choice": {"means": "nothing in the repository or its dependencies settles it, and no Done Contract item"
                         " depends on it.", "then": GO},
     "checkable": {"means": "it can be checked.", "then": STOP,
                   "evidence": "where: the file, the command or the document that settles it.",
                   "told": "Check it where the answer names, then write in the row how you checked: `VERIFIED:` and"
                           " what you ran or read, without `decided, not checked:`."},
     "contract": {"means": "a Done Contract item depends on it, so the choice belongs in the contract.", "then": STOP,
                  "evidence": "the Done Contract item that depends on it, word for word.",
                  "told": "Amend the contract so that the choice stands where the reviewer reads it: state it in the"
                          " Done Contract item that depends on it, take the row out of ## Assumptions, and run rail"
                          " amend {nn} \"why\"."}},
    _find_decided, _show_decided, once=True)


IGNORED = ".gitleaksignore"   # one fingerprint a line: a finding the secret scan no longer reports


def fingerprint(line):
    """A line of .gitleaksignore as {commit, file, rule, line}: `commit:file:rule:line` from a scan of commits. An
    empty dict for a line in another form."""
    parts = line.strip().split(":")
    if len(parts) < 4 or not parts[-1].isdigit() or not all(c in "0123456789abcdef" for c in parts[0].lower()):
        return {}
    return {"commit": parts[0], "file": ":".join(parts[1:-2]), "rule": parts[-2], "line": int(parts[-1])}


def _ignored(text):
    return [row.strip() for row in (text or "").splitlines() if row.strip() and not row.strip().startswith("#")]


def _find_secret(project, f, ref, patch_id, run):
    now, base = f"{ref}:{IGNORED}", f"{project.base_ref}:{IGNORED}"
    held = gitx.read_blobs([now, base], project.root)
    before = set(_ignored(held.get(base)))
    return [{"key": row, **fingerprint(row),
             "said": f"The change adds `{row}` to {IGNORED}, so the secret scan no longer reports that finding."}
            for row in dict.fromkeys(_ignored(held.get(now))) if row not in before]


def _scanned(project, fact):
    """The finding as gitleaks reports it with the string redacted: {match, start, end}, or None when gitleaks is not
    on the machine or reports no such finding. It reads the one commit from the project's root, whose checkout does
    not have the ticket's new line in .gitleaksignore."""
    import shutil
    import subprocess
    if not fact.get("commit") or not shutil.which("gitleaks"):
        return None
    with tempfile.TemporaryDirectory(prefix="rail-scan-") as held:
        report = os.path.join(held, "report.json")
        try:
            subprocess.run(["gitleaks", "git", "--no-banner", "--redact", f"--log-opts=-1 {fact['commit']}",
                            "--report-format", "json", "--report-path", report, project.root], cwd=project.root,
                           capture_output=True, text=True, timeout=120, check=False)
            with open(report) as fh:
                found = json.load(fh)
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    for x in found if isinstance(found, list) else []:
        if isinstance(x, dict) and x.get("Fingerprint") == fact["key"]:
            return {"match": str(x.get("Match") or ""), "start": int(x.get("StartLine") or fact["line"]),
                    "end": int(x.get("EndLine") or x.get("StartLine") or fact["line"])}
    return None


def _show_secret(project, f, fact):
    if not fact.get("commit"):
        return ["## The line", fact["key"], "",
                "It is not a fingerprint of a scan of commits (`commit:file:rule:line`), so the engine can't show the"
                " finding. Run the project's secret scan without the line to see what it takes out."]
    lines = ["## The finding the line takes out of the secret scan", f"Rule: {fact['rule']}",
             f"File: {fact['file']}, line {fact['line']}", f"Commit: {fact['commit']}", ""]
    ref = f"{fact['commit']}:{fact['file']}"
    text = gitx.read_blobs([ref], project.root).get(ref) or ""
    seen = _scanned(project, fact)
    # The string is shown only as the scan redacts it. Without the scan's own report the engine can't tell where the
    # string ends, so it shows the lines above the finding and nothing from its first line on.
    start = seen["start"] if seen else fact["line"]
    lines += [f"## {fact['file']} at that commit", "```", *_numbered(text, start - 5, start - 1)]
    if seen:
        lines += [f"{start:>5}  {seen['match']}", *_numbered(text, seen["end"] + 1, seen["end"] + 5), "```",
                  "The scan's own redaction stands in for the string."]
    else:
        lines += [f"{start:>5}  (the line the scan reported is not shown)", "```",
                  "The scan's report could not be read here, so the string and the lines after it are left out."]
    return lines


def _said(project, f, fact, evidence):
    return None if len(evidence.strip()) >= 3 else "the answer does not say what the string is"


question(
    "secret",
    f"The change adds a line to `{IGNORED}`, which takes one finding out of the secret scan.",
    "The secret scan reported a string in this branch's commits, and the author's line says it is no secret. Is the"
    " string a credential that works, or worked, anywhere?",
    {"not-a-secret": {"means": "the string is no credential: an example, a fixture, a public id.", "then": GO,
                      "evidence": "what the string is, in a few words.", "check": _said},
     "secret": {"means": "the string is, or may be, a real credential. It is pushed, so it counts as leaked.",
                "then": WAIT, "wait": "SECRET_FOUND",
                "told": "Stop here: a person rotates the secret. Don't take the string or the line out yourself. Once"
                        " the person has acted, the engine starts the ticket's branch again from the base branch,"
                        " because the scan fails on this branch's commits for good."}},
    _find_secret, _show_secret, once=True)


# --- a ticket at its retry cap --------------------------------------------------------------------
#
# One question for a ticket, raised by the table when the ticket reaches its retry cap or its budget after consult
# (rail docs retries). It is not about a patch: it asks why the attempts fail, and each answer names what the engine
# does next.

STUCK_RUNS = 2  # runs with no answer after which the ticket is handled as if the answer were `cannot-tell`


def diagnosis(events):
    """The `stuck` question of a ticket as `asked` gives it, with `runs_without_answer`, or None when none was
    raised."""
    q = next((q for q in asked(events) if q.get("type") == "stuck"), None)
    if q:
        q["runs_without_answer"] = sum(
            1 for e in events[q["at_index"]:]
            if e.get("event") == "step" and e.get("step") == "triage" and e.get("question") == q["id"]
            and (e.get("counted") is False or e.get("status") == "could_not_run"))
    return q


def diagnosed(q):
    """A diagnosis in the words a record or a brief keeps: {answer, means, reason, evidence}, or None while it has
    no answer."""
    if not q or not q.get("answer") or q["answer"].get("answer") not in QUESTIONS["stuck"]["answers"]:
        return None
    a = q["answer"]
    return {key: value for key, value in {
        "answer": a["answer"], "means": QUESTIONS["stuck"]["answers"][a["answer"]]["means"],
        "reason": a.get("reason"), "evidence": a.get("evidence")}.items() if value}


def diagnosis_said(x):
    """A diagnosis in one line, from `diagnosed`."""
    return (f"`{x['answer']}`, {x['means']}" + (f" Its reason: {x['reason']}" if x.get("reason") else "")
            + (f" What it names: {x['evidence']}" if x.get("evidence") else ""))


def raise_stuck(f, said, steps_):
    """The `question` event of the diagnosis: `said` is why the ticket is stuck, `steps_` the steps at their cap."""
    number = len(asked(f.t.events)) + 1
    return event(f.id, "question", id=f"Q{number}", type="stuck", key="stuck", fact={"said": said, "steps": steps_})


def _show_stuck(project, f, fact):
    from .project import advice_path
    t, ticket = f.t, f.ticket
    lines = [*_contract(f), "", "## Where the ticket may change", ", ".join(ticket.scope) or "(no scope)", ""]
    failed = [e for e in t.events if e.get("event") == "step" and e.get("result") == "fail" and e.get("step") != "triage"
              and e.get("counted", True)]
    lines += ["## Each failed attempt, oldest first",
              *([f"- step `{e.get('step')}`" + (f", signature `{e['signature']}`" if e.get("signature") else "")
                 + (f": {e['detail']}" if e.get("detail") else "") for e in failed[-20:]] or ["(none in the journal)"]), ""]
    try:
        kept = json.loads(project.cache_read("failure", f.id) or "null")
    except ValueError:
        kept = None
    if isinstance(kept, dict) and kept.get("output"):
        lines += ["## The output of the last failed attempt", "```", tail(kept["output"], 60), "```", ""]
    found = [f.ledger.describe(fid) for fid in f.ledger.findings]
    if found:
        lines += ["## What the reviewer found", *found, ""]
    ref = f"{t.ref}:{advice_path(f.id)}"
    advice = (gitx.read_blobs([ref], project.root).get(ref) or "").strip()
    if advice:
        lines += ["## Advice a second model gave the worker (consult)", advice, ""]
    diff = gitx.out(["diff", "--no-color", "--no-ext-diff", f"{project.base_ref}...{t.ref}", "--", ".",
                     ":(exclude).rail/tickets", ":(exclude).rail/journal"], project.root)
    if len(diff) > SHOWN:
        diff = diff[:SHOWN] + f"\n(cut at {SHOWN} characters)"
    return [*lines, "## The change as it stands", "```diff", diff.rstrip() or "(no change to any product file)", "```"]


def lines_in_contract(project, f, fact, evidence):
    """The evidence is one or more lines of the Done Contract, each word for word but for spacing and backticks.
    Returns what is wrong, or None."""
    held = _plain(f.ticket.sections.get("Done Contract", ""))
    rows = [_plain(row) for row in evidence.splitlines() if _plain(row)]
    if not rows or any(len(row) < 8 for row in rows):
        return "a quoted line is too short to be looked up"
    missing = [row for row in rows if row not in held]
    return f"this line is not in the Done Contract of the ticket: {missing[0]}" if missing else None


def _parts(project, f, fact, evidence):
    rows = [row for row in evidence.replace(";", "\n").splitlines() if row.strip(" -*")]
    return None if len(rows) >= 2 else "the answer names fewer than two parts: one on each line"


# Not tested with a model run: the question, the answers and what each tells the run, as the rest of the brief.
question(
    "stuck",
    "A ticket reaches its retry cap, or its retry budget after consult advised. Raised once for a ticket.",
    "This ticket's attempts keep failing. Before anything else is done with it: why? Is the contract at fault, is the"
    " work too large for one ticket, do the attempts share a mistake, or is the machine at fault?",
    {"contract": {"means": "a `Check:` line or a Done Contract item is wrong, or two of them contradict each other.",
                  "then": ACT, "does": "amend", "check": lines_in_contract,
                  "evidence": "the line or lines of the Done Contract that are wrong, word for word, one on each line.",
                  "effect": "The contract writer amends the contract, and the ticket is tried again."},
     "too-large": {"means": "the work is more than one ticket.", "then": ACT, "does": "split", "check": _parts,
                   "evidence": "the parts it falls into, one on each line.",
                   "effect": "The contract writer files a ticket for each part, and this one is dropped."},
     "approach": {"means": "the contract is right, and the attempts share a mistake.", "then": ACT, "does": "restart",
                  "check": _said, "evidence": "what the attempts share, and what to do instead.",
                  "effect": "The ticket's branch starts again from the base branch, and the worker is told what you"
                            " name."},
     "machine": {"means": "the failures are the machine's or a tool's, not the change's.", "then": ACT,
                 "does": "machine", "check": _said, "evidence": "the failure that shows it, as the output has it.",
                 "effect": "The ticket waits for a person to mend the machine."},
     "cannot-tell": {"means": "none of the others can be shown from what is here.", "then": ACT, "does": "as-before",
                     "effect": "An AUTO ticket is dropped, and a PERSON ticket waits for a person."}},
    lambda project, f, ref, patch_id, run: [], _show_stuck, at="cap",
    model=lambda project: project.config["worker"]["contract"].rpartition(":")[0])
