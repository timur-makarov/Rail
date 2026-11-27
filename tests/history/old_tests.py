#!/usr/bin/env python3
"""Old tests against new code, on real history: what the `old-test` question would have met (rail docs triage).

For each repository below, every one of its last commits that edits, deletes or renames a test file its parent had
is run twice: with the commit's own tests, then with the parent's version of those files, as ship does for a
ticket. Green with the commit's tests and red with the parent's is the fact that raises `old-test`.

The results are in old-test.json beside this file. Each red result there was read by hand and sorted into one of
the question's three answers (`answer`, with `why`); a later run of this script keeps what was sorted. A commit has
no ticket, so its message stands for the contract: `contract` when the message asks for the change in behaviour,
`moved` when the behaviour is kept and the old test fails for another reason, `lost` when behaviour is lost that the
message does not ask for. `red_with_own_tests` counts the commits whose own tests fail on this machine, mostly old
commits under a toolchain newer than they are: nothing can be said about those.

    python3 tests/history/old_tests.py WORK_FOLDER [--repo NAME] [--jobs N]

WORK_FOLDER holds the clones and the TypeScript test runner; it is made when missing. The run needs the network,
python3, go, node and npm, and takes some minutes. No part of the test suite runs it.
"""

import argparse
import json
import os
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from rail.util import match_any  # noqa: E402

RESULTS = os.path.join(HERE, "old-test.json")
TIMEOUT = 600
# One repository for each language profile that has a small one with fast tests and few dependencies. `head` pins
# the history that was read, `commits` is how many first-parent commits back from it.
REPOS = [
    {"name": "more-itertools", "url": "https://github.com/more-itertools/more-itertools.git", "profile": "python",
     "head": "aa9977698a5e6ae15d3fdfac08a5fc5621c4e179", "commits": 400, "command": "python3 -m unittest discover -q"},
    {"name": "pflag", "url": "https://github.com/spf13/pflag.git", "profile": "go",
     "head": "7b3c6eb4194a1d06e9e0eec9c24860a9c0045ad2", "commits": 400, "command": "go test ./..."},
    {"name": "ufo", "url": "https://github.com/unjs/ufo.git", "profile": "typescript",
     "head": "f06c800d0c59f2a4a1b9ba65eb6cb61a84419be6", "commits": 300, "command": "{work}/node_modules/.bin/vitest run"},
]


def sh(args, cwd, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"{' '.join(args)} failed in {cwd}:\n{result.stderr}")
    return result.stdout


def run(command, cwd):
    """(green, the last lines of the output)."""
    try:
        result = subprocess.run(["bash", "-o", "pipefail", "-c", command], cwd=cwd, capture_output=True, text=True,
                                timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT}s"
    return result.returncode == 0, "\n".join((result.stdout + result.stderr).splitlines()[-40:])


def test_globs(profile):
    with open(os.path.join(ROOT, "profiles", profile, "profile.toml"), "rb") as f:
        return tomllib.load(f)["tests"]


def edited_tests(clone, parent, commit, globs):
    """[(status, the path the parent had)] for each test file of the parent that the commit edits, deletes or
    renames. A new test file is the commit's own and is left out."""
    found = []
    for row in sh(["git", "diff", "--name-status", "-M", parent, commit], clone).splitlines():
        status, *paths = row.split("\t")
        if status[0] in "MDR" and match_any(globs, paths[0]):
            found.append((status[0], paths[0]))
    return found


