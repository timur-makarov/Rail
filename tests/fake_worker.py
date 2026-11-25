#!/usr/bin/env python3
"""A stand-in for the worker `rail work` starts (`claude -p --output-format stream-json`). Each run takes the next item
of a queue the test writes, logs its brief, cwd and environment, and prints JSON lines shaped like the CLI's stream.

Queue items (a dict, every key optional): "write" {path: text} writes files in its cwd; "run" [commands] runs shell
commands and logs their exit codes and output; "sleep" seconds; "calls" [[tool, input, outcome, text]] prints a
tool_use and its tool_result for each (outcome ok, failed or denied); "result" {...} merges into the result line, or
null prints none; "raw" text is printed as is; "exit" is the exit code; "resume_fails" fails as the CLI does when the
session to resume isn't on this machine, when RAIL_SESSION is set.
"""
import json
import os
import subprocess
import sys
import time

brief = sys.stdin.read()
queue_path = os.environ.get("RAIL_FAKE_WORKER")
item = {}
if queue_path and os.path.exists(queue_path):
    with open(queue_path) as f:
        queue = json.load(f)
    if queue:
        item = queue.pop(0)
        with open(queue_path, "w") as f:
            json.dump(queue, f)
entry = {"cwd": os.getcwd(), "brief": brief, "env": {k: os.environ.get(k) for k in (
    "RAIL_TICKET", "RAIL_MODEL", "RAIL_EFFORT", "RAIL_SESSION", "ANTHROPIC_MODEL", "RAIL_WORKER")}, "ran": []}
session = os.environ.get("RAIL_SESSION") or item.get("session") or f"session-{time.time_ns()}"


def say(record):
    print(json.dumps(record), flush=True)


def log():
    path = os.environ.get("RAIL_FAKE_WORKER_LOG")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")


if "raw" not in item:
    say({"type": "system", "subtype": "init", "session_id": session, "model": os.environ.get("RAIL_MODEL")})
if item.get("resume_fails") and os.environ.get("RAIL_SESSION"):
    log()
    say({"type": "result", "subtype": "error_during_execution", "is_error": True, "num_turns": 0,
         "session_id": session, "total_cost_usd": 0})
    print(f"No conversation found with session ID: {session}", file=sys.stderr)
    sys.exit(1)
for path, text in (item.get("write") or {}).items():
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
for command in item.get("run") or []:
    done = subprocess.run(command, shell=True, capture_output=True, text=True)
    entry["ran"].append({"command": command, "code": done.returncode, "output": done.stdout + done.stderr})
for n, (tool, tool_input, outcome, text) in enumerate(item.get("calls") or []):
    tool_id = f"toolu_{n}"
    say({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tool_id, "name": tool,
                                                         "input": tool_input}]}})
    if outcome == "denied":
        say({"type": "system", "subtype": "permission_denied", "tool_name": tool, "tool_use_id": tool_id,
             "decision_reason": text})
    say({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text,
                                                    "is_error": outcome != "ok"}]}})
if item.get("sleep"):
    time.sleep(item["sleep"])
log()
if "raw" in item:
    print(item["raw"])
elif item.get("result", {}) is not None:
    result = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "session_id": session,
              "total_cost_usd": 0.25, "result": "done"}
    result.update(item.get("result") or {})
    say(result)
sys.exit(item.get("exit", 0))
