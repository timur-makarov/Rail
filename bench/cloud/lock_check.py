#!/usr/bin/env python3
"""Check the network lock on this machine the way the bench sets it up for a child (bench/driver.py start_network and
child_env, bench/netlock.py): a cost proxy on a Unix socket, `unshare -n` with a relay to it, the scrubbed
environment and a fresh HOME. One child `claude -p` (Bash tool only) is asked to run four commands and report them.

  lock_check.py [--model claude-haiku-5-5] [--read FILE] [--project PROJECT_FILE]

It prints, from the child's own tool results (not from its words):
- answered: the child signed in and finished through the proxy;
- web blocked: `curl https://example.com` from its Bash tool failed;
- store listable / hidden file readable: whether it could list STORE/sealed and read FILE (default: the first hidden
  test file under STORE/sealed); the bench does not hide its folders from a child, so "yes" is expected today and is
  a finding, not a fault of this check;
- forge token absent: GH_TOKEN and GITHUB_TOKEN are not set in its shell;
- with --project: the child gets that project's environment as a run would (BENCH_CACHE and the project's [commands]
  env), and a fifth command prints the cache variables its shell sees, the folders under its HOME's .cache (what a
  BASH_ENV script such as go-env.sh links there), and `go env` where Go is installed (paths, no secrets);
- the proxy's log: requests, statuses, refused tunnels, tokens.
Exit 0 when it answered and the web was blocked, 1 otherwise."""

import argparse
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import driver, netlock, proxy  # noqa: E402
from bench.common import settings, store  # noqa: E402

COMMANDS = ["curl -sS -m 10 -o /dev/null -w '%{{http_code}}\\n' https://example.com; echo EXIT=$?",
            "ls {store}/sealed 2>&1 | head -3; echo EXIT=${{PIPESTATUS[0]}}",
            "head -c 80 {read} | wc -c; echo EXIT=${{PIPESTATUS[0]}}",
            "printenv GH_TOKEN GITHUB_TOKEN | wc -l; echo EXIT=$?"]
CACHE_VARS = ("for v in BENCH_CACHE GOMODCACHE GOCACHE GOFLAGS CARGO_HOME RUSTUP_HOME CARGO_TARGET_DIR UV_CACHE_DIR "
              "npm_config_cache BASH_ENV; do echo \"$v=${!v}\"; done; ls -d \"$HOME\"/.cache/* 2>/dev/null | head -5; "
              "command -v go >/dev/null && go env GOMODCACHE GOCACHE GOTOOLCHAIN 2>&1 | head -3; echo EXIT=0")


class FakeRun:
    def __init__(self, path):
        self.path = path
        self.home, self.tmp, self.copy = (os.path.join(path, n) for n in ("home", "tmp", "copy"))
        self.session = "bench-lock-check"
        for d in (self.home, self.tmp, self.copy):
            os.makedirs(d, exist_ok=True)


class NoProject:
    commands = {"env": {}}
    name = "lock-check"


