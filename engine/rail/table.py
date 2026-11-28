"""The first-match table: for one ticket's facts, the first matching row names the next legal move.

Rows whose code is in TRANSITIONS are moves `next` makes itself (accepting an AUTO ticket, claiming, resuming, asking
consult); `next` makes the move, derives the facts again, and reads the table once more.

A row for an agent's task or a person's wait builds `facts`: the values its brief is made of, as plain JSON. The
renderer of its code writes the brief from those facts and nothing else, so what the answer carries as `action.facts`
is all the brief says (engine/answer-v1.json names the keys). A renderer reads no ticket, no config and no file.
"""

import json
import os

from . import flakes, gitx, history, tools
from .project import advice_path, ticket_path
from .review import describe_finding
from .ticket import Ticket
from .util import MISSING_HELP, NOT_COUNTED, tried_help

TRANSITIONS = {"ACCEPT_AUTO", "CLAIM", "RESUME", "CONSULT", "GO", "REBASE_BEHIND", "CONTRACT_MERGED", "STUCK",
               "RESTART", "DIAGNOSE"}
MERGE_PATIENCE = 600  # seconds a requested merge may take before a person looks
OPEN = ("implementing", "reviewing", "in-ci", "merge-ready")

# What a person's wait asks of them: an approval of something a revert doesn't undo (money included), a grant (the
# machine lacks something a person gives once: a tool, a key, a setting to repair), or a hold (the person's own brake).
WAIT_KINDS = {
    "APPROVE_CONTRACT": "approval", "APPROVE_AMEND": "approval", "MERGE_BY_PERSON": "approval", "RETRY_CAP": "approval",
    "BUDGET": "approval",
    "TOOL_MISSING": "grant", "TOOL_DOWN": "grant", "STUCK_REVIEW": "grant", "MERGE_FAILED": "grant",
    "SECRET_FOUND": "grant",
    "HOLD": "hold", "STOPPED": "hold",
}


# --- facts: what a row reads from the ticket, as plain values ----------------------------------------------


def _shared(f):
    """The keys every answer with facts has."""
    return {"ticket": f.id, "title": f.ticket.title if f.ticket else "", "branch": f.t.name,
            "ticket_file": ticket_path(f.id)}


def _pr_fact(f):
    return {"number": f.pr["number"], "url": f.pr["html_url"], "open": f.pr_open} if f.pr else None


def _wait(code, f, accept=True, **ways):
    """How a person answers a wait: its kind, and each way that works here, by name. `accept` is the command,
    `label` the label to put on the ticket's pull request when it has an open one."""
    found = {"kind": WAIT_KINDS[code]}
    if accept:
        found["accept"] = f"rail accept {f.id}"
        if f.pr_open:
            found["label"] = "rail:go"
    found.update({name: way for name, way in ways.items() if way})
    return found


def _finding_facts(f):
    """The findings a brief lists: the blocking ones still to answer, then the open advisory ones. None while no
    blocking finding is open, since the brief then says nothing of findings."""
    ids = f.ledger.unanswered()
    return [f.ledger.fact(fid) for fid in ids + f.ledger.open_advisory()] if ids else []


def _not_taken(f):
    """An issue that held a whole ticket, taken as a request only: why, so whoever runs the bot can fix it."""
    req = next((e for e in f.t.events if e.get("event") == "requested"), None)
    return (req or {}).get("not_taken") or None


def _size(f):
    from . import rules
    if not f.auto or not f.worktree:
        return None
    return {"count": rules.size(f.project, None, f.worktree)[0], "cap": f.project.config["size"]["cap"]}


def _migration(f):
    from .state import floor
    return any(key == "migration_paths" for _, _, key in floor(f.project, f.ticket.scope)[1])


def _base_green(f):
    """Every check of the contract as it stands passed on the base before any work: the checks can't tell done
    from not done yet. False once the contract's checks differ from the ones run on the base."""
    found = f.t.last("base_checks")
    checks = (found or {}).get("checks") or []
    if not checks or any(c.get("result") != "green" for c in checks):
        return False
    return [c.get("command") for c in checks] == f.ticket.checks()


def _ticket_now(f):
    """The ticket as the worktree has it: the agent writes ## Tried and ## Look at there before a ship commits them."""
    if f.worktree:
        try:
            with open(os.path.join(f.worktree, ticket_path(f.id)), encoding="utf-8") as copy:
                return Ticket(copy.read())
        except OSError:
            pass
    return f.ticket


def _save_note(f):
    """Whether the brief tells the agent to save: where no hook saves for the session, the agent does. Unsaved work
    is lost with the machine, and a ticket that shows no life is taken to be abandoned."""
    return not (f.project.session and f.project.cache_read("hooks", f.project.session))


def _failure_output(f, e):
    """The output of the failed ship step `e`, which the answer of that `advance` showed. The journal keeps only the
    step's detail; advance keeps the output in the local cache, so a later brief for the same failure has it too."""
    try:
        kept = json.loads(f.project.cache_read("failure", f.id) or "null")
    except ValueError:
        return ""
    if not isinstance(kept, dict) or kept.get("patch_id") != e.get("patch_id") or \
            e.get("signature") not in (kept.get("signatures") or []):
        return ""
    return kept.get("output") or ""


def _advice(f, step):
    """Consult's latest advice, while the attempt it was given for is still to come. `rail advance` shows it once;
    a fresh worker gets its brief from `rail next` and would otherwise never see it."""
    if step not in f.advised:
        return None
    ref = f"{f.t.ref}:{advice_path(f.id)}"
    text = gitx.read_blobs([ref], f.project.root).get(ref) or ""
    return text.strip().rsplit("\n## ", 1)[-1].strip() or None


def _stuck_facts(f):
    """Why each capped step waits: the same failure at the budget, or the cap on failures of any kind."""
    return [{"step": step, "why": f.capped_why[step], "attempts": f.attempts[step],
             "budget": f.project.config["retry"]["budget"]} for step in f.capped]


def _could_not_run(f, steps):
    """For a person at the retry cap: which of the capped steps last ended without running at all."""
    last = {}
    for e in f.t.events:
        if e.get("event") == "step" and e.get("step") in steps:
            last[e["step"]] = e
    return [{"step": s, "detail": e.get("detail")} for s, e in last.items() if e.get("status") == "could_not_run"]


def _conflicted(f):
    """The files a rebase stopped on, or those a merge of the base into the branch would conflict in. Best effort:
    an empty list when git can't say."""
    if f.rebasing and f.worktree:
        return gitx.git(["diff", "--name-only", "--diff-filter=U"], f.worktree, check=False).stdout.split("\n")[:-1]
    base, tip = gitx.rev(f.project.base_ref, f.project.root), gitx.rev(f.t.ref, f.project.root) if f.t.ref else None
    if not base or not tip:
        return []
    out = gitx.git(["merge-tree", "--write-tree", "--name-only", "--no-messages", base, tip], f.project.root, check=False)
    return [line for line in out.stdout.split("\n")[1:] if line] if out.returncode == 1 else []


def _facts_stopped(f):
    return {**_shared(f), "stop": f.stopped, "wait": _wait("STOPPED", f, accept=False, issue=f.stopped["url"])}


def _facts_rebasing(f):
    return {**_shared(f), "cwd": f.cwd, "conflicted": _conflicted(f)}


