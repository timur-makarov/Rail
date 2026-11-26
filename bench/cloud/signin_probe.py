#!/usr/bin/env python3
"""Find which variables a child `claude -p` needs to sign in when its environment is scrubbed and its HOME is new, as
the bench gives every child (bench/driver.py child_env). It prints variable NAMES only, never a value; for a variable
that names a file it says only whether the file exists and can be read.

  signin_probe.py [--model claude-haiku-5-5] [--write-config PATH]

Steps: (1) the bench's pass_env as configured; (2) if that fails, pass_env plus every CLAUDE_* and ANTHROPIC_*
variable of this session (messaging, session-id and forge variables left out), then remove them one at a time while
the child still signs in; (3) the set found, again through a bench cost proxy (ANTHROPIC_BASE_URL pointing at it).
With --write-config, writes a copy of bench/config.toml whose pass_env is the set found, for BENCH_CONFIG.
Exit 0 when a set signs in both ways, 1 otherwise."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from bench import proxy  # noqa: E402
from bench.common import BENCH, settings  # noqa: E402

LEAVE_OUT = re.compile(r"MESSAGING|SESSION_ID|REMOTE_SESSION|GH_|GITHUB|CLOUDSDK|AWS|_SOCKET", re.I)
PLAIN = ["PATH", "LANG", "LC_ALL", "TERM", "TZ", "USER", "LOGNAME", "SHELL"]


def try_names(names, model, base_url=None):
    """Whether a child with only `names` (and a fresh HOME and TMPDIR) answers. Returns (ok, why)."""
    with tempfile.TemporaryDirectory(prefix="signin-") as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(os.path.join(home, "tmp"))
        env = {k: os.environ[k] for k in set(PLAIN) | set(names) if k in os.environ}
        env.update(HOME=home, TMPDIR=os.path.join(home, "tmp"))
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url
        try:
            done = subprocess.run(["claude", "-p", "--model", model, "--output-format", "json", "--tools", "Read"],
                                  input="Reply with the single word ok.", capture_output=True, text=True, env=env,
                                  cwd=tmp, timeout=180)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        try:
            data = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return False, f"exit {done.returncode}, no JSON (stderr: {redact(done.stderr)[-200:]})"
        if data.get("is_error") or "ok" not in str(data.get("result", "")).lower():
            return False, f"exit {done.returncode}, subtype {data.get('subtype')}, error {redact(str(data.get('result')))[:200]}"
        return True, "answered"


def redact(text):
    """Drop anything that looks like a token from a message before it is printed."""
    return re.sub(r"[A-Za-z0-9_\-\.]{24,}", "<redacted>", text or "")


def describe(names):
    for name in sorted(names):
        value = os.environ.get(name)
        if value is None:
            print(f"  {name}: not set in this session")
        elif value.startswith("/"):
            print(f"  {name}: a path; file exists {os.path.exists(value)}, readable {os.access(value, os.R_OK)}")
        else:
            print(f"  {name}: set ({len(value)} characters)")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--write-config")
    a = p.parse_args(argv)
    conf = settings()
    configured = [n for n in conf["pass_env"] if n not in PLAIN]
    print("1. the bench's pass_env as configured; set in this session:")
    describe([n for n in configured if n in os.environ])
    ok, why = try_names(configured, a.model)
    print(f"   -> {'signs in' if ok else 'fails'} ({why})")
    found = [n for n in configured if n in os.environ]
    if not ok:
        extra = sorted(n for n in os.environ if re.match(r"^(CLAUDE|ANTHROPIC)", n) and not LEAVE_OUT.search(n)
                       and n not in configured)
        print("2. adding this session's CLAUDE_* and ANTHROPIC_* variables:", ", ".join(extra) or "none")
        names = found + extra
        ok, why = try_names(names, a.model)
        print(f"   -> {'signs in' if ok else 'fails'} ({why})")
        if not ok:
            print("No set of variables signs in: stop and report.")
            return 1
        for n in list(names):
            trial = [x for x in names if x != n]
            if try_names(trial, a.model)[0]:
                names = trial
                print(f"   {n}: not needed")
            else:
                print(f"   {n}: needed")
        found = names
    print("The set that signs in:")
    describe(found)
    server = proxy.Proxy("probe", os.path.join(tempfile.mkdtemp(prefix="signin-proxy-"), "proxy.jsonl"))
    try:
        ok_proxy, why = try_names(found, a.model, base_url=server.url)
    finally:
        server.close()
    print(f"3. the same through a bench cost proxy -> {'signs in' if ok_proxy else 'fails'} ({why})")
    if a.write_config:
        with open(os.path.join(BENCH, "config.toml")) as f:
            text = f.read()
        names = ["PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "USER", "LOGNAME", "SHELL"] + found
        line = "pass_env = [" + ", ".join(json.dumps(n) for n in names) + "]"
        text, n = re.subn(r"^pass_env = \[.*?\]", line, text, count=1, flags=re.S | re.M)
        if n != 1:
            print("could not find pass_env in bench/config.toml")
            return 1
        with open(a.write_config, "w") as f:
            f.write(text)
        print(f"wrote {a.write_config}: pass_env = the plain variables and {', '.join(found)}")
    return 0 if ok_proxy else 1


if __name__ == "__main__":
    sys.exit(main())
