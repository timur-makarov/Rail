"""The sealed copy: a new repository holding one commit, the tree at the situation's start, with no remote and no other
ref, so the fix is nowhere in it. Its dependencies are fetched while it is built, so it builds offline. The hidden test
files and the fix are kept beside it, outside the copy.

store/sealed/SET/PROJECT/ID/
  copy/        the sealed repository, with what setup fetched (untracked)
  hidden/      the hidden test files, as the fix has them
  fix.diff     start..fix without the hidden test files: what the oracle grade applies
  meta.toml    start, fix, the copy's commit
"""

import io
import os
import shutil
import subprocess
import tarfile

from . import tomlw
from .common import BenchError, git, now_iso, run, write


def project_env(project, store_root, base=None):
    """The environment every project command runs with: the project's [commands] env, and BENCH_CACHE, a folder the
    project's commands may keep fetched dependencies in (CARGO_HOME, GOMODCACHE, a wheel folder)."""
    env = dict(os.environ if base is None else base)
    env["BENCH_CACHE"] = cache_dir(store_root, project)
    env.update(project.commands["env"])
    return env


def cache_dir(store_root, project):
    path = os.path.join(store_root, "cache", project.name)
    os.makedirs(path, exist_ok=True)
    return path


def mirror(store_root, project):
    """A mirror of the project's repository in the store, fetched when it is there already."""
    path = os.path.join(store_root, "mirrors", f"{project.name}.git")
    if os.path.isdir(path):
        git(["fetch", "--quiet", "--prune", "--tags", "origin", "+refs/*:refs/*"], path, check=False)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        git(["clone", "--quiet", "--mirror", project.repo, path], os.path.dirname(path))
    return path


def folder(store_root, situation):
    return os.path.join(store_root, "sealed", situation.key)


def resolve(repo, rev):
    sha = git(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], repo, check=False).strip()
    if not sha:
        raise BenchError(f"no commit '{rev}' in {repo}")
    return sha


def build(store_root, situation, log=print):
    """Build the sealed copy of a situation, once. Returns its folder."""
    project = situation.project
    dest = folder(store_root, situation)
    if os.path.exists(os.path.join(dest, "meta.toml")):
        return dest
    repo = mirror(store_root, project)
    start, fix = resolve(repo, situation.start), resolve(repo, situation.fix)
    tmp = dest + ".building"
    shutil.rmtree(tmp, ignore_errors=True)
    copy = os.path.join(tmp, "copy")
    os.makedirs(copy)
    archive = subprocess.run(["git", "archive", "--format=tar", start], cwd=repo, capture_output=True)
    if archive.returncode != 0:
        raise BenchError(f"git archive {start[:12]} failed: {archive.stderr.decode(errors='replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        try:
            tar.extractall(copy, filter="tar")
        except TypeError:  # Python before 3.11.4 has no filter
            tar.extractall(copy)
    git(["init", "--quiet", "-b", "main"], copy)
    # -f: the tree as upstream tracked it, a file its .gitignore lists included
    git(["add", "-A", "-f"], copy)
    git(["commit", "--quiet", "--no-verify", "-m", f"{project.name} at the start"], copy)
    commit = git(["rev-parse", "HEAD"], copy).strip()
    for path in situation.hidden_tests:
        blob = subprocess.run(["git", "show", f"{fix}:{path}"], cwd=repo, capture_output=True)
        if blob.returncode != 0:
            raise BenchError(f"{situation.id}: the fix has no hidden test file {path}")
        target = os.path.join(tmp, "hidden", path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            f.write(blob.stdout)
    excludes = [f":(exclude){p}" for p in situation.hidden_tests]
    diff = subprocess.run(["git", "diff", "--binary", "--no-color", start, fix, "--", ".", *excludes], cwd=repo,
                          capture_output=True)
    with open(os.path.join(tmp, "fix.diff"), "wb") as f:
        f.write(diff.stdout)
    if project.commands["setup"]:
        log(f"{situation.id}: setup, with the network")
        code, out = run(project.commands["setup"], copy, project_env(project, store_root), project.timeout)
        if code != 0:
            raise BenchError(f"{situation.id}: setup failed ({'timeout' if code is None else f'exit {code}'}):\n"
                             f"{out[-3000:]}")
    write(os.path.join(tmp, "meta.toml"), tomlw.dumps({"start": start, "fix": fix, "commit": commit,
                                                        "built": now_iso()}))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return dest


def meta(store_root, situation):
    import tomllib
    with open(os.path.join(folder(store_root, situation), "meta.toml"), "rb") as f:
        return tomllib.load(f)


def fresh(store_root, situation, dest):
    """A new copy of the sealed repository at `dest`, what setup fetched included."""
    copy_from = os.path.join(folder(store_root, situation), "copy")
    shutil.copytree(copy_from, dest, symlinks=True)
    return dest


def put_hidden(store_root, situation, root):
    """Put the hidden test files in place in `root`, over whatever is there."""
    base = os.path.join(folder(store_root, situation), "hidden")
    for path in situation.hidden_tests:
        target = os.path.join(root, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.lexists(target) and not os.path.isfile(target):
            shutil.rmtree(target) if os.path.isdir(target) else os.unlink(target)
        shutil.copyfile(os.path.join(base, path), target)


def fix_diff(store_root, situation):
    return os.path.join(folder(store_root, situation), "fix.diff")


def ok_sealed(copy):
    """What makes a copy sealed: one commit, no remote, one ref. Returns what is wrong, or []."""
    problems = []
    if git(["remote"], copy).strip():
        problems.append("it has a remote")
    refs = git(["for-each-ref", "--format=%(refname)"], copy).split()
    if refs != ["refs/heads/main"]:
        problems.append(f"it has refs {refs}")
    if git(["rev-list", "--count", "--all"], copy).strip() != "1":
        problems.append("it has more than one commit")
    return problems