def _facts_budget(f):
    return {**_shared(f), "spent": f.spent, "limit": f.project.config["worker"]["ticket_usd"], "spent_by": f.spent_by,
            "wait": _wait("BUDGET", f, drop=f"rail drop {f.id} --by person")}


def _facts_lint(f):
    return {**_shared(f), "lint_errors": f.lint_errors, "not_taken": _not_taken(f)}


def _facts_approve_contract(f):
    return {**_shared(f), "tier": f.tier, "pr": _pr_fact(f),
            "wait": _wait("APPROVE_CONTRACT", f, drop=f"rail drop {f.id} --by person")}


def _facts_after_dropped(f):
    return {**_shared(f), "tier": f.tier, "after_dropped": f.after_dropped}


def _facts_tool_missing(f):
    return {**_shared(f), "tools_missing": f.tools_missing, "machine": tools.machine(),
            "wait": _wait("TOOL_MISSING", f, accept=False,
                          set=sorted({name for names in f.tools_missing.values() for name in names}))}


def _facts_approve_amend(f):
    return {**_shared(f), "amend_reason": f.amend_reason, "pr": _pr_fact(f), "wait": _wait("APPROVE_AMEND", f)}


def _diagnosis(f):
    """The diagnosis the ticket got at its retry cap, once it has an answer: {answer, means, reason, evidence}."""
    from . import triage
    return triage.diagnosed(f.diagnosis)


def _facts_capped(f):
    return {**_shared(f), "stuck": _stuck_facts(f), "could_not_run": _could_not_run(f, f.capped), "pr": _pr_fact(f),
            "diagnosis": _diagnosis(f), "wait": _wait("RETRY_CAP", f)}


def _facts_stuck_contract(f):
    return {**_shared(f), "cwd": f.cwd, "stuck": _stuck_facts(f), "diagnosis": _diagnosis(f)}


def _facts_stuck_split(f):
    external = (f.ticket.get("external_id") or "") if f.ticket else ""
    return {**_shared(f), "cwd": f.cwd, "stuck": _stuck_facts(f), "diagnosis": _diagnosis(f),
            "external_id": external if external.startswith("github#") else None}


def _facts_tool_down(f):
    e, times = f.machine_stuck
    return {**_shared(f), "failed": {key: e[key] for key in ("step", "detail", "tools_down") if e.get(key)},
            "times": times, "pr": _pr_fact(f), "diagnosis": _diagnosis(f) if f.diagnosed == "machine" else None,
            "wait": _wait("TOOL_DOWN", f)}


def _facts_person(code):
    """A wait whose brief names only the ticket and its pull request."""
    return lambda f: {**_shared(f), "pr": _pr_fact(f), "wait": _wait(code, f)}


def _facts_stuck_review(f):
    return {**_shared(f), "run": f.stuck_run, "pr": _pr_fact(f), "wait": _wait("STUCK_REVIEW", f)}


def _facts_secret(f):
    q = f.triage_wait
    fact = q.get("fact") or {}
    return {**_shared(f), "question": q["id"], "reason": q["answer"].get("reason") or "",
            "finding": {key: fact[key] for key in ("rule", "file", "line", "commit") if fact.get(key)},
            "pr": _pr_fact(f), "wait": _wait("SECRET_FOUND", f)}


def _restarted(f):
    """The branch the engine started again from the base, until the ticket ships on the new one: the old branch's
    name, and what the scan found there or, after the diagnosis of a stuck ticket, what the attempts shared."""
    last = max((i for i, e in enumerate(f.t.events) if e.get("event") == "restarted"), default=-1)
    if last < 0 or any(e.get("event") == "shipped" for e in f.t.events[last:]):
        return None
    e = f.t.events[last]
    return {key: e[key] for key in ("branch", "rule", "file", "type", "note") if e.get(key)}


def _facts_stuck(f):
    return {**_shared(f), "stuck": _stuck_facts(f), "diagnosis": _diagnosis(f)}


def _facts_sweep_tickets(f):
    return {**_shared(f), "cwd": f.cwd, "summary_file": f".rail/journal/{f.id}-summary.md"}


def _facts_setup_failed(f):
    return {**_shared(f), "cwd": f.cwd, "failed": {"step": f.setup_failed.get("step") or "setup",
                                                   "detail": f.setup_failed.get("detail", "")}}


def _facts_assumptions(f):
    return {**_shared(f), "cwd": f.cwd, "open_assumptions": f.open_assumptions}


def _facts_conflict(f):
    return {**_shared(f), "cwd": f.cwd, "pr": _pr_fact(f), "conflicted": _conflicted(f)}


def _facts_red_check(f):
    return {**_shared(f), "cwd": f.cwd, "pr": _pr_fact(f),
            "checks": [{"name": name, "summary": summary} for name, summary in f.ci_failing],
            "findings": _finding_facts(f), "person_note": f.person_note}


def _facts_split(f):
    return {**_shared(f), "cwd": f.cwd, "size": f.split.get("size"), "cap": f.split.get("cap"),
            "rest_branch": f"split/{f.id}-rest", "remote": f.project.remote, "person_note": f.person_note}


def _facts_step_failed(f):
    e = f.last_fail
    output = _failure_output(f, e)
    if flakes.TOLD not in output and any(x["step"] == e.get("step") and x["patch_id"] == e.get("patch_id")
                                         for x in flakes.of(f.t.events)):
        output = f"{output}\n\n{flakes.TOLD}".strip()  # another machine's ship: the journal still says so
    found = {**_shared(f), "cwd": f.cwd, "output": output,
             "failed": {key: e[key] for key in ("step", "status", "detail", "signature", "counted", "tools_down")
                        if e.get(key) is not None},
             "findings": _finding_facts(f), "person_note": f.person_note}
    if e.get("status") != "could_not_run" and not e.get("tools_down"):  # an attempt at the work itself
        found.update(tried=_ticket_now(f).tried(), advice=_advice(f, e.get("step")))
    if e.get("step") == "triage":
        # The answer that stopped the change is in the journal, so every clone's brief has it.
        from . import triage
        found["triage"] = triage.stop_facts(f.t.events, e.get("question"))
    return found


def _facts_revert(f):
    return {**_shared(f), "cwd": f.cwd, "revert": f.revert, "scope_paths": list(f.ticket.scope),
            "save_note": _save_note(f), "findings": _finding_facts(f), "person_note": f.person_note}


def _facts_revert_ship(f):
    return {**_shared(f), "revert": f.revert}


def _facts_implement(f):
    return {**_shared(f), "cwd": f.cwd, "why": f.ticket.sections.get("Why", ""), "decided": f.ticket.decided(),
            "done_contract": {"text": f.ticket.sections.get("Done Contract", ""), "checks": f.ticket.checks()},
            "base_green": _base_green(f), "scope_paths": list(f.ticket.scope),
            "out_of_scope": f.ticket.sections.get("Out of scope", ""), "size": _size(f), "migration": _migration(f),
            "tools": tools.declared(f.project), "tried": _ticket_now(f).tried(),
            "history": history.of(f.project, f.ticket.scope, skip=f.id), "save_note": _save_note(f),
            "findings": _finding_facts(f), "person_note": f.person_note, "restarted": _restarted(f)}


def _facts_answer(f):
    return {**_shared(f), "findings": _finding_facts(f), "person_note": f.person_note}


