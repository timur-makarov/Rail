#!/usr/bin/env python3
"""A resumable job runner for a cloud session, whose machine pauses a few minutes after the session's turn ends and
kills every process (files stay; CLOUD-CHECK-RESULT.md, probe 6).

A job list is a text file, one job per line: ID, a tab, then a bash command. The runner starts the jobs not yet done,
N at a time, each in its own process group with its output in logs/ID.log, and appends one JSON line per finished job
to done.jsonl. A job that was running when the machine stopped has no line there, so the next `run` starts it again:
every job must be safe to start again (bench run and bench admit are).

  jobs.py start STATE JOBFILE [-j N]   start the runner in the background (setsid), unless one is running already
  jobs.py wait STATE [--minutes M]     block until every job is done, the runner is gone, or M minutes pass;
                                       print progress every 10 minutes. Exit 0: all done; 3: still running; 4: the
                                       runner is not running and jobs are left (start it again); 5: it stopped itself
  jobs.py status STATE                 one line per job state, and the totals
  jobs.py run STATE JOBFILE [-j N]     the runner itself, in the foreground (what start runs)
  jobs.py exec -- COMMAND ...          run one command in the foreground with the same scrubbed environment

Jobs run without the session's forge, cloud and messaging credentials (GH_TOKEN, GITHUB_TOKEN, *_ACCESS_TOKEN,
CLAUDE_CODE_MESSAGING_*, ...): the projects' setups and tests, and the graded code a model wrote, run unlocked, and
need none of them. Model children get their own, narrower environment from the bench (pass_env). Use `exec` for a
bench command run in the foreground.

The runner stops starting new jobs, and writes STATE/stopped with the reason, when STATE/STOP exists, when the free disk
of the store's file system is under --min-free-gb (default 3) or under 5% of its inodes, or when --stop-after-failures
jobs in a row fail (default 0: never). Jobs already running finish first. An empty job list is done at once."""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time


SCRUB = re.compile(r"^(GH_TOKEN|GITHUB_TOKEN|GH_ENTERPRISE_TOKEN|GITHUB_ENTERPRISE_TOKEN|GITHUB_PAT|GIT_ASKPASS"
                   r"|SSH_AUTH_SOCK|AWS_.*|AZURE_.*|GOOGLE_APPLICATION_CREDENTIALS|CLOUDSDK_.*|.*_ACCESS_TOKEN"
                   r"|CLAUDE_CODE_MESSAGING.*|NPM_TOKEN|NODE_AUTH_TOKEN|CARGO_REGISTRY_TOKEN)$")


def scrubbed_env():
    return {k: v for k, v in os.environ.items() if not SCRUB.match(k)}


def free_inodes_pct(path):
    st = os.statvfs(path)
    return 100.0 * st.f_favail / st.f_files if st.f_files else 100.0


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_jobs(path):
    jobs = []
    with open(path) as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "\t" not in line:
                raise SystemExit(f"{path}:{n}: ID, a tab, then the command")
            jid, command = line.split("\t", 1)
            jobs.append((jid.strip(), command))
    ids = [j for j, _ in jobs]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path}: an id is there twice")
    return jobs


def done_lines(state):
    path = os.path.join(state, "done.jsonl")
    out = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                out[d["id"]] = d
    return out


def free_gb(path):
    return round(shutil.disk_usage(path).free / 1e9, 2)


def alive(state):
    try:
        with open(os.path.join(state, "runner.pid")) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return None
    # the pid file may name a pid reused after a reboot: check the command line
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
            if b"jobs.py" not in cmdline or os.fsencode(state) not in cmdline:
                return None
    except OSError:
        pass  # no /proc (not Linux): trust kill(0)
    return pid


def run(args):
    state = os.path.abspath(args.state)
    os.makedirs(os.path.join(state, "logs"), exist_ok=True)
    with open(os.path.join(state, "runner.pid"), "w") as f:
        f.write(str(os.getpid()))
    for name in ("stopped", "finished"):
        if os.path.exists(os.path.join(state, name)):
            os.unlink(os.path.join(state, name))
    jobs = read_jobs(args.jobfile)
    shutil.copyfile(args.jobfile, os.path.join(state, "jobs.txt"))
    done = done_lines(state)
    todo = [(j, c) for j, c in jobs if j not in done or (args.retry_failed and done[j]["exit"] != 0)]
    running = {}  # id -> (proc, started, free before)
    failures_in_row = 0
    stop_reason = None
    disk_path = args.disk_path or state

    def finish(jid, proc, started, before):
        nonlocal failures_in_row
        code = proc.returncode
        line = {"id": jid, "exit": code, "seconds": round(time.time() - started, 1), "started": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)), "ended": now(), "free_gb_before": before,
                "free_gb_after": free_gb(disk_path)}
        with open(os.path.join(state, "done.jsonl"), "a") as f:
            f.write(json.dumps(line) + "\n")
        failures_in_row = failures_in_row + 1 if code != 0 else 0

    while todo or running:
        with open(os.path.join(state, "heartbeat"), "w") as f:
            f.write(f"{now()} running={sorted(running)} left={len(todo)}\n")
        for jid, (proc, started, before) in list(running.items()):
            if proc.poll() is not None:
                finish(jid, proc, started, before)
                del running[jid]
        if stop_reason is None:
            if os.path.exists(os.path.join(state, "STOP")):
                stop_reason = "STOP file"
            elif free_gb(disk_path) < args.min_free_gb:
                stop_reason = f"free disk {free_gb(disk_path)} GB is under {args.min_free_gb} GB"
            elif free_inodes_pct(disk_path) < 5:
                stop_reason = f"free inodes {free_inodes_pct(disk_path):.1f}% are under 5%"
            elif args.stop_after_failures and failures_in_row >= args.stop_after_failures:
                stop_reason = f"{failures_in_row} jobs in a row failed"
        if stop_reason is None:
            while todo and len(running) < args.jobs:
                jid, command = todo.pop(0)
                log = open(os.path.join(state, "logs", f"{jid}.log"), "a")
                log.write(f"\n=== {now()} start {jid}\n$ {command}\n")
                log.flush()
                proc = subprocess.Popen(["bash", "-o", "pipefail", "-c", command], stdout=log, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, start_new_session=True, env=scrubbed_env())
                log.close()
                running[jid] = (proc, time.time(), free_gb(disk_path))
        elif not running:
            break
        time.sleep(5)
    if stop_reason:
        with open(os.path.join(state, "stopped"), "w") as f:
            f.write(f"{now()} {stop_reason}; {len(todo)} jobs not started\n")
    else:
        with open(os.path.join(state, "finished"), "w") as f:
            f.write(now() + "\n")
    os.unlink(os.path.join(state, "runner.pid"))
    return 0


