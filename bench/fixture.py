"""The fixture project, tests/bench_fixture: a tiny calculator with four situations, built into a git repository and a
project file. The suite and `bench check-arm` run on it.

- calc-01: add() subtracts. The trivial situation check-arm runs.
- calc-02: div() by zero should raise ValueError.
- calc-flaky: the hidden test fails on every fourth run, so the oracle refuses it.
- calc-null: the hidden test passes on the start commit already, so the null grade refuses it.
tests/test_legacy.py is red on the start commit and after every fix: the grade leaves it out."""

import os
import shutil

from .common import FRAMEWORK, commit_all, git

SOURCE = os.path.join(FRAMEWORK, "tests", "bench_fixture")
SET = "fixture"


def build(dest):
    """Build the repository at DEST/calc and the project file at DEST/fixture/calc.toml. Returns the project file."""
    dest = os.path.abspath(dest)
    repo = os.path.join(dest, "calc")
    os.makedirs(repo)
    shutil.copytree(os.path.join(SOURCE, "start"), repo, dirs_exist_ok=True)
    git(["init", "--quiet", "-b", "main"], repo)
    commit_all(repo, "calc")
    git(["tag", "start"], repo)
    counter = os.path.join(dest, "flaky-counter")
    for sid in sorted(os.listdir(os.path.join(SOURCE, "fixes"))):
        git(["checkout", "--quiet", "-B", f"fix/{sid}", "start"], repo)
        src = os.path.join(SOURCE, "fixes", sid)
        for base, _, names in os.walk(src):
            for name in names:
                rel = os.path.relpath(os.path.join(base, name), src)
                with open(os.path.join(base, name)) as f:
                    text = f.read().replace("@COUNTER@", counter)
                target = os.path.join(repo, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "w") as f:
                    f.write(text)
        commit_all(repo, f"Fix {sid}")
        git(["tag", f"{sid}-fix"], repo)
    git(["checkout", "--quiet", "main"], repo)
    with open(os.path.join(SOURCE, "PROJECT.toml.in")) as f:
        text = f.read().replace("@REPO@", repo)
    path = os.path.join(dest, SET, "calc.toml")
    os.makedirs(os.path.dirname(path))
    with open(path, "w") as f:
        f.write(text)
    return path