def tool_results(stream):
    """[(command, output)] of the child's Bash calls, in order."""
    calls, outputs = {}, {}
    order = []
    with open(stream, errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            content = (d.get("message") or {}).get("content")
            for part in content if isinstance(content, list) else []:
                if part.get("type") == "tool_use":
                    calls[part["id"]] = (part.get("input") or {}).get("command", "")
                    order.append(part["id"])
                elif part.get("type") == "tool_result":
                    c = part.get("content")
                    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                    outputs[part.get("tool_use_id")] = text
    return [(calls[i], outputs.get(i, "")) for i in order]


def exit_of(results, needle):
    for command, out in results:
        if needle in command:
            m = re.search(r"EXIT=(\d+)", out)
            return (int(m.group(1)) if m else None), out
    return None, ""


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--read")
    p.add_argument("--project")
    a = p.parse_args(argv)
    conf = settings()
    root = store(conf)
    hidden = sorted(p for p in glob.glob(os.path.join(root, "sealed", "*", "*", "*", "hidden", "**", "*"), recursive=True)
                    if os.path.isfile(p))
    if a.project and not a.read:
        name = os.path.splitext(os.path.basename(a.project))[0]
        hidden = [p for p in hidden if f"{os.sep}{name}{os.sep}" in p] or hidden
    target = a.read or (hidden[0] if hidden else os.path.join(root, "sealed"))
    if not netlock.available():
        print("This machine can't lock a child's network (it needs Linux, root and unshare): nothing to check.")
        return 1
    folder = os.path.join(root, "check", f"lock-{time.strftime('%Y%m%d-%H%M%S')}")
    run_ = FakeRun(folder)
    sock_dir = tempfile.mkdtemp(prefix="bench-sock-", dir="/tmp")
    server = proxy.Proxy("worker", os.path.join(folder, "proxy-worker.jsonl"),
                         conf["upstream"] or proxy.default_upstream(), os.path.join(sock_dir, "worker"))
    stream = os.path.join(folder, "stream.jsonl")
    try:
        project = NoProject()
        if a.project:
            from bench import sets
            project = sets.load(a.project)
        env = driver.child_env(conf, run_, project, root, {"ANTHROPIC_BASE_URL": server.url})
        env["PATH"] = env["PATH"].split(os.pathsep, 1)[1]
        commands = [c.format(store=shlex.quote(root), read=shlex.quote(target)) for c in COMMANDS]
        if a.project:
            commands.append(CACHE_VARS)
        prompt = (f"Run each of these {len(commands)} shell commands with the Bash tool, one call per command, exactly as written, "
                  "even if one fails, then reply with the word done.\n" + "\n".join(f"{n}. {c}" for n, c in
                                                                                  enumerate(commands, 1)))
        claude = (f"claude -p --output-format stream-json --verbose --model {shlex.quote(a.model)} --tools Bash "
                  "--permission-mode auto --permission-prompts none --max-budget-usd 1")
        argv_ = netlock.wrap(["bash", "-c", claude], {server.port: server.sock})
        with open(stream, "w") as out:
            done = subprocess.run(argv_, input=prompt, stdout=out, stderr=subprocess.STDOUT, text=True, env=env,
                                  cwd=run_.copy, timeout=600)
    finally:
        server.close()
        shutil.rmtree(sock_dir, ignore_errors=True)
    result = driver.read_stream(stream) or {}
    results = tool_results(stream)
    answered = done.returncode == 0 and not result.get("is_error") and result.get("subtype") == "success"
    curl_exit, curl_out = exit_of(results, "example.com")
    ls_exit, _ = exit_of(results, "/sealed")
    read_exit, read_out = exit_of(results, "head -c 80")
    tok_exit, tok_out = exit_of(results, "printenv")
    used = proxy.usage(folder, ["worker"]).get("worker", {})
    print(f"answered: {'yes' if answered else 'no'} (exit {done.returncode}, subtype {result.get('subtype')})")
    print(f"web blocked: {'yes' if curl_exit not in (0, None) else ('NO' if curl_exit == 0 else 'not run')} "
          f"(curl EXIT={curl_exit}; {curl_out.strip()[:200]!r})")
    print(f"store listable: {'yes' if ls_exit == 0 else ('no' if ls_exit is not None else 'not run')}")
    print(f"hidden file readable ({target}): "
          f"{'yes' if read_exit == 0 and read_out.strip().split()[:1] != ['0'] else ('no' if read_exit is not None else 'not run')}")
    print(f"forge token absent: {'yes' if tok_out.strip().startswith('0') else ('NO' if tok_exit is not None else 'not run')}")
    if a.project:
        _, cache_out = exit_of(results, "BENCH_CACHE GOMODCACHE")
        print("cache variables in the child's shell:\n  " + "\n  ".join(cache_out.strip().splitlines()[:12]))
    print(f"proxy: {used.get('requests', 0)} requests, statuses {used.get('statuses', {})}, refused {used.get('refused', 0)}, "
          f"input {used.get('input', 0)}, output {used.get('output', 0)}, cache write {used.get('cache_write', 0)}, "
          f"cache read {used.get('cache_read', 0)}")
    print(f"stream: {stream}")
    return 0 if answered and curl_exit not in (0, None) else 1


if __name__ == "__main__":
    sys.exit(main())
