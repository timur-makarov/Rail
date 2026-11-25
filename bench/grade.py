"""The grade of a change against a situation (PLAN section 5).

A change is right when, on a new copy of the sealed repository with the change applied and the hidden test files put
in place, every round passes: the hidden tests pass, and the tests of every package the change touches pass, leaving
out tests already red on the start commit. The arm's own test files that clash with the hidden ones are set aside
first. A change that passes some rounds and not others is wrong: it may have added a race.

A package's run passes when it exits 0, or when every failing test it names was red on the start commit too, or when
the start commit's run of it failed with no test named either (a package red as a whole at the start is left out).
"""

import json
import os
import shutil
import subprocess
import tempfile

from . import sealed
from .common import git, run, write

EXCLUDE = (".rail", ".claude")  # Rail's own files and Claude Code's: never part of a change


def diff(repo, base, head=None, exclude=EXCLUDE):
    """The change from commit `base` to commit `head`, or to the working tree of `repo` when `head` is None
    (untracked files included, ignored ones left out), as a binary patch."""
    specs = ["--", "."] + [f":(exclude){p}" for p in exclude]
    if head is None:
        index = tempfile.mktemp(prefix="bench-index-")
        env = dict(os.environ, GIT_INDEX_FILE=index)
        try:
            git(["read-tree", base], repo, env)
            git(["add", "-A"], repo, env)
            head = git(["write-tree"], repo, env).strip()
        finally:
            if os.path.exists(index):
                os.unlink(index)
    done = subprocess.run(["git", "-c", "core.quotePath=false", "diff", "--binary", "--no-color", "--no-renames", base,
                           head, *specs], cwd=repo, capture_output=True)
    return done.stdout


def changed_paths(patch):
    """The paths a patch touches."""
    paths = []
    for line in patch.decode(errors="replace").splitlines():
        if line.startswith("diff --git "):
            # diff --git a/PATH b/PATH, with --no-renames both are the same
            rest = line[len("diff --git "):]
            half = len(rest) // 2
            paths.append(rest[half + 1:][2:] if rest[half] == " " else rest.split(" b/", 1)[-1])
    return paths


def apply(root, patch):
    """Apply a patch to the working tree. Returns (applied, why not)."""
    if not patch.strip():
        return True, ""
    done = subprocess.run(["git", "apply", "--binary", "--whitespace=nowarn", "-"], cwd=root, input=patch,
                          capture_output=True)
    return done.returncode == 0, done.stderr.decode(errors="replace").strip()


def clashing(project, situation, paths):
    """The arm's changed test files that clash with the hidden ones: the same path, or with clash = "dir" (Go, where a
    folder is one package and two tests of one name don't compile) a test file in a hidden test's folder."""
    hidden = set(situation.hidden_tests)
    dirs = {os.path.dirname(p) for p in hidden}
    out = []
    for p in paths:
        if p in hidden:
            out.append(p)
        elif project.clash == "dir" and os.path.dirname(p) in dirs and project.is_test(p):
            out.append(p)
    return sorted(out)


def set_aside(root, paths, aside):
    for p in paths:
        src = os.path.join(root, p)
        if os.path.lexists(src):
            dest = os.path.join(aside, p)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)


def red_at_start(store_root, situation, package, env, timeout):
    """The start commit's run of one package's tests, hidden tests not in place: {exit, failing}. Kept in the sealed
    folder, so it runs once per package."""
    path = os.path.join(sealed.folder(store_root, situation), "red", package.replace("/", "%") + ".json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    project = situation.project
    with tempfile.TemporaryDirectory(dir=scratch(store_root)) as tmp:
        root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
        code, out = run(project.test_package_command(package), root, env, timeout)
    found = {"exit": code, "failing": project.failing(out), "output": out[-2000:]}
    write(path, json.dumps(found, indent=1))
    return found


def package_ok(project, code, out, red):
    """Whether one package's run passes, red tests on the start commit left out. Returns (passed, failing, why)."""
    if code == 0:
        return True, [], ""
    failing = project.failing(out)
    if failing:
        new = [t for t in failing if t not in red["failing"]]
        if not new:
            return True, failing, "only tests red on the start commit fail"
        return False, failing, "fails: " + ", ".join(new[:10])
    if red["exit"] != 0 and not red["failing"]:
        return True, [], "red as a whole on the start commit"
    return False, [], "timeout" if code is None else f"exit {code}, no failing test named"


def scratch(store_root):
    path = os.path.join(store_root, "tmp")
    os.makedirs(path, exist_ok=True)
    return path


def grade(store_root, situation, patch, rounds, hidden_runs=1, keep=None):
    """Grade a change (a binary patch from the start commit) against a situation. Each round runs the hidden tests
    `hidden_runs` times and every touched package once; the change is right only if every run of every round passes.
    Returns the grade as a dict."""
    project = situation.project
    env = sealed.project_env(project, store_root)
    timeout = project.timeout
    with tempfile.TemporaryDirectory(dir=scratch(store_root)) as tmp:
        root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
        applied, why = apply(root, patch)
        result = {"right": False, "applied": applied, "rounds": [], "aside": [], "packages": []}
        if not applied:
            result["why"] = f"the change does not apply: {why[:500]}"
            return result
        paths = changed_paths(patch)
        aside = clashing(project, situation, paths)
        set_aside(root, aside, os.path.join(tmp, "aside"))
        sealed.put_hidden(store_root, situation, root)
        hidden = set(situation.hidden_tests)
        packages = sorted({project.package_of(p, root) for p in paths if p not in hidden and p not in aside})
        result.update(aside=aside, packages=packages, changed=paths)
        reds = {p: red_at_start(store_root, situation, p, env, timeout) for p in packages}
        right = True
        for n in range(rounds):
            this = {"hidden": [], "packages": {}}
            for _ in range(hidden_runs):
                code, out = run(project.test_files_command(situation.hidden_tests), root, env, timeout)
                this["hidden"].append({"exit": code, "failing": project.failing(out), "tail": out[-1500:]})
                right = right and code == 0
            for p in packages:
                code, out = run(project.test_package_command(p), root, env, timeout)
                ok, failing, why = package_ok(project, code, out, reds[p])
                this["packages"][p] = {"passed": ok, "exit": code, "failing": failing, "why": why, "tail": out[-1500:]}
                right = right and ok
            result["rounds"].append(this)
        result["right"] = right
        result["why"] = "" if right else why_wrong(result)
        if keep:
            shutil.copytree(root, keep, symlinks=True)
        return result


def why_wrong(result):
    for n, r in enumerate(result["rounds"], 1):
        for h in r["hidden"]:
            if h["exit"] != 0:
                named = ", ".join(h["failing"][:5]) or ("timeout" if h["exit"] is None else f"exit {h['exit']}")
                return f"round {n}: hidden tests fail ({named})"
        for p, pr in r["packages"].items():
            if not pr["passed"]:
                return f"round {n}: package {p} {pr['why']}"
    return ""
