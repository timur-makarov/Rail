#!/usr/bin/env python3
"""Admit one situation and record it for the cloud admission step: `bench admit` (null, oracle, the touched packages,
Rail's setup and verify on the start commit, the request's links), then two checks the bench's admission does not make
but every agent run depends on, both with the network cut (`unshare -n`, Linux as root):

- offline tests: on a new copy with the fix applied and the hidden tests in place, the project's test_files command
  passes with no network and a fresh HOME, as an agent's own test run would;
- Rail in a worktree: Rail installed, a ticket-like worktree made with `git worktree add` under .claude/worktrees/,
  and Rail's setup then verify run there with no network and a fresh HOME, as Rail's claim and ship run them.

Where the network cannot be cut (not Linux, not root) the two checks run with it and say so.

  admit_one.py PROJECT_FILE ID OUTDIR [--skip-offline] [--prune-refused]

Writes OUTDIR/ID.json: {situation, project, admitted, reasons, bench (the admission record), offline, worktree,
seconds per part, sizes}. When bench admit admits it and a check above refuses it, the sealed folder's
admission.toml is rewritten as refused, with those reasons, so the report and choose.py see the overall verdict.
Exit 0 when admitted, 1 when refused, 2 on an error of the step itself."""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import admit, grade, netlock, rail_install, sealed, sets, tomlw  # noqa: E402
from bench.common import BenchError, git, run, settings, store, write  # noqa: E402

KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TERM", "TZ", "USER", "LOGNAME", "SHELL")


def du_mb(path):
    if not os.path.exists(path):
        return 0
    done = subprocess.run(["du", "-sm", path], capture_output=True, text=True)
    try:
        return int(done.stdout.split()[0])
    except (IndexError, ValueError):
        return -1


def agent_env(project, store_root, home, extra=None):
    """What an agent's shell has: a few plain variables, a fresh HOME and TMPDIR, the project's env and BENCH_CACHE."""
    env = {k: os.environ[k] for k in KEEP_ENV if k in os.environ}
    tmp = os.path.join(home, "tmp")
    os.makedirs(tmp, exist_ok=True)
    env.update(HOME=home, TMPDIR=tmp, GIT_CONFIG_NOSYSTEM="1")
    gitconfig = os.path.join(home, ".gitconfig")
    with open(gitconfig, "w") as f:
        f.write("[user]\n\tname = bench\n\temail = bench@localhost\n[init]\n\tdefaultBranch = main\n")
    env["GIT_CONFIG_GLOBAL"] = gitconfig
    env.update(sealed.project_env(project, store_root, base={}))
    env.update(extra or {})
    return env


def offline(command):
    """(the command with the network cut where this machine can, whether it is cut). Loopback is up, as in an
    agent's locked network (bench/netlock.py), so tests that bind 127.0.0.1 still can."""
    if netlock.available():
        return shlex.join(netlock.wrap(["bash", "-o", "pipefail", "-c", command], {})), True
    return command, False


def check_offline_tests(store_root, situation, tmp):
    project = situation.project
    root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
    with open(sealed.fix_diff(store_root, situation), "rb") as f:
        applied, why = grade.apply(root, f.read())
    if not applied:
        return {"passed": False, "why": f"the fix does not apply: {why[:300]}"}
    sealed.put_hidden(store_root, situation, root)
    env = agent_env(project, store_root, os.path.join(tmp, "home"))
    command, locked = offline(project.test_files_command(situation.hidden_tests))
    code, out = run(command, root, env, project.timeout)
    return {"passed": code == 0, "locked": locked, "exit": code, "tail": out[-1500:],
            "why": "" if code == 0 else ("timeout" if code is None else f"exit {code}") + " with the network cut"}