def one(repo, command, globs, folder, commit):
    """One commit in one checkout: None when it edits no test file its parent had, else its row."""
    parents = sh(["git", "rev-list", "--parents", "-n", "1", commit], folder).split()[1:]
    if not parents:
        return None
    files = edited_tests(folder, parents[0], commit, globs)
    if not files:
        return None
    sh(["git", "checkout", "--quiet", "--force", "--detach", commit], folder)
    sh(["git", "clean", "-fdq"], folder)
    row = {"commit": commit[:12], "subject": sh(["git", "log", "-1", "--format=%s", commit], folder).strip(),
           "files": [f"{status} {path}" for status, path in files]}
    green, output = run(command, folder)
    if not green:
        # Red with its own tests: not the fact the question is about. Old commits also fail for the machine's
        # reasons, such as a toolchain newer than the code.
        row["result"] = "red with its own tests"
    else:
        sh(["git", "checkout", parents[0], "--", *[path for _, path in files]], folder)
        green, output = run(command, folder)
        row["result"] = "green" if green else "red"
        if not green:
            # The checkout's own path says nothing and differs on every machine: the repository's name stands in.
            row["output"] = output.replace(folder + os.sep, repo["name"] + "/")
        sh(["git", "reset", "--quiet", "--hard", commit], folder)
        sh(["git", "clean", "-fdq"], folder)
    print(f"{repo['name']} {row['commit']} {row['result']}", flush=True)
    return row


def read(repo, work, jobs):
    clone = os.path.join(work, repo["name"])
    if not os.path.isdir(clone):
        sh(["git", "clone", "--quiet", repo["url"], clone], work)
    command = repo["command"].format(work=work)
    globs = test_globs(repo["profile"])
    commits = sh(["git", "rev-list", "--first-parent", "-n", str(repo["commits"]), repo["head"]], clone).split()
    # One checkout for each job, each taking every jobs-th commit.
    folders = []
    for n in range(jobs):
        folder = f"{clone}-job{n}"
        if not os.path.isdir(folder):
            sh(["git", "worktree", "add", "--quiet", "--detach", folder, repo["head"]], clone)
        folders.append(folder)

    def share(n):
        return [one(repo, command, globs, folders[n], commit) for commit in commits[n::jobs]]

    with ThreadPoolExecutor(jobs) as pool:
        done = list(pool.map(share, range(jobs)))
    order = {commit[:12]: n for n, commit in enumerate(commits)}
    rows = sorted((row for part in done for row in part if row), key=lambda row: order[row["commit"]])
    return {"url": repo["url"], "head": repo["head"], "profile": repo["profile"], "command": repo["command"],
            "commits_read": len(commits), "edit_tests": len(rows),
            "green": sum(r["result"] == "green" for r in rows), "red": sum(r["result"] == "red" for r in rows),
            "red_with_own_tests": sum(r["result"] == "red with its own tests" for r in rows),
            "results": [r for r in rows if r["result"] == "red"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("work")
    parser.add_argument("--repo", action="append", help="only this repository; may be given more than once")
    parser.add_argument("--jobs", type=int, default=4, help="checkouts of each repository to run at once")
    args = parser.parse_args()
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    if not os.path.isdir(os.path.join(work, "node_modules", "vitest")):
        with open(os.path.join(work, "package.json"), "w") as f:
            f.write('{"name": "history-tools", "private": true}\n')
        sh(["npm", "install", "--no-audit", "--no-fund", "vitest@3", "typescript"], work)
    held = {}
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            held = json.load(f)
    for repo in REPOS:
        if args.repo and repo["name"] not in args.repo:
            continue
        sorted_by_hand = {r["commit"]: r for r in (held.get(repo["name"]) or {}).get("results", []) if r.get("answer")}
        found = read(repo, work, args.jobs)
        for row in found["results"]:
            row.update({key: sorted_by_hand[row["commit"]][key] for key in ("answer", "why")
                        if row["commit"] in sorted_by_hand and key in sorted_by_hand[row["commit"]]})
        sorted_rows = [row["answer"] for row in found["results"] if row.get("answer")]
        found["answers"] = {answer: sorted_rows.count(answer) for answer in sorted(set(sorted_rows))}
        held[repo["name"]] = found
        with open(RESULTS, "w") as f:
            json.dump(held, f, indent=1)
            f.write("\n")


if __name__ == "__main__":
    main()