def _facts_merge_by_person(f):
    way = {"merge": f.pr["html_url"] if f.pr else "the pull request"} if f.project.remote else {}
    return {**_shared(f), "tier": f.tier, "pr": _pr_fact(f), "remote": bool(f.project.remote),
            "asked": f.ledger.asked_for_person(), "wait": _wait("MERGE_BY_PERSON", f, accept=not f.project.remote, **way)}


# --- renderers: the brief, from the facts alone ----------------------------------------------------------------


def _join(items):
    return ", ".join(items)


def _pr(x):
    return f"PR #{x['pr']['number']} ({x['pr']['url']})" if x.get("pr") else "its pull request"


def _go(x):
    """How a person continues a wait from GitHub, where a cloud session leaves them: the label on the pull request."""
    return (f" On GitHub: add the label rail:go to {_pr(x)}; a comment there reaches the agent as your note."
            if (x.get("pr") or {}).get("open") else "")


def _note(x):
    if not x.get("person_note"):
        return ""
    return (f"\n\nA person said: \"{x['person_note']}\". If that holds beyond this ticket, open a ticket that writes it into"
            " the project's part of AGENTS.md, or into a rule, so nobody has to say it twice.")


def _findings(x, intro):
    if not x.get("findings"):
        return ""
    return "\n".join([
        "", intro,
        f"Fix each blocking finding in the worktree. Then answer each one: rail answer {x['ticket']} F1 fixed \"what you"
        f" changed\", or declined \"why it is not a problem\", or parked \"a real problem this change didn't cause\".",
        "Declining or parking a blocking finding disputes it, and a fresh refuter decides whether it holds and whether"
        " this change caused it. An advisory finding doesn't hold the ticket: fix and answer it too, or leave it"
        " unanswered for the sweep.",
        *[f"- {describe_finding(finding, scripts=True)}" for finding in x["findings"]],
    ])


def _save_line(x):
    if not x.get("save_note"):
        return ""
    return (f"\nNothing saves your work for you in this session. Run rail save {x['ticket']} every ten minutes or so of"
            " work and before you stop: it pushes what you have, and shows other sessions this ticket is alive.")


def _size_line(x):
    size = x.get("size")
    if not size:
        return ""
    line = f"size {size['count']}/{size['cap']}"
    if size["count"] >= 0.8 * size["cap"]:
        line += (": past 80% of the cap. Split what is left into a new ticket (rail add); over the cap, ship offers"
                 " a split once, because a reviewer checks a small change better")
    return line


def _tried_lines(x):
    """What earlier attempts at this ticket tried, for an agent that starts with none of their context."""
    if not x.get("tried"):
        return []
    return ["Tried before on this ticket, and it didn't work (## Tried in the ticket):", *[f"- {t}" for t in x["tried"]]]


def _stuck(row):
    """Why a step waits for a person: the same failure at the budget, or the cap on failures of any kind."""
    if row["why"] == "cap":
        return f"'{row['step']}' failed {row['attempts']} times since it last passed, whatever the output ([retry] cap)"
    after = ", then once more after consult" if row["why"] == "consulted" else ""
    return f"'{row['step']}' failed the same way {row['budget']} times in a row{after} ([retry] budget)"


def stuck_reason(f):
    """(reason, step, signature) for an AUTO ticket the engine drops at the retry cap: what was tried and why it
    stopped. It goes into the dropped event, the drop mark and the issue's comment."""
    step = f.capped[0]
    last = [e for e in f.t.events if e.get("event") == "step" and e.get("step") == step and e.get("result") == "fail"]
    detail = last[-1].get("detail") if last else ""
    reason = f"stuck: {_stuck(_stuck_facts(f)[0])}" + (f"; the last failure: {detail}" if detail else "")
    found = _diagnosis(f)
    if found:
        from . import triage
        reason += f". The diagnosis it got at the cap: {triage.diagnosis_said(found)}"
    return reason, step, last[-1].get("signature") if last else None


def stop_brief(stop, what):
    """What a brake's wait says, about one ticket or about the repository."""
    where = f" for the paths {', '.join(stop['paths'])}" if stop["paths"] else ""
    return (f"A person stopped Rail{where}: issue #{stop['number']} ({stop['title']}) is open with the label rail:stop."
            f" Nothing is done on {what} until that issue is closed or loses the label; a run that then starts goes on"
            f" by itself. Do no work on it meanwhile. {stop['url']}").rstrip()


def _render_stopped(x):
    return stop_brief(x["stop"], f"ticket {x['ticket']}" if x.get("ticket") else "any ticket")


def _render_rebasing(x):
    return (f"A rebase is under way in {x['cwd']} (ticket {x['ticket']}, branch {x['branch']}). Finish it there: resolve"
            " each conflicted file, git add it, then git rebase --continue. To give the rebase up: git rebase --abort."
            f" Then run: rail advance {x['ticket']}\nRail writes nothing to the ticket until the rebase has ended.")


def _render_budget(x):
    spent = ", ".join(f"{what} ${usd:.2f}" for what, usd in sorted(x["spent_by"].items(), key=lambda item: -item[1]))
    return (f"Ticket {x['ticket']} has spent ${x['spent']:.2f} since a person last acted, over [worker] ticket_usd"
            f" (${x['limit']:g}): {spent}. These are the costs the runs reported,"
            f" not the bill. To let it go on, with the count starting again: {x['wait']['accept']}, or the rail:go label"
            f" on its pull request. To end it: {x['wait']['drop']}")


def _render_lint(x):
    not_taken = (f"\nThe issue held a whole ticket, and Rail took it only as a request: {x['not_taken']}. Write the"
                 " contract from it, keeping what it says.") if x.get("not_taken") else ""
    return (f"Ticket {x['ticket']} isn't complete: {'; '.join(x['lint_errors'])}. Read it ({x['ticket_file']} on branch"
            f" {x['branch']}), write the whole ticket to a file with its Done Contract, tier and scope_paths, and run:"
            f" rail amend {x['ticket']} --file FILE" + not_taken)


def _render_approve_contract(x):
    return (f"Approve the contract of ticket {x['ticket']} ({x['tier']}): read {x['ticket_file']} on branch {x['branch']},"
            f" then run: {x['wait']['accept']}. To change it, say what to change. To reject it, run:"
            f" {x['wait']['drop']}"
            + (f" On GitHub: {_pr(x)} shows the contract; the label rail:go approves it, a comment asks for a"
               f" change, and closing it rejects it." if (x.get("pr") or {}).get("open") else ""))


def _render_after_dropped(x):
    nn, gone = x["ticket"], _join(x["after_dropped"])
    # No person is asked: whether the ticket stands without the dropped one is the contract writer's call, and
    # either answer is recorded and can be undone.
    return (f"Ticket {nn} comes after ticket {gone}, which was dropped. Read both tickets and"
            f" decide whether ticket {nn} still stands without it. If it does, remove {gone}"
            f" from `after`: write the whole ticket to a file and run rail amend {nn} \"why it stands without"
            f" it\" --file FILE. If it doesn't, drop it: rail drop {nn} --reason \"why\".")


def _render_tool_missing(x):
    """One ticket's wait, or the one wait of several tickets ("1, 2") with what else rests."""
    resting = x.get("resting") or []
    return (tools.wait_brief(", ".join(x["tickets"]) if x.get("tickets") else x["ticket"], x["tools_missing"], x["machine"])
            + (("\nNothing for an agent on these now:\n" + "\n".join(resting)) if resting else ""))


