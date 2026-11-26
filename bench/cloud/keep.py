#!/usr/bin/env python3
"""Keep results: copy files and folders into a clone of the results repository, cut every file over --piece-mb into
numbered parts (NAME.part000, NAME.part001, ...; `cat NAME.part* > NAME` joins them), commit, and push, so a lost
machine loses little. Build folders and the runs' working folders are left out.

  keep.py --repo DIR --branch NAME --dest PATH [--message TEXT] [--no-stages] SRC [SRC ...]

DIR is a clone whose `origin` the session can push to; PATH is the folder inside it (such as go/admission); each SRC
lands at PATH/<its name>. With --no-stages, a run's saved stages (stages/NN-NAME.tar.gz pieces: whole copies, often
hundreds of MB each) are left out and only stages/stages.jsonl is kept. Pushes are retried three times, with a rebase on the remote branch between tries.
Exit 0 when pushed (or nothing changed), 1 when the push failed."""

import argparse
import os
import shutil
import subprocess
import sys
import time

SKIP_DIRS = {"copy", "home", "tmp", "node_modules", "target", ".venv", "__pycache__", ".git", "mirrors", "cache",
             ".building", ".restoring"}
SKIP_SUFFIX = (".packing", ".tmp", ".lock")
MB = 1024 * 1024


def git(args, repo, check=True):
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {done.stderr.strip()[-800:]}")
    return done


def put_file(src, dest, piece):
    """Copy src to dest, or to dest.partNNN pieces when it is bigger than `piece` bytes. Skips an unchanged copy."""
    size = os.path.getsize(src)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if size <= piece:
        if os.path.exists(dest) and os.path.getsize(dest) == size and os.path.getmtime(dest) >= os.path.getmtime(src):
            return
        shutil.copy2(src, dest)
        return
    n = 0
    with open(src, "rb") as f:
        while True:
            chunk = f.read(piece)
            if not chunk:
                break
            with open(f"{dest}.part{n:03d}", "wb") as out:
                out.write(chunk)
            n += 1
    if os.path.exists(dest):
        os.unlink(dest)


def put(src, dest, piece, no_stages=False):
    if os.path.isfile(src):
        put_file(src, dest, piece)
        return
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith((".building", ".restoring"))]
        rel = os.path.relpath(base, src)
        for name in files:
            if name.endswith(SKIP_SUFFIX) or name == "lock":
                continue
            if no_stages and os.path.basename(base) == "stages" and name != "stages.jsonl":
                continue
            path = os.path.join(base, name)
            if os.path.islink(path):
                continue
            put_file(path, os.path.normpath(os.path.join(dest, rel, name)), piece)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--dest", required=True)
    p.add_argument("--message", default="")
    p.add_argument("--piece-mb", type=int, default=90)
    p.add_argument("--no-stages", action="store_true")
    p.add_argument("srcs", nargs="+")
    a = p.parse_args(argv)
    piece = a.piece_mb * MB
    for src in a.srcs:
        if not os.path.exists(src):
            print(f"keep: no {src}, skipped")
            continue
        put(os.path.abspath(src), os.path.join(a.repo, a.dest, os.path.basename(os.path.normpath(src))), piece,
            a.no_stages)
    git(["add", "-A", "--", a.dest], a.repo)
    if not git(["diff", "--cached", "--quiet"], a.repo, check=False).returncode:
        print("keep: nothing changed")
        return 0
    message = a.message or f"Results: {a.dest} at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    git(["-c", "user.name=rail-bench", "-c", "user.email=rail-bench@localhost", "commit", "--quiet", "-m", message],
        a.repo)
    for attempt in range(1, 4):
        done = git(["push", "--quiet", "origin", f"HEAD:refs/heads/{a.branch}"], a.repo, check=False)
        if done.returncode == 0:
            print(f"keep: pushed {a.dest} to {a.branch}")
            return 0
        print(f"keep: push {attempt} failed: {done.stderr.strip()[-400:]}")
        if git(["fetch", "--quiet", "origin", a.branch], a.repo, check=False).returncode == 0:
            git(["-c", "user.name=rail-bench", "-c", "user.email=rail-bench@localhost", "rebase", "--quiet",
                 f"origin/{a.branch}"], a.repo, check=False)
        time.sleep(10 * attempt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