def check_worktree(store_root, situation, tmp):
    project = situation.project
    root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
    env = agent_env(project, store_root, os.path.join(tmp, "home"))
    rail_install.install(root, project, env=env)
    wt = os.path.join(root, ".claude", "worktrees", "01")
    git(["worktree", "add", "--quiet", "-b", "01-bench-check", wt, "main"], root, env)
    commands = project.rail_config.get("commands", {})
    out = {"locked": netlock.available()}
    for step in ("setup", "verify"):
        command = commands.get(step, "")
        limit = commands.get(f"{step}_timeout_secs") or commands.get("timeout_secs") or 900
        if not command:  # Rail runs no setup when it is empty; an empty verify is refused by bench admit already
            out[step] = {"passed": step == "setup", "why": "empty"}
            continue
        wrapped, _ = offline(command)
        began = time.time()
        code, text = run(wrapped, wt, dict(env, RAIL_TICKET="01", RAIL_BASE="refs/heads/main"), limit)
        out[step] = {"passed": code == 0, "exit": code, "seconds": round(time.time() - began, 1), "limit": limit,
                     "tail": text[-1500:]}
        if code != 0:
            break
    out["passed"] = all(out.get(s, {}).get("passed") for s in ("setup", "verify"))
    status = git(["status", "--porcelain"], wt, env, check=False)
    out["dirty_after"] = [line for line in status.splitlines() if line.strip()][:20]
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("project")
    p.add_argument("id")
    p.add_argument("outdir")
    p.add_argument("--skip-offline", action="store_true", help="only bench admit")
    p.add_argument("--prune-refused", action="store_true",
                   help="delete a refused situation's sealed folder to free disk (OUTDIR/ID.json keeps its record)")
    args = p.parse_args(argv)
    conf = settings()
    root = store(conf)
    project = sets.load(args.project)
    situation = project.situation(args.id)
    os.makedirs(args.outdir, exist_ok=True)
    record = {"situation": situation.id, "project": project.name, "set": project.set,
              "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seconds": {}}
    began = time.time()
    try:
        ok, reasons, bench_record = admit.admit(root, situation, conf, log=lambda m: print(m, flush=True))
    except BenchError as e:
        ok, reasons, bench_record = False, [f"bench: {e}"], {}
    record["seconds"]["bench_admit"] = round(time.time() - began, 1)
    record["bench"] = bench_record
    reasons = list(reasons)
    if ok and not args.skip_offline:
        for name, check in (("offline", check_offline_tests), ("worktree", check_worktree)):
            began = time.time()
            with tempfile.TemporaryDirectory(dir=grade.scratch(root)) as tmp:
                try:
                    result = check(root, situation, tmp)
                except BenchError as e:
                    result = {"passed": False, "why": str(e)[:1000]}
            record["seconds"][name] = round(time.time() - began, 1)
            record[name] = result
            if not result.get("passed"):
                if name == "offline":
                    reasons.append(f"offline: the hidden tests with the fix fail with the network cut: {result.get('why')}")
                else:
                    failed = next((s for s in ("setup", "verify") if not result.get(s, {}).get("passed")), "setup")
                    reasons.append(f"worktree: Rail's {failed} fails in a new worktree with the network cut "
                                   f"({result.get(failed, {}).get('exit', result.get('why'))})")
    record["admitted"] = not reasons
    record["reasons"] = reasons
    folder = sealed.folder(root, situation)
    if ok and reasons and os.path.isdir(folder):
        # bench admit wrote admission.toml as admitted; the report, choose.py and the later steps read it, so it must
        # carry the overall verdict: refused by the checks above.
        overall = dict(bench_record, admitted=False, reasons=list(bench_record.get("reasons") or []) + reasons,
                       refused_by="bench/cloud/admit_one.py")
        write(os.path.join(folder, "admission.toml"), tomlw.dumps(overall))
    record["sizes_mb"] = {"sealed": du_mb(folder), "cache": du_mb(sealed.cache_dir(root, project))}
    record["free_gb"] = round(shutil.disk_usage(root).free / 1e9, 2)
    if not record["admitted"] and args.prune_refused and os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)
        record["pruned"] = True
    record["ended"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = os.path.join(args.outdir, f"{situation.id}.json")
    with open(path + ".tmp", "w") as f:
        json.dump(record, f, indent=1, default=str)
    os.replace(path + ".tmp", path)
    print(f"{situation.id}: {'admitted' if record['admitted'] else 'refused'}")
    for r in reasons:
        print(f"  - {r}")
    return 0 if record["admitted"] else 1


if __name__ == "__main__":
    sys.exit(main())
