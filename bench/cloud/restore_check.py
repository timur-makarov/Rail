#!/usr/bin/env python3
"""Check that restoring a saved stage gives the same tree as was saved: unpack the stage's pieces as they are (A), restore
the stage as `bench run --from` does (bench/runs.py restore: build folders put back from the sealed copy, worktrees
repaired, Rail's setup run in each worktree) into a new folder (B), and compare A and B: every ref, HEAD, the
worktrees, the tracked and untracked files of the root and of each worktree (ignored files left out, so build folders
do not count), and every file under .git/rail/.

  restore_check.py RUN STAGE        (RUN: a run's id or folder; STAGE: a stage's name, such as contract or work-1)

Prints SAME or the differences. Exit 0 when the same."""

import hashlib
import os
import sys
import tarfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import driver, runs, sets  # noqa: E402
from bench.common import git, settings, store  # noqa: E402


def state(copy):
    """What must match: refs, HEAD, worktrees, the tree of each checkout's files, and .git/rail/."""
    out = {"refs": git(["for-each-ref", "--format=%(refname) %(objectname)"], copy),
           "head": git(["rev-parse", "HEAD"], copy).strip()}
    roots = [copy] + runs.worktree_paths(copy)
    out["worktrees"] = sorted(os.path.relpath(w, copy) for w in roots[1:])
    for root in roots:
        index = tempfile.mktemp(prefix="restore-check-index-")
        env = dict(os.environ, GIT_INDEX_FILE=index)
        try:
            git(["read-tree", "HEAD"], root, env)
            git(["add", "-A"], root, env)
            out[f"tree {os.path.relpath(root, copy)}"] = git(["write-tree"], root, env).strip()
        finally:
            if os.path.exists(index):
                os.unlink(index)
    rail = os.path.join(copy, ".git", "rail")
    for base, _, files in os.walk(rail):
        for name in sorted(files):
            path = os.path.join(base, name)
            with open(path, "rb") as f:
                out[f"file {os.path.relpath(path, copy)}"] = hashlib.sha256(f.read()).hexdigest()[:16]
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    conf = settings()
    root = store(conf)
    run_arg, stage_name = argv
    source = runs.Run(run_arg if os.sep in run_arg else os.path.join(root, "runs", run_arg))
    meta = source.stage(stage_name)
    project = sets.load(source.project)
    situation = project.situation(source.situation)
    with tempfile.TemporaryDirectory(prefix="restore-check-", dir=os.path.join(root, "tmp")) as tmp:
        raw = os.path.join(tmp, "raw")
        os.makedirs(raw)
        with tarfile.open(fileobj=runs.Pieces(source.stages_dir, meta["pieces"]), mode="r|gz") as tar:
            tar.extractall(raw, filter="tar")
        a = os.path.join(raw, "copy")
        for wt in runs.worktree_paths(a):
            git(["worktree", "repair", wt], a, check=False)
        target = runs.Run(os.path.join(tmp, "restored"))
        os.makedirs(target.path)
        target.meta = {"session": source.session}  # child_env keys the session id on it, as the bench does
        env = driver.child_env(conf, target, project, root)
        runs.restore(source, meta, target, situation, root, env, project.build_dirs)
        sa, sb = state(a), state(target.copy)
    diffs = [k for k in sorted(set(sa) | set(sb)) if sa.get(k) != sb.get(k)]
    if not diffs:
        print(f"SAME: stage {stage_name} of {source.id} ({len(sa)} things compared)")
        return 0
    print(f"DIFFERENT: stage {stage_name} of {source.id}")
    for k in diffs:
        print(f"  {k}: saved {str(sa.get(k))[:200]!r} restored {str(sb.get(k))[:200]!r}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