def _render_approve_amend(x):
    return (f"The Done Contract of ticket {x['ticket']} changed (rail amend)."
            + (f" The agent's reason: {x['amend_reason']}" if x.get("amend_reason") else "")
            + f" Read {x['ticket_file']} on branch {x['branch']}, then approve it: {x['wait']['accept']}." + _go(x))


def _render_capped(x):
    missing = [f"'{row['step']}' ({row['detail']})" for row in x["could_not_run"]]
    could_not = (f" Its last attempt at {_join(missing)} could not run: the shell couldn't start the command or a tool it"
                 f" calls, so nothing was checked.") if missing else ""
    return (f"Ticket {x['ticket']} is stuck: {'; '.join(_stuck(row) for row in x['stuck'])}.{could_not}"
            f"{_diagnosed(x)} A person"
            f" looks at the journal and the branch {x['branch']}, then continues it: {x['wait']['accept']} \"what to do"
            f" differently\". That gives a fresh budget and a fresh cap." + _go(x))


def _diagnosed(x):
    """The diagnosis a stuck ticket got, as a sentence of a brief; empty when it got none."""
    found = x.get("diagnosis")
    if not found:
        return ""
    from . import triage
    return (f" A run that did not write the change read the attempts once and answered {triage.diagnosis_said(found)}")


# Not tested with a model run: the wording of the two briefs below, which the contract writer reads.
def _render_stuck_contract(x):
    nn, found = x["ticket"], x["diagnosis"]
    return "\n".join([
        f"Ticket {nn} is stuck: {'; '.join(_stuck(row) for row in x['stuck'])}. A run that did not write the change read"
        f" the attempts and judged that the contract is at fault, not the work: {found.get('reason', '')}",
        "", "The lines of the Done Contract it names:", found.get("evidence", ""), "",
        f"Amend the contract. Read the ticket's Why and the lines above, then edit the Done Contract in"
        f" {x['ticket_file']} (in {x['cwd']}) so that each Check: line tests what the Why asks for and no two lines"
        f" contradict each other. Change nothing but the ticket. Then run rail amend {nn} \"why the contract was"
        f" wrong\". The amend gives the ticket a fresh retry budget and a fresh cap, and the work goes on under the"
        f" new contract.",
    ])


def _render_stuck_split(x):
    nn, found = x["ticket"], x["diagnosis"]
    issue = (f" The engine then writes this ticket's issue ({x['external_id']}) into each of them, and the issue stays"
             f" open until the last of them merges.") if x.get("external_id") else ""
    return "\n".join([
        f"Ticket {nn} is stuck: {'; '.join(_stuck(row) for row in x['stuck'])}. A run that did not write the change read"
        f" the attempts and judged that the work is more than one ticket: {found.get('reason', '')}",
        "", "The parts it names:", found.get("evidence", ""), "",
        f"Split it. Write one ticket for each part, each with its own Done Contract and scope_paths, and `after` where"
        f" one part needs another. File each with"
        f" rail add FILE. Then drop this ticket and name the tickets that replace it: rail drop {nn} --reason"
        f" \"split: why\" --replaced-by A,B (their numbers).{issue} Nothing of this ticket's branch is kept, so a"
        f" part that needs its work says so in its own ticket.",
    ])


def _render_tool_down(x):
    """A step failed for the machine's own reason more than once in a row: more attempts would not mend it."""
    e, times = x["failed"], x["times"]
    if x.get("diagnosis"):
        found = x["diagnosis"]
        said = (f"it failed {times} times, and a run that did not write the change read the attempts and judged that"
                f" the machine or a tool is at fault, not the change: {found.get('reason', '')} The failure it names:"
                f" {found.get('evidence', '')}. A person mends that on this machine")
    elif e.get("tools_down"):
        said = (f"it failed {times} times in a row while a tool the project declares was out of reach"
                f" ({tools.down_said(e['tools_down'])}). No failure of these counted as an attempt, since it may not be"
                f" the change's. A person checks that the tool answers and that its credential is valid on this machine")
    else:
        said = (f"its command could not run {times} times in a row ({e.get('detail', '')}), so nothing was checked and"
                f" no attempt was counted. A person installs what it needs on this machine, and adds it to [commands]"
                f" provision so that every cloud machine and CI runner gets it")
    return (f"Ticket {x['ticket']} can't get past '{e.get('step')}' on this machine: {said}, then continues the ticket:"
            f" {x['wait']['accept']}." + _go(x))


def _render_stuck_review(x):
    if x["run"] == "triage":
        return (f"The triage run of ticket {x['ticket']} failed twice in a row with no answer: it timed out"
                f" (timeout_secs), its output was invalid, or the evidence it named was not where it said. A person"
                f" looks at why, for example a command that waits for input or a question the run can't answer from"
                f" what it is shown, then continues it: {x['wait']['accept']}." + _go(x))
    return (f"The review of ticket {x['ticket']} failed twice in a row with no verdict: it timed out (timeout_secs) or its"
            f" output was invalid. A person looks at why, for example a command that waits for input or a reviewer"
            f" that can't return review/v1, then continues it: {x['wait']['accept']}." + _go(x))


def _render_secret(x):
    found = x["finding"]
    where = (f"rule {found.get('rule')}, {found.get('file')} line {found.get('line')}, commit"
             f" {str(found.get('commit'))[:12]}" if found.get("file") else "the finding its .gitleaksignore line names")
    return (f"A triage run judged that the commits of ticket {x['ticket']} hold a real secret ({where}): {x['reason']}"
            f" The branch is pushed, so the secret counts as leaked. A person rotates it where it was issued, then"
            f" continues: {x['wait']['accept']}. The engine then starts the ticket's branch again from the base branch"
            f" under a new name and closes the old one, because the secret scan fails on the old commits for good; the"
            f" work is done again there." + _go(x))


def _render_merge_failed(x):
    return (f"The merge of {_pr(x)} was requested and hasn't landed. A person looks at the pull request, then"
            f" continues: {x['wait']['accept']}." + _go(x))


def _render_hold(x):
    return (f"A person holds ticket {x['ticket']} with the label rail:hold on {_pr(x)}. They continue it with the"
            f" label rail:go, or: {x['wait']['accept']} \"note\"")


def _render_sweep_tickets(x):
    return (f"The sweep ran: read {x['summary_file']} in {x['cwd']}. Open a ticket with rail add for each"
            f" finding that names something wrong: an input or a sequence that fails, or a doc that no longer"
            f" matches the code (set caused_by when a ticket caused it); a finding about style, naming or where a"
            f" test lives gets no ticket. Open one ticket \"make it a check: ...\" for"
            f" each kind of proposed check. Open one ticket for each pattern in the worker runs, for what would have"
            f" told the worker: a setup or provision command, a line in the project's part of AGENTS.md, or a guide's"
            f" text. Open one ticket for each flaky check, to make it deterministic, with the Check: line the summary"
            f" gives for it. Drop duplicates. Change no code here. Then run: rail advance {x['ticket']}")


def _render_setup_failed(x):
    return (f"setup failed in {x['cwd']}: {x['failed']['detail']}. Fix the cause, then run"
            f" rail next --ticket {x['ticket']} to run setup again.")


