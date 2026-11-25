"""What every part of the bench shares: its own settings, the store, running a command, and git."""

import datetime
import os
import shutil
import signal
import subprocess
import time
import tomllib

BENCH = os.path.dirname(os.path.abspath(__file__))
FRAMEWORK = os.path.dirname(BENCH)  # the Rail checkout the bench sits in: its bin/rail installs Rail into a copy

# Every commit the bench makes has this author and date, so the same tree gives the same commit id on any machine.
GIT_IDENTITY = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@localhost", "GIT_COMMITTER_NAME": "bench",
                "GIT_COMMITTER_EMAIL": "bench@localhost", "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"}

DEFAULTS = {
    "store": "",
    "oracle_runs": 10,
    "grade_rounds": 3,
    "command_minutes": 30,
}


class BenchError(Exception):
    """A refusal with one sentence that says why."""


def settings(path=None):
    """bench/config.toml over the defaults. An unknown key is refused."""
    path = path or os.environ.get("BENCH_CONFIG") or os.path.join(BENCH, "config.toml")
    found = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "rb") as f:
            raw = tomllib.load(f)
        for key, value in raw.items():
            if key not in DEFAULTS:
                raise BenchError(f"{path}: unknown key '{key}'")
            if type(value) is not type(DEFAULTS[key]):
                raise BenchError(f"{path}: {key} must be {type(DEFAULTS[key]).__name__}")
            found[key] = value
    return found


def store(conf):
    """The folder that holds mirrors, sealed copies and runs: BENCH_STORE, then the config's store, then
    ~/.rail-bench."""
    path = os.environ.get("BENCH_STORE") or conf["store"] or os.path.join(os.path.expanduser("~"), ".rail-bench")
    path = os.path.realpath(os.path.expanduser(path))
    os.makedirs(path, exist_ok=True)
    return path


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bash(command):
    return [shutil.which("bash") or "/bin/bash", "-o", "pipefail", "-c", command]


def run(command, cwd, env=None, timeout=None, stdin=None, stdout=None):
    """Run a shell command in its own process group. Returns (exit code, or None when the timeout ended it, output).
    With `stdout` (an open file) the output goes there instead and the returned output is empty."""
    proc = subprocess.Popen(bash(command), cwd=cwd, env=env, text=True, start_new_session=True,
                            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=stdout or subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        out, _ = proc.communicate(input=stdin, timeout=timeout)
        return proc.returncode, out or ""
    except subprocess.TimeoutExpired:
        kill(proc)
        out, _ = proc.communicate()
        return None, out or ""


def kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def git(args, cwd, env=None, check=True, input=None, text=True):
    """A git command with the bench's identity. Returns stdout."""
    full = dict(os.environ if env is None else env)
    full.update(GIT_IDENTITY)
    full["GIT_CONFIG_NOSYSTEM"] = "1"
    done = subprocess.run(["git", "-c", "core.quotePath=false", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
                           *args], cwd=cwd, env=full, capture_output=True, text=text, input=input)
    if check and done.returncode != 0:
        err = done.stderr if text else done.stderr.decode(errors="replace")
        raise BenchError(f"git {' '.join(args[:3])} failed in {cwd}: {err.strip()}")
    return done.stdout


def commit_all(cwd, message, env=None):
    """Stage everything, ignored files left out, and commit it. Returns the commit id."""
    git(["add", "-A"], cwd, env)
    git(["commit", "--quiet", "--allow-empty", "--no-verify", "-m", message], cwd, env)
    return git(["rev-parse", "HEAD"], cwd, env).strip()


def copy_tree(src, dest):
    """A copy of a folder, symlinks kept as links."""
    shutil.copytree(src, dest, symlinks=True)


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def minutes(seconds):
    return round(seconds / 60, 2)


class Clock:
    """Seconds since it started."""

    def __init__(self):
        self.began = time.monotonic()

    def seconds(self):
        return time.monotonic() - self.began
