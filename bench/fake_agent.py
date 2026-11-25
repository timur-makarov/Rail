#!/usr/bin/env python3
"""A deterministic stand-in for a coding agent, for the suite and `bench check-arm fake`. It prints JSON lines shaped
like `claude -p --output-format stream-json`, so the drivers read it as they read the real CLI.

It reads its plan from BENCH_FAKE_PLAN (a JSON file the bench writes into the run's folder):

  {"contract": {"tier": "AUTO", "scope": ["calc/**"], "check": "...", "why": "..."},
   "work": [ACTION, ...],      the Nth implementing run of the ticket (TICKET_LINT runs not counted) does work[N]
   "review": [REVIEW, ...],    the Nth review round answers review[N]; past the end, a clean review
   "plain": ACTION}            a plain arm's one run

An ACTION may hold: "patch" (a file `git apply` applies in the cwd), "write" {path: text}, "answer" [[finding,
outcome, reason]] (rail answer), "calls" [[tool, input]] (tool calls it prints, such as a planted leak), "sleep"
seconds, "say" (its last words; a plain run's default is "DONE"), "dump_env" (a file to write its environment to),
"error" ("rate_limit" ends the run as
the CLI does on a 429, "sign_in" as it does with no sign-in), "exit" (its exit code).

The plan index comes from the ticket's journal on its branch, so a run restarted from a saved stage does the same.

  fake_agent.py            a worker run of `rail work` (RAIL_TICKET set) or of a plain arm (--plain)
  fake_agent.py --review   a review run: prints review/v1 as `claude -p --output-format json` does
  fake_agent.py --consult  consult's advice, ending in a VERDICT line
"""

import json
import os
import subprocess
import sys
import time

SESSION = "fake-session"


def say(record):
    print(json.dumps(record), flush=True)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def journal(nn):
    """The ticket's events, as its branch holds them."""
    branches = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{nn}-*").stdout.split()
    if not branches:
        return []
    text = git("show", f"{branches[0]}:.rail/journal/{nn}-events.jsonl").stdout
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def plan():
    path = os.environ.get("BENCH_FAKE_PLAN")
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def calls_of(action):
    out = []
    for n, call in enumerate(action.get("calls") or []):
        tool, tool_input = call[0], call[1]
        out.append((f"toolu_{n}", tool, tool_input))
    return out


def act(action, nn=None):
    """Do an action in the cwd. Returns the tool calls to print."""
    done = calls_of(action)
    if action.get("patch"):
        result = subprocess.run(["git", "apply", "--whitespace=nowarn", action["patch"]], capture_output=True, text=True)
        done.append(("toolu_patch", "Bash", {"command": "git apply the change"}))
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
    for path, text in (action.get("write") or {}).items():
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        done.append((f"toolu_w{len(done)}", "Write", {"file_path": path}))
    for finding, outcome, reason in action.get("answer") or []:
        subprocess.run(["rail", "answer", nn, finding, outcome, reason, "--json"], capture_output=True, text=True)
        done.append((f"toolu_a{len(done)}", "Bash", {"command": f"rail answer {nn} {finding} {outcome}"}))
    if action.get("dump_env"):
        with open(action["dump_env"], "w") as f:
            json.dump(dict(os.environ), f)
    if action.get("sleep"):
        time.sleep(action["sleep"])
    return done


def stream(calls, action, default_say):
    say({"type": "system", "subtype": "init", "session_id": SESSION, "model": os.environ.get("RAIL_MODEL") or "fake"})
    for tool_id, tool, tool_input in calls:
        say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_id, "name": tool,
                                                             "input": tool_input}]}})
        say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok",
                                                        "is_error": False}]}})
    if action.get("error") == "rate_limit":
        say({"type": "result", "subtype": "error_during_execution", "is_error": True, "num_turns": 1,
             "session_id": SESSION, "total_cost_usd": 0.01, "api_error_status": 429,
             "result": "API Error: 429 rate_limit_error"})
        return 1
    if action.get("error") == "sign_in":  # as the CLI ends when it finds no sign-in
        say({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1, "session_id": SESSION,
             "total_cost_usd": 0, "result": "Not logged in · Please run /login"})
        return 1
    say({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2 + len(calls), "session_id": SESSION,
         "total_cost_usd": 0.05, "usage": {"input_tokens": 100, "output_tokens": 20},
         "result": action.get("say", default_say)})
    return action.get("exit", 0)


def contract(nn, spec):
    """Write the whole ticket from the stub and file it with rail amend."""
    branches = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{nn}-*").stdout.split()
    text = git("show", f"{branches[0]}:.rail/tickets/{nn}.md").stdout
    scope = ", ".join(json.dumps(s) for s in spec.get("scope", ["**"]))
    text = text.replace('tier = ""', f'tier = "{spec.get("tier", "AUTO")}"', 1)
    text = text.replace("scope_paths = []", f"scope_paths = [{scope}]", 1)
    text = text.replace("## Why\n", f"## Why\n{spec.get('why', 'The request asks for it.')}\n", 1)
    text = text.replace("## Done Contract\n", f"## Done Contract\n- Check: `{spec['check']}`\n", 1)
    path = os.path.join(os.environ.get("TMPDIR") or "/tmp", f"bench-ticket-{nn}.md")
    with open(path, "w") as f:
        f.write(text)
    done = subprocess.run(["rail", "amend", nn, "--file", path, "--json"], capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout + done.stderr, file=sys.stderr)
    return [("toolu_c", "Bash", {"command": f"rail amend {nn} --file {path}"})]


def review():
    p = plan()
    nn = os.environ.get("RAIL_TICKET", "")
    rounds = sum(1 for e in journal(nn) if e.get("event") == "step" and e.get("step") == "review")
    answers = p.get("review") or []
    response = answers[rounds] if rounds < len(answers) else {"summary": "Read the diff.", "findings": []}
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "", "total_cost_usd": 0.02,
                      "structured_output": response}))
    return 0


def main(argv):
    sys.stdin.read()  # the brief or the prompt; the plan decides
    if "--review" in argv:
        return review()
    if "--consult" in argv:
        print("Read the failing step's output and change the approach.\nVERDICT: change")
        return 0
    p = plan()
    if "--plain" in argv:
        action = p.get("plain") or {}
        return stream(act(action), action, "DONE")
    nn = os.environ.get("RAIL_TICKET", "")
    events = journal(nn)
    if events and not any(e.get("event") == "accepted" for e in events) and p.get("contract"):
        calls = contract(nn, p["contract"])
        return stream(calls, {}, "Wrote the contract.")
    n = sum(1 for e in events if e.get("event") == "worked" and e.get("code") != "TICKET_LINT")
    work = p.get("work") or []
    action = work[n] if n < len(work) else {}
    return stream(act(action, nn), action, "Done.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