def _render_assumptions(x):
    rows = "\n".join(f"- {r}" for r in x["open_assumptions"])
    return (f"Ticket {x['ticket']} has open ASSUMED rows. Verify each one in the code or the docs before you implement,"
            f" then change \"ASSUMED:\" to \"VERIFIED:\" in {x['ticket_file']} and say how you checked."
            f" A row you can't verify is a choice, not a fact, and nobody is here to ask. Decide it: keep the reading"
            f" the ticket's `## Why` supports, change the row to `VERIFIED:` and start it with `decided, not checked:`,"
            f" then your reason and what it costs if you are wrong. On a PERSON ticket the person approved the contract"
            f" with these rows in it.\n{rows}\nWork in {x['cwd']}.")


def _render_conflict(x):
    return (f"{_pr(x)} conflicts with the base branch. Run: rail advance {x['ticket']}. It rebases; when the rebase stops,"
            f" resolve the conflict in {x['cwd']} and run it again.")


def _render_red_check(x):
    lines = [f"A required check failed on {_pr(x)}. Fix the cause in {x['cwd']}, then run: rail advance {x['ticket']}"]
    for check in x["checks"]:
        lines += ["", f"{check['name']}:", check["summary"] or "(no output; open the check on GitHub)"]
    return "\n".join(lines) + _findings(x, "Open review findings:") + _note(x)


def _render_split(x):
    nn, rest = x["ticket"], x["rest_branch"]
    return "\n".join([
        f"This change is {x['size']} lines, over [size] cap of {x['cap']}. A reviewer checks a change of that"
        " size badly, so see whether it splits into tickets that each stand alone.", "",
        "It splits when you can name a first part that is under the cap, meets at least one Check: of the Done Contract"
        " on its own, and leaves the code working. If you can:",
        f"1. Keep the first part on this ticket's branch, {x['branch']}. Move the rest to a branch of its own, so"
        f" nothing is lost: git branch {rest}, then take the rest out of {x['cwd']}."
        + (f" Push that branch (git push {x['remote']} {rest}): another session may work the later"
           " tickets." if x.get("remote") else ""),
        f"2. Narrow this ticket's contract to the first part: in {x['cwd']}, edit {x['ticket_file']} (the Done Contract,"
        f" and scope_paths if they shrink), then run rail amend {nn} \"why\". On an AUTO ticket the engine accepts the"
        " narrowed contract at once: no person approves it.",
        f"3. File one ticket for each remaining part with rail add: its own Check: lines, after = [\"{nn}\"] (or the"
        f" part before it), a line in ## Request saying it was split from ticket {nn}, and under ## Look at the branch"
        f" that holds its code, {rest}.",
        f"4. Run rail advance {nn}.", "",
        f"If it does not split (the parts would not work alone, or each Check: needs all of it), change nothing and run"
        f" rail advance {nn}: the ticket stays AUTO and goes on to review as it is.",
    ]) + _note(x)


def _render_step_failed(x):
    e, nn, output = x["failed"], x["ticket"], x.get("output") or ""
    end = f".\n{output}\n\n" if output else ". "
    if e.get("status") == "could_not_run":
        from . import sensors
        # A sensor that ended with an exit it doesn't declare crashed or is set up wrongly: no tool is missing.
        crashed = e.get("step") == "sensors" and "could not run (" not in (e.get("detail") or "")
        told = MISSING_HELP if not crashed else "" if sensors.HELP in output else sensors.HELP
        return (f"The last ship of ticket {nn} could not run '{e.get('step')}': {e.get('detail', '')}{end}"
                f"{told} Then run: rail advance {nn}".replace("\n\n Then", "\n\nThen")
                + (f"\n{NOT_COUNTED}" if e.get("counted") is False else "")
                ) + _findings(x, "Open review findings:") + _note(x)
    if e.get("tools_down"):
        return (f"The last ship of ticket {nn} failed at '{e.get('step')}': {e.get('detail', '')}{end}A tool the"
                f" project declares was out of reach ({tools.down_said(e['tools_down'])}). {tools.DOWN_HELP} Then run:"
                f" rail advance {nn}") + _findings(x, "Open review findings:") + _note(x)
    tried = "".join(f"\n{line}" for line in _tried_lines(x))
    advice = (f"\n\nConsult advised on this failure:\n## {x['advice'].removeprefix('## ')}" if x.get("advice") else "")
    if x.get("triage"):
        # Not tested with a model run: this wording. The answer is the journal's, so the cache's output is not shown.
        from . import triage
        return (f"Ticket {nn} shipped, and a triage answer stopped it ({e.get('detail', '')}).\n"
                f"{triage.stop_said(x['triage'])}\n\nNothing has changed since. Do that in {x['cwd']}, then run:"
                f" rail advance {nn}\n{tried_help(e.get('step'), x['ticket_file'])}{tried}".rstrip()) + advice \
            + _findings(x, "Open review findings:") + _note(x)
    return (f"The last ship of ticket {nn} failed at '{e.get('step')}': {e.get('detail', '')}{end}Nothing has changed"
            f" since. Fix the cause in {x['cwd']}, then run: rail advance {nn}\n"
            f"{tried_help(e.get('step'), x['ticket_file'])}{tried}".rstrip()) + advice \
        + _findings(x, "Open review findings:") + _note(x)


def _render_revert(x):
    """A revert ticket's work, where the engine couldn't leave it done."""
    r, nn = x["revert"], x["ticket"]
    if not r["sha"]:
        return (f"Ticket {nn} reverts ticket {r['ticket']}, and no commit on the base branch merged a ticket"
                f" {r['ticket']}: there is nothing to reverse. `reverts` names the id of a merged ticket. End this"
                f" one: rail drop {nn} --reason \"ticket {r['ticket']} was never merged\"")
    short = r["sha"][:12]
    head = f"Ticket {nn} reverts ticket {r['ticket']}: take its change (commit {short}) out again. Work in {x['cwd']}."
    if r["applies"] and not r["failed"]:
        from .revert import RESTORE
        return (f"{head}\nThe reverse of that change still applies as it is, and the worktree holds something else."
                f" Put the exact reverse in its place:\n  git restore --source={r['base'][:12]} --staged --worktree -- .\n"
                f"  {RESTORE.format(sha=short)}\nThen run: rail advance {nn}\nIf verify fails on it, later work depends"
                " on what that change removes: adapt the revert by hand, inside scope_paths, and run rail advance"
                f" {nn} again. A revert made by hand is accepted once verify has failed on the exact one."
                + _save_line(x) + _note(x))
    why = ("Verify failed on the exact reverse of that change: later work depends on what it removes." if r["failed"] else
           "The reverse of that change no longer applies, because later tickets changed the same lines.")
    return (f"{head}\n{why} Undo"
            f" by hand what ticket {r['ticket']} changed, and keep the later work: `git show {short}` shows the change."
            f" Change only paths inside scope_paths: {_join(x['scope_paths'])}.\nWhen the project holds without that"
            f" change, run: rail advance {nn}" + _save_line(x) + _findings(x, "Open review findings:") + _note(x))