def start(args):
    state = os.path.abspath(args.state)
    os.makedirs(state, exist_ok=True)
    if not read_jobs(args.jobfile):
        shutil.copyfile(args.jobfile, os.path.join(state, "jobs.txt"))
        with open(os.path.join(state, "finished"), "w") as f:
            f.write(now() + " (no jobs)\n")
        print("nothing to run: the job list is empty")
        return 0
    pid = alive(state)
    if pid:
        print(f"the runner is already running (pid {pid})")
        return 0
    argv = [sys.executable, os.path.abspath(__file__), "run", state, os.path.abspath(args.jobfile), "-j", str(args.jobs),
            "--min-free-gb", str(args.min_free_gb), "--stop-after-failures", str(args.stop_after_failures)]
    if args.retry_failed:
        argv.append("--retry-failed")
    if args.disk_path:
        argv += ["--disk-path", args.disk_path]
    out = open(os.path.join(state, "runner.log"), "a")
    subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if alive(state):
            print(f"runner started: {state}")
            return 0
        time.sleep(0.1)
    print("the runner did not start; see runner.log")
    return 1


def summary(state):
    jobs = read_jobs(os.path.join(state, "jobs.txt")) if os.path.exists(os.path.join(state, "jobs.txt")) else []
    done = done_lines(state)
    ok = sum(1 for j, _ in jobs if j in done and done[j]["exit"] == 0)
    bad = [j for j, _ in jobs if j in done and done[j]["exit"] != 0]
    left = [j for j, _ in jobs if j not in done]
    return jobs, done, ok, bad, left


def status(args):
    state = os.path.abspath(args.state)
    jobs, done, ok, bad, left = summary(state)
    for j, _ in jobs:
        d = done.get(j)
        print(f"{j}\t" + (f"exit {d['exit']}\t{d['seconds']}s\tfree {d['free_gb_after']} GB" if d else "not done"))
    print(f"total {len(jobs)}: {ok} exit 0, {len(bad)} failed, {len(left)} left; runner "
          + ("running" if alive(state) else "not running"))
    for name in ("stopped", "finished"):
        p = os.path.join(state, name)
        if os.path.exists(p):
            print(f"{name}: {open(p).read().strip()}")
    return 0


def wait(args):
    state = os.path.abspath(args.state)
    deadline = time.time() + 60 * args.minutes
    last = 0
    while True:
        jobs, done, ok, bad, left = summary(state)
        running = alive(state)
        if time.time() - last >= 600 or not running:
            hb = open(os.path.join(state, "heartbeat")).read().strip() if os.path.exists(
                os.path.join(state, "heartbeat")) else ""
            print(f"{now()} {ok} ok, {len(bad)} failed, {len(left)} left of {len(jobs)}; {hb}", flush=True)
            last = time.time()
        if not running:
            if os.path.exists(os.path.join(state, "stopped")):
                print("stopped: " + open(os.path.join(state, "stopped")).read().strip())
                return 5
            if not left and (jobs or os.path.exists(os.path.join(state, "finished"))):
                print("all done")
                return 0
            print("the runner is not running and jobs are left: start it again")
            return 4
        if time.time() >= deadline:
            print("time is up; the runner is still running: wait again")
            return 3
        time.sleep(20)


def exec_(args):
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("jobs.py exec -- COMMAND ...")
    return subprocess.call(command, env=scrubbed_env())


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="verb", required=True)
    for verb in ("run", "start"):
        v = sub.add_parser(verb)
        v.add_argument("state")
        v.add_argument("jobfile")
        v.add_argument("-j", "--jobs", type=int, default=1)
        v.add_argument("--min-free-gb", type=float, default=3.0)
        v.add_argument("--stop-after-failures", type=int, default=0)
        v.add_argument("--retry-failed", action="store_true")
        v.add_argument("--disk-path", help="the folder whose file system's free space is watched (default: STATE)")
    w = sub.add_parser("wait")
    w.add_argument("state")
    w.add_argument("--minutes", type=float, default=110)
    s = sub.add_parser("status")
    s.add_argument("state")
    e = sub.add_parser("exec")
    e.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args(argv)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    return {"run": run, "start": start, "wait": wait, "status": status, "exec": exec_}[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
