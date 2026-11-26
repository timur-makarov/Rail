#!/usr/bin/env python3
"""Write a job list for jobs.py: one line per job, ID, a tab, the bash command, with absolute paths.

  joblist.py admit PROJECT_FILE OUTDIR [--id ID ...] [--skip-offline-after N] [--keep-refused]
      one `admit_one.py PROJECT_FILE ID OUTDIR --prune-refused` per situation, in the file's order; with
      --skip-offline-after N, the situations after the first N get --skip-offline (bench admit only); with
      --keep-refused, no --prune-refused (a smoke round keeps a refused situation's sealed copy to look into).
  joblist.py runs PROJECT_FILE --arm ARM --runs N [--id ID ...] [--admitted-from DIR] [--seed S]
      `bench run PROJECT_FILE --id ID --arm ARM --runs k` for k = 1..N, in rounds: every situation's run 1, then
      every run 2, and so on, so a stop part-way leaves whole rounds; the situations in a seeded shuffle (--seed,
      default 20261128) so that a stop does not favour the file's first ones. With --admitted-from, only the
      situations whose DIR/ID.json (admit_one.py's record) says admitted. Each job ends with prune_runs.py, so a
      graded run's working copy does not stay on the disk.

Every command starts by sourcing --env-file (default /srv/rail-bench/session.env) when that file exists, so a job
started again after a pause has the same environment. Prints the list; redirect it to a file."""

import argparse
import json
import os
import random
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from bench import sets  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    a_ = sub.add_parser("admit")
    a_.add_argument("project")
    a_.add_argument("outdir")
    a_.add_argument("--id", action="append")
    a_.add_argument("--skip-offline-after", type=int)
    a_.add_argument("--keep-refused", action="store_true")
    r_ = sub.add_parser("runs")
    r_.add_argument("project")
    r_.add_argument("--arm", required=True)
    r_.add_argument("--runs", type=int, default=3)
    r_.add_argument("--id", action="append")
    r_.add_argument("--admitted-from")
    r_.add_argument("--seed", type=int, default=20261128)
    for v in (a_, r_):
        v.add_argument("--env-file", default="/srv/rail-bench/session.env")
    a = p.parse_args(argv)
    path = os.path.abspath(a.project)
    project = sets.load(path)
    ids = [s.id for s in project.situations if not a.id or s.id in a.id]
    unknown = sorted(set(a.id or []) - set(ids))
    if unknown:
        raise SystemExit(f"{path}: no situation {', '.join(unknown)}")
    prefix = f". {shlex.quote(a.env_file)} && " if os.path.exists(a.env_file) else ""
    py = shlex.quote(sys.executable)
    q = shlex.quote
    if a.mode == "admit":
        outdir = os.path.abspath(a.outdir)
        for n, sid in enumerate(ids):
            skip = " --skip-offline" if a.skip_offline_after is not None and n >= a.skip_offline_after else ""
            prune = "" if a.keep_refused else " --prune-refused"
            print(f"{sid}\t{prefix}{py} {q(os.path.join(HERE, 'admit_one.py'))} {q(path)} {sid} {q(outdir)}"
                  f"{prune}{skip}")
        return 0
    if a.admitted_from:
        keep = []
        for sid in ids:
            record = os.path.join(a.admitted_from, f"{sid}.json")
            if os.path.exists(record):
                with open(record) as f:
                    if json.load(f).get("admitted"):
                        keep.append(sid)
        ids = keep
    random.Random(a.seed).shuffle(ids)
    bench = q(os.path.join(os.path.dirname(HERE), "bench"))
    prune = q(os.path.join(HERE, "prune_runs.py"))
    for k in range(1, a.runs + 1):
        for sid in ids:
            print(f"{sid}.{a.arm}.{k}\t{prefix}{py} {bench} run {q(path)} --id {sid} --arm {q(a.arm)} --runs {k}; "
                  f"rc=$?; {py} {prune} >/dev/null 2>&1; exit $rc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