def _render_implement(x):
    nn, decided = x["ticket"], x["decided"]
    lines = [
        f"Implement ticket {nn}: {x['title']}",
        f"Work in {x['cwd']}, on branch {x['branch']}. The ticket is {x['ticket_file']}.",
        "", "Why:", x["why"], "",
        *(["Decided when the ticket was written, and not checked. Keep to each one, or write in the ticket why it is"
           " wrong:", *[f"- {row}" for row in decided], ""] if decided else []),
        "Done Contract:", x["done_contract"]["text"], "",
    ]
    if x["base_green"]:
        lines += [f"Every Check: above already passed on the base branch before any work, so the contract can't tell done"
                  f" from not done. A new test in a file these checks already run does not change the contract. Add a Check:"
                  f" line that fails now and passes once the work is done, such as one that runs your new test by name: edit"
                  f" the Done Contract in {x['ticket_file']}, then run rail amend {nn} \"why\".", ""]
    again = x.get("restarted")
    if again and again.get("type") == "stuck":
        # Not tested with a model run: the wording of this paragraph.
        lines += [f"The engine started this ticket's branch again from the base branch. The attempts on the branch before"
                  f" it ({again.get('branch')}) kept failing, and a run that did not write them judged that they shared a"
                  f" mistake. What it names, and what to do instead: {again.get('note', '')}",
                  "None of that work is here. Do the ticket again, and not that way.", ""]
    elif again:
        lines += [f"The engine started this ticket's branch again from the base branch: the commits of the branch before"
                  f" it ({again.get('branch')}) held a secret"
                  + (f" ({again['rule']} in {again['file']})" if again.get("file") else "") +
                  ", and a person has rotated it. None of that work is here. Do it again, and write no credential into"
                  " any file: read it from the environment, and use a made-up value in tests and examples.", ""]
    lines += [
        f"Change only paths inside scope_paths: {_join(x['scope_paths'])}.",
    ]
    if x["out_of_scope"]:
        lines += ["Out of scope:", x["out_of_scope"]]
    migration = ("Migrations: expand, then contract. Write the down step and test the rollback. Set reversibility (such as"
                 " expand-contract) and rollback in the ticket's front matter.") if x["migration"] else ""
    for extra in (_size_line(x), migration):
        if extra:
            lines.append(extra)
    past = history.text(x["history"])
    for extra in (tools.lines(x["tools"]), _tried_lines(x), past):
        if extra:
            lines += ["", *extra]
    lines += [
        *([""] if _tried_lines(x) or past or x["tools"] else []),
        "Before you ship, write \"## Look at\" in the ticket: what a reader of this change should check. A problem you"
        " see outside this ticket is not yours to fix here: leave it, and write a line there that starts \"Noticed:\".",
        f"When the Done Contract holds, run: rail advance {nn}",
    ]
    return "\n".join(lines) + _save_line(x) + _findings(x, "Open review findings:") + _note(x)


def _render_answer(x):
    return (f"The review of ticket {x['ticket']} left findings open. When you fix one, rail advance {x['ticket']} ships"
            " the fix and reviews it again." + _findings(x, "Findings:") + _note(x))


def _render_merge_by_person(x):
    asked = "".join(f"\nThe reviewer found what a revert doesn't undo: {said}" for said in x["asked"])
    if x["remote"]:
        return f"Ticket {x['ticket']} ({x['tier']}) is ready: a person reviews and merges {_pr(x)}." + asked
    return (f"Ticket {x['ticket']} ({x['tier']}) is ready to merge. A person reviews branch {x['branch']} and approves the"
            f" merge: {x['wait']['accept']}. The engine then merges it." + asked)


def _render_waiting_person(x):
    """Several tickets wait for a person, and no agent has work: each wait's own brief, and what else rests."""
    resting = x.get("resting") or []
    return ("Tickets wait for a person:\n" + "\n".join(f"- {w['ticket']}: {w['brief']}" for w in x["waits"])
            + (("\nNothing for an agent on these now:\n" + "\n".join(resting)) if resting else ""))


def _render_init(x):
    """The init task: the project's commands, areas, kinds and rules, set up by the agent and confirmed by a person."""
    from .init import INIT_TASK, INIT_TASK_CLOUD
    return (INIT_TASK_CLOUD if x["cloud"] else INIT_TASK).format(base=x["base"], depth=x["depth"], tools=x["tools"],
                                                                 projects=x["projects"])


def _next_ticket(x):
    return f"rail next --ticket {x['ticket']}"


RENDER = {
    "STOPPED": _render_stopped, "REBASING": _render_rebasing, "BUDGET": _render_budget, "TICKET_LINT": _render_lint,
    "APPROVE_CONTRACT": _render_approve_contract, "AFTER_DROPPED": _render_after_dropped,
    "TOOL_MISSING": _render_tool_missing, "APPROVE_AMEND": _render_approve_amend, "RETRY_CAP": _render_capped,
    "TOOL_DOWN": _render_tool_down, "STUCK_REVIEW": _render_stuck_review, "SECRET_FOUND": _render_secret,
    "MERGE_FAILED": _render_merge_failed, "HOLD": _render_hold, "STUCK": _next_ticket,
    "STUCK_CONTRACT": _render_stuck_contract, "STUCK_SPLIT": _render_stuck_split,
    "SWEEP_TICKETS": _render_sweep_tickets, "SETUP_FAILED": _render_setup_failed,
    "VERIFY_ASSUMPTIONS": _render_assumptions, "CONFLICT": _render_conflict, "RED_CHECK": _render_red_check,
    "SPLIT": _render_split, "STEP_FAILED": _render_step_failed, "REVERT_SHIP": lambda x: f"rail advance {x['ticket']}",
    "REVERT": _render_revert, "IMPLEMENT": _render_implement, "ANSWER_FINDINGS": _render_answer,
    "MERGE_BY_PERSON": _render_merge_by_person, "WAITING_PERSON": _render_waiting_person, "INIT_TASK": _render_init,
}
ENDS = ("guide", "consult")  # text a brief ends with: a [guides] page for the situation, then what consult said just now


def adopted_line(nn, name, adopted):
    """What `rail adopt` says first: where the branch's work is now."""
    return f"Ticket {nn} holds the work of branch {adopted['branch']} ({adopted['head']}), on its own branch {name}."


def render(code, facts):
    """The brief of an answer, from its facts alone."""
    start = [adopted_line(facts["ticket"], facts["branch"], facts["adopted"])] if facts.get("adopted") else []
    return "\n\n".join([*start, RENDER[code](facts), *[facts[key] for key in ENDS if facts.get(key)]])


def end_with(code, action, key, text):
    """Put text at the end of an answer's brief: with facts, as the fact `key` of ENDS, so the brief is still what
    the facts render; without, on the brief itself."""
    if "facts" in action:
        action["facts"][key] = text
        action["brief"] = render(code, action["facts"])
    else:
        action["brief"] += "\n\n" + text


def _held(f):
    where = f" ({f.claimed['session_url']})" if f.claimed and f.claimed.get("session_url") else ""
    quiet, limit = f.quiet_minutes, f.project.config["claim"]["stale_minutes"]
    if f.taken_from_me:
        return (f"Ticket {f.id} was taken over by another session{where}. Stop work on it here: its branch has moved on"
                f" from this session's copy, and whatever isn't saved stays in {f.cwd} for you to look at. Take other"
                f" work with rail next.")
    return (f"Ticket {f.id} is another session's work{where}, quiet for {quiet if quiet is not None else '?'} min."
            f" After {limit} min with no move, rail next resumes it here. To take it over now: rail next --ticket {f.id}")


