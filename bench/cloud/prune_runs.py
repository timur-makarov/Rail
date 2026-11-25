#!/usr/bin/env python3
"""Free the disk a finished run no longer needs. The bench keeps every run's working copy after its grade (bench/driver.py
deletes a run's copy only when the run starts again), and a Rust or TypeScript copy with its build folders and Rail's
worktrees is gigabytes, so a 30 GB machine fills after a few runs.

  prune_runs.py [--dry-run]

For every run under STORE/runs with a result.toml (graded, or to run again and set aside): deletes copy/ and tmp/.
Kept: run.toml, log.jsonl, streams/, stages/ (a restart with `bench run --from` and restore_check.py read only these),
home/ (the children's own session files, small), proxy logs, ended.toml, result.toml. A run without a result (running,
or cut off by a pause and still to be resumed) is not touched. Also deletes folders in STORE/tmp (grade and admission
scratch) older than six hours, which only a killed process leaves behind. Prints what it freed."""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.common import settings, store  # noqa: E402


def size_mb(path):
    done = subprocess.run(["du", "-sm", path], capture_output=True, text=True)
    try:
        return int(done.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    root = store(settings())
    freed, n = 0, 0
    for run_dir in sorted(glob.glob(os.path.join(root, "runs", "*"))):
        if not os.path.exists(os.path.join(run_dir, "result.toml")):
            continue
        for name in ("copy", "tmp"):
            path = os.path.join(run_dir, name)
            if os.path.isdir(path) and not os.path.islink(path):
                mb = size_mb(path)
                if not a.dry_run:
                    shutil.rmtree(path, ignore_errors=True)
                freed += mb
                n += 1
    old = time.time() - 6 * 3600
    for path in glob.glob(os.path.join(root, "tmp", "*")):
        try:
            if os.path.getmtime(path) < old:
                mb = size_mb(path)
                if not a.dry_run:
                    if os.path.isdir(path) and not os.path.islink(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.unlink(path)
                freed += mb
                n += 1
        except FileNotFoundError:
            continue
    free_gb = shutil.disk_usage(root).free / 1e9
    print(f"prune: {'would free' if a.dry_run else 'freed'} {freed} MB in {n} folders; free now {free_gb:.1f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