def _pr_of(f):
    return _pr({"pr": _pr_fact(f)})


def _merge_requested(f):
    sha, _, at = (f.merge_note or "").partition(" ")
    return sha == (f.pr or {}).get("head", {}).get("sha") and f.pr_open


def _merge_stale(f):
    import time
    sha, _, at = (f.merge_note or "").partition(" ")
    return _merge_requested(f) and at.isdigit() and time.time() - int(at) > MERGE_PATIENCE


ROWS = [
    # (code,               owner,   kind,          when,                                         brief, or the facts of it)
    ("MERGED",             "none",  "rest",        lambda f: f.state == "merged",
     lambda f: f"Ticket {f.id} is merged."),
    # A drop whose mark on the counter branch couldn't be written: everything stays until a later rail next writes it.
    ("DROP_PENDING",       "none",  "rest",        lambda f: f.state == "dropped" and f.drop_pending,
     lambda f: f"Ticket {f.id} is dropped, and its mark on the counter branch isn't written yet: the remote can't be"
               f" reached or refused the push. Its worktree, branches and pull request stay until a later rail next"
               f" writes the mark and finishes the drop."),
    ("DROPPED",            "none",  "rest",        lambda f: f.state == "dropped",
     lambda f: f"Ticket {f.id} was dropped."),
    # A person's brake, an open issue labelled rail:stop, comes before every row that sends anyone to the ticket.
    ("STOPPED",            "person", "person_wait",  lambda f: f.stopped and f.state not in ("merged", "dropped"),
     _facts_stopped),
    # A rebase stopped in the ticket's worktree. Until it ends the engine writes nothing to the ticket: git moves
    # the branch when the rebase finishes. Another session's fresh work is still left alone (CLAIMED_ELSEWHERE).
    ("REBASING",           "agent", "agent_task",  lambda f: f.rebasing and f.state in OPEN and not (f.held and not f.explicit),
     _facts_rebasing),
    # A ticket whose runs cost more than [worker] ticket_usd since a person last acted stops in every state, before
    # any row that sends an agent to it. A person's answer comes first, so it can go on.
    ("GO",                 "agent", "script",      lambda f: f.over_budget and "rail:go" in f.labels
                                                   and f.state not in ("merged", "dropped"),
     lambda f: f"rail next --ticket {f.id}"),
    ("BUDGET",             "person", "person_wait",  lambda f: f.over_budget and f.state not in ("merged", "dropped"),
     _facts_budget),
    # One session writes a contract: four that start at once would each send a worker to write the same one.
    ("CONTRACT_ELSEWHERE", "none",  "rest",        lambda f: f.state == "new" and f.lint_errors and f.drafted_elsewhere
                                                   and not f.explicit,
     lambda f: f"Another session is writing the contract of ticket {f.id}. Leave it; rail next --ticket {f.id} takes it over"
               " when that session is gone."),
    ("TICKET_LINT",        "agent", "agent_task",  lambda f: f.state == "new" and f.lint_errors,
     _facts_lint),
    ("GO",                 "agent", "script",      lambda f: "rail:go" in f.labels and f.state not in ("merged", "dropped")
                                                   and not (f.state == "new" and f.lint_errors),
     lambda f: f"rail next --ticket {f.id}"),
    ("CONTRACT_MERGED",    "agent", "script",      lambda f: f.state == "new" and f.contract_merged,
     lambda f: f"rail next --ticket {f.id}"),
    # The engine accepts a contract that passes lint, on either tier, unless the project asks for a person's approval
    # of this kind of ticket before the build (approve_contract).
    ("ACCEPT_AUTO",        "agent", "script",      lambda f: f.state == "new" and not f.approve_first,
     lambda f: f"rail next --ticket {f.id}"),
    ("APPROVE_CONTRACT",   "person", "person_wait",  lambda f: f.state == "new",
     _facts_approve_contract),
    # No person is asked: whether the ticket stands without the dropped one is the contract writer's call, and
    # either answer is recorded and can be undone.
    ("AFTER_DROPPED",      "agent", "agent_task",  lambda f: f.state == "accepted" and f.after_dropped,
     _facts_after_dropped),
    ("WAITING_AFTER",      "none",  "rest",        lambda f: f.state == "accepted" and f.after_open,
     lambda f: f"Ticket {f.id} waits for ticket {_join(f.after_open)} to merge."),
    ("SCOPE_OVERLAP",      "none",  "rest",        lambda f: f.state == "accepted" and f.overlaps,
     lambda f: f"Ticket {f.id} can't be claimed while ticket {_join(f.overlaps)} changes the same paths."),
    ("TOOL_MISSING",       "person", "person_wait",  lambda f: f.state == "accepted" and f.tools_missing,
     _facts_tool_missing),
    ("CLAIM",              "agent", "script",      lambda f: f.state == "accepted",
     lambda f: f"rail next --ticket {f.id}"),
    ("APPROVE_AMEND",      "person", "person_wait",  lambda f: f.amend_pending,
     _facts_approve_amend),
    # A PERSON ticket at the retry cap waits for a person, once its one diagnosis is made and names nothing the
    # engine or the contract writer can do (the rows below STUCK).
    ("RETRY_CAP",          "person", "person_wait",  lambda f: f.state in OPEN and f.capped and not f.auto and _undiagnosed(f),
     _facts_capped),
    ("TOOL_DOWN",          "person", "person_wait",  lambda f: f.state in OPEN and f.machine_stuck,
     _facts_tool_down),
    ("STUCK_REVIEW",       "person", "person_wait",  lambda f: f.state == "reviewing" and f.stuck_review,
     _facts_stuck_review),
    # A triage run judged a line of .gitleaksignore to cover a real secret: a person rotates it.
    ("SECRET_FOUND",       "person", "person_wait",  lambda f: f.state in OPEN and f.triage_wait,
     _facts_secret),
    ("MERGE_FAILED",       "person", "person_wait",  lambda f: f.state == "merge-ready" and _merge_stale(f),
     _facts_person("MERGE_FAILED")),
    ("HOLD",               "person", "person_wait",  lambda f: "rail:hold" in f.labels,
     _facts_person("HOLD")),
    # A claim protects work in flight. The waits above show from any session, and a shipped ticket (in CI, ready to
    # merge) needs no claim: the rows below move it from whichever session looks.
    ("CLAIMED_ELSEWHERE",  "none",  "rest",        lambda f: f.held and not f.explicit,
     _held),
    # The branch starts again from the base, under a new name: the person has rotated the secret, or the diagnosis
    # of a stuck ticket judged that its attempts share a mistake.
    ("RESTART",            "agent", "script",      lambda f: f.state in OPEN and f.restart_due,
     lambda f: f"rail next --ticket {f.id}"),
    # An AUTO ticket at the retry cap: nothing merged, so nothing needs undoing, and the engine drops it with a
    # record instead of asking a person. A PERSON ticket waits (RETRY_CAP). Both come after the ticket's one
    # diagnosis, and only when that names nothing to do.
    ("STUCK",              "agent", "script",      lambda f: f.state in OPEN and f.capped and f.auto and _undiagnosed(f),
     _facts_stuck),
    ("RESUME",             "agent", "script",      lambda f: f.in_flight and (f.claimed_elsewhere or not f.worktree),
     lambda f: f"rail next --ticket {f.id}"),
    # A ticket at its retry cap gets one diagnosis before it is dropped or waits: rail next starts the run, which
    # did not write the change (rail docs retries). What its answer leads to: the contract writer amends the
    # contract or splits the ticket (the two rows below), the branch starts again (RESTART), the machine is a
    # person's to mend (TOOL_DOWN), or nothing, and the ticket is dropped or waits as before.
    ("DIAGNOSE",           "agent", "script",      lambda f: f.state in OPEN and f.diagnose_due,
     lambda f: f"rail next --ticket {f.id}"),
    ("STUCK_CONTRACT",     "agent", "agent_task",  lambda f: f.state in OPEN and f.diagnosed == "contract",
     _facts_stuck_contract),
    ("STUCK_SPLIT",        "agent", "agent_task",  lambda f: f.state in OPEN and f.diagnosed == "too-large",
     _facts_stuck_split),
    ("CONSULT",            "agent", "script",      lambda f: f.state in OPEN and f.consult_due,
     lambda f: f"rail next --ticket {f.id}"),
    ("SWEEP_RUN",          "agent", "script",      lambda f: f.state == "implementing" and f.sweep and not f.sweep_done,
     lambda f: "rail sweep"),
    # A sweep that found nothing has no task for the agent: it ships and merges, which moves the Sweep: marker.
    ("SWEEP_EMPTY",        "agent", "script",      lambda f: f.state == "implementing" and f.sweep and f.sweep_empty
                                                   and not f.dirty and not f.last_fail,
     lambda f: f"rail advance {f.id}"),
    ("SWEEP_TICKETS",      "agent", "agent_task",  lambda f: f.state == "implementing" and f.sweep and not f.dirty
                                                   and not f.last_fail,
     _facts_sweep_tickets),
    # The ticket that asks about the folders inside no project has no task for the agent either: its ship raises
    # the questions, and the triage step answers them.
    ("ASK_COVERAGE",       "agent", "script",      lambda f: f.state == "implementing" and f.asks_coverage
                                                   and not f.dirty and not f.last_fail,
     lambda f: f"rail advance {f.id}"),
    ("SETUP_FAILED",       "agent", "agent_task",  lambda f: f.state == "implementing" and f.setup_failed,
     _facts_setup_failed),
    ("VERIFY_ASSUMPTIONS", "agent", "agent_task",  lambda f: f.state == "implementing" and f.open_assumptions,
     _facts_assumptions),
    ("RED_BASE",           "none",  "rest",        lambda f: f.state == "implementing" and f.red_base and f.last_fail
                                                   and ((f.last_fail.get("step") or "").split(":")[0] == "verify"
                                                        or f.last_fail.get("step") == "product") and not f.dirty,
     lambda f: (f"the product does not start on the base branch either, so ticket {f.id} waits: a fix ticket for the"
                f" base comes first." if f.last_fail.get("step") == "product" else
                f"verify fails on the base branch too, so ticket {f.id} waits: a fix ticket for the base comes first.")),
    ("CONFLICT",           "agent", "agent_task",  lambda f: f.state == "implementing" and f.conflict and not f.dirty,
     _facts_conflict),
    ("RED_CHECK",          "agent", "agent_task",  lambda f: f.state == "implementing" and f.ci == "red" and not f.dirty,
     _facts_red_check),
    ("SPLIT",              "agent", "agent_task",  lambda f: f.state == "implementing" and f.split and not f.dirty,
     _facts_split),
    ("STEP_FAILED",        "agent", "agent_task",  lambda f: f.state == "implementing" and f.last_fail and not f.dirty,
     _facts_step_failed),
    # A revert ticket: the engine put the reverse into the worktree at the claim, so the ship is all that is left;
    # where it couldn't, an agent undoes the change by hand.
    ("REVERT_SHIP",        "agent", "script",      lambda f: f.state == "implementing" and f.revert and f.revert["exact"],
     _facts_revert_ship),
    ("REVERT",             "agent", "agent_task",  lambda f: f.state == "implementing" and f.revert,
     _facts_revert),
    ("IMPLEMENT",          "agent", "agent_task",  lambda f: f.state == "implementing",
     _facts_implement),
    # A question the engine raised about the shipped patch is answered before any review, so that no review is
    # spent on a patch that is about to change: rail advance starts the triage run.
    ("TRIAGE",             "agent", "script",      lambda f: f.state == "reviewing" and f.open_questions,
     lambda f: f"rail advance {f.id}"),
    ("ANSWER_FINDINGS",    "agent", "agent_task",  lambda f: f.state == "reviewing" and f.ledger.unanswered(),
     _facts_answer),
    ("REVIEW",             "agent", "script",      lambda f: f.state == "reviewing",
     lambda f: f"rail advance {f.id}"),
    ("FORGE_UNAVAILABLE",  "none",  "rest",        lambda f: f.state == "in-ci" and not f.forge,
     lambda f: f"Ticket {f.id} shipped. The forge can't be reached (no GitHub remote, offline, or gh not logged in),"
               f" so CI and the merge wait; rail doctor says which."),
    ("REBASE_BEHIND",      "agent", "script",      lambda f: f.state == "in-ci" and f.behind,
     lambda f: f"rail next --ticket {f.id}"),
    ("CI_WAIT",            "none",  "rest",        lambda f: f.state == "in-ci",
     lambda f: f"Ticket {f.id} shipped; CI runs on {_pr_of(f)}." if f.pushed else
               # Not tested with a model run: the sentence for a ticket that has no pull request.
               f"Ticket {f.id} shipped and has no open pull request: run rail next --ticket {f.id}, which opens one."
               if not f.pr_open else
               f"Ticket {f.id} shipped; its branch isn't pushed to {_pr_of(f)} yet: run rail advance {f.id}. If that answer"
               " has a `push` step that failed, the remote refuses the push: do what the step says, and don't run"
               " rail advance again until the two branches agree."),
    ("MERGE_REQUESTED",    "none",  "rest",        lambda f: f.state == "merge-ready" and _merge_requested(f),
     lambda f: f"The merge of {_pr_of(f)} is requested; rail next sees it on the base branch once GitHub lands it."),
    ("MERGE",              "agent", "script",      lambda f: f.state == "merge-ready" and (f.auto or f.merge_approved)
                                                   and not (f.project.remote and not f.auto),
     lambda f: f"rail advance {f.id}"),  # it merges, and removes the worktree: run it from the project's root
    ("MERGE_BY_PERSON",    "person", "person_wait",  lambda f: f.state == "merge-ready",
     _facts_merge_by_person),
]


def _undiagnosed(f):
    """A ticket at its cap whose diagnosis leaves it where it was: made and `cannot-tell`, not to be had (two runs
    gave no answer, or no command runs one), or made for an earlier cap."""
    return not f.diagnose_due and f.diagnosed in (None, "cannot-tell")


def first_match(f):
    """(code, owner, action) for the first row that matches. A row gives its brief as text, or the facts its code's
    renderer writes the brief from: those go into the action as `facts`."""
    for code, owner, kind, when, made in ROWS:
        if when(f):
            found = made(f)
            action = {"kind": kind, "brief": found if isinstance(found, str) else render(code, found)}
            if kind == "script":
                action["command"] = action["brief"]
            if not isinstance(found, str):
                action["facts"] = found
            return code, owner, action
    raise AssertionError(f"no row matches ticket {f.id} in state {f.state}")
