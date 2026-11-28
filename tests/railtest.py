"""Test harness: throwaway fixture projects driven through the real `rail` launcher."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "rail")

# The repository's engine, the one bin/rail runs. A test that imports an engine module in-process imports it from
# here, never from a fixture's .rail/engine: that copy is deleted with the fixture, and the `rail` package stays in
# sys.modules pointing at the deleted folder, so every later in-process import in the same worker fails.
ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(RAIL))), "engine")


def engine():
    """Put the repository's engine on sys.path, so that `from rail import ...` works in the test process."""
    if ENGINE not in sys.path:
        sys.path.insert(0, ENGINE)

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_reviewer.py")
FAKE_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_worker.py")
FAKE_GH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_gh.py")
GITHUB_URL = "https://github.com/acme/app.git"

# The calculator has no manifest, so no project is derived for it: one entry declares the whole fixture as a project
# with no commands of its own. Without it every folder would be inside no project, and each ship would ask about it
# (rail docs languages). A config a test writes itself gets the entry too, unless it has a [[projects]] of its own.
CALC = '[[projects]]\nname = "calc"\npaths = ["**"]\n'

CONFIG = f"""\
{CALC}
[commands]
verify = "python3 -m py_compile src/calc.py"
timeout_secs = 60

[review]
command = "python3 {FAKE}"

[consult]
command = "python3 {FAKE} --consult"
"""

# First in a config, it makes a PERSON ticket of the kind `ticket` names wait for a person's approval of its
# contract before the build. Without it a person acts once on a PERSON ticket, at the merge (rail docs kinds).
APPROVE = 'approve_contract = ["data-shape"]\n'

ARCHITECTURE = """\
# Architecture

## Areas
| Area | Paths | Holds |
|---|---|---|
| calc | src/** | the calculator |
| api | api/** | public HTTP handlers |
"""


CHECK_ADD = "python3 -c \"import sys; sys.path.insert(0, 'src'); import calc; assert calc.add(2, 3) == 5\""


def ticket(title="Fix add", tier="AUTO", scope=("src/**",), check=CHECK_ADD, front=(), body=""):
    """A ticket file, in the format rail add reads. A PERSON ticket names a kind, as lint requires."""
    scope_list = ", ".join(f'"{s}"' for s in scope)
    if tier == "PERSON" and not any(line.startswith("person_reason") for line in front):
        front = (*front, f'person_reason = "data-shape: {scope[0]}"')
    lines = ["+++", f'title = "{title}"', f'tier = "{tier}"', f"scope_paths = [{scope_list}]", *front, "+++", "",
             "## Why", "add subtracts instead of adding.", "",
             "## Done Contract", f"- Check: `{check}`", ""]
    return "\n".join(lines) + body


class Fixture:
    """A git project set up with `rail init`, with a test config and a tiny calculator.

    With `remote`, it is a clone of that bare repository instead. With `tree`, the project is a copy of that folder
    and nothing else, not the calculator. `projects=False` leaves a config with no [[projects]] entry as it is.
    """

    def __init__(self, root, config=CONFIG, files=None, remote=None, init=True, tree=None, projects=True):
        self.root = root
        if remote:
            self.git("clone", "--quiet", remote, root, cwd=os.path.dirname(root))
            return
        if tree:
            shutil.copytree(tree, root)
        else:
            os.makedirs(root)
        self.git("init", "--quiet", "-b", "main")
        defaults = {} if tree else {
            ".gitignore": ".claude/worktrees/\n__pycache__/\n",
            "ARCHITECTURE.md": ARCHITECTURE,
            "src/calc.py": "def add(a, b):\n    return a - b\n",
            "api/handlers.py": "def handle():\n    return 200\n",
        }
        defaults.update(files or {})
        for path, text in defaults.items():
            self.write(path, text)
        if not init:
            return
        self.rail("init")
        if not tree and "[[projects]]" not in config and projects:
            config = config.rstrip("\n") + "\n\n" + CALC
        self.write(".rail/config.toml", config)
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "init")

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def write(self, rel, text, base=None):
        full = os.path.join(base or self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True, text=True, check=True).stdout

    @property
    def reviews(self):
        return self.root + ".reviews.json"

    @property
    def review_log(self):
        return self.root + ".reviews.log"

    def queue_reviews(self, *responses):
        """What the stand-in reviewer answers to the next review runs, in order."""
        with open(self.reviews, "w") as f:
            json.dump(list(responses), f)

    def queue_work(self, *items):
        """What the stand-in worker does in the next `rail work` runs, in order (tests/fake_worker.py)."""
        with open(self.root + ".worker.json", "w") as f:
            json.dump(list(items), f)

    def work_log(self):
        path = self.root + ".worker.log"
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f]

    def briefs(self):
        if not os.path.exists(self.review_log):
            return []
        with open(self.review_log) as f:
            return [json.loads(line) for line in f]

    def rail(self, *args, cwd=None, session="session-a", expect=0, raw=False, cloud=False, env_extra=None):
        env = dict(os.environ)
        env.pop("RAIL_TICKET", None)
        env.pop("GITHUB_ACTIONS", None)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        env["RAIL_CLOUD"] = "1" if cloud else "0"  # the suite itself may run inside a cloud session
        # No bytecode files: a check that imports src/calc.py right after a test rewrote it, in the same second and at
        # the same size, would run the stale .pyc and fail a correct change.
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # What provision writes on a cloud machine goes to a scratch home and bin folder, never the real ones.
        scratch = os.path.join(os.path.dirname(self.root), "machine")
        env["RAIL_BIN_DIR"] = os.path.join(scratch, "bin")
        if cloud:
            env["HOME"] = os.path.join(scratch, "home")
            os.makedirs(env["RAIL_BIN_DIR"], exist_ok=True)
            os.makedirs(env["HOME"], exist_ok=True)
        env.update(env_extra or {})
        env["CLAUDE_CODE_SESSION_ID"] = session
        env["RAIL_FAKE_REVIEWS"] = self.reviews
        env["RAIL_FAKE_LOG"] = self.review_log
        env["RAIL_FAKE_WORKER"] = self.root + ".worker.json"
        env["RAIL_FAKE_WORKER_LOG"] = self.root + ".worker.log"
        if getattr(self, "github", None):
            env["RAIL_FAKE_GITHUB"] = self.github.state
            env["PATH"] = self.github.bin + os.pathsep + env["PATH"]
        cmd = [sys.executable, RAIL, *args] + ([] if raw else ["--json"])
        result = subprocess.run(cmd, cwd=cwd or self.root, capture_output=True, text=True, env=env)
        if expect is not None and result.returncode != expect:
            raise AssertionError(f"rail {' '.join(args)} exited {result.returncode}, expected {expect}\n"
                                 f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        if raw:
            return result
        answer = json.loads(result.stdout)
        check_shape(answer, args[0] if args else None)
        return answer

    def add(self, text, **kw):
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        try:
            return self.rail("add", path, **kw)
        finally:
            os.unlink(path)

    def worktree(self, nn):
        return self.path(".claude", "worktrees", nn)

    def undiagnosed(self, nn="1"):
        """A ticket at its retry cap gets one diagnosis before it is dropped or waits (rail docs retries). Here the
        stand-in answers `cannot-tell`, which leaves the ticket where it was: what rail next then answers."""
        self.queue_reviews({"answer": "cannot-tell", "reason": "Nothing here shows which."})
        return self.rail("next", "--ticket", nn)

    def fix_calc(self, nn):
        self.write("src/calc.py", "def add(a, b):\n    return a + b\n", base=self.worktree(nn))


def check_shape(answer, verb=None):
    """Every verb answers in the same shape, and in the one engine/answer-v1.json describes."""
    engine()
    from rail import answers
    broken = answers.check(answer, verb)
    assert not broken, "\n".join(["the answer breaks engine/answer-v1.json:", *broken, json.dumps(answer, indent=1)[:3000]])
    assert answer["schema_version"] == 2, answer
    if not answer["ok"]:
        assert answer["reason"]["code"] and answer["reason"]["message"], answer
        return
    for key in ("ticket", "state", "owner", "cwd", "action", "reason", "steps"):
        assert key in answer, (key, answer)
    assert answer["owner"] in ("agent", "person", "none"), answer
    assert answer["action"]["kind"] in ("script", "agent_task", "person_wait", "rest"), answer
    for step in answer["steps"]:
        assert step["status"] in ("ran", "could_not_run", "not_run", "unavailable"), step
        assert ("result" in step) == (step["status"] in ("ran", "could_not_run")), step
        assert step["status"] != "could_not_run" or step["result"] == "fail", step


class GitHub:
    """The fake GitHub that tests/fake_gh.py serves: its state file, and acts a person or GitHub would take."""

    def __init__(self, tmp, bare):
        self.state = os.path.join(tmp, "github.json")
        self.bin = os.path.join(tmp, "ghbin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gh"), "w") as f:
            f.write(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_GH}" "$@"\n')
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.write({"repo": "acme/app", "bare": bare, "labels": [], "pulls": [], "issues": [], "checks": {},
                    "required": ["rail"], "settings": {"allow_squash_merge": True}})

    def read(self):
        with open(self.state) as f:
            return json.load(f)

    def write(self, state):
        with open(self.state, "w") as f:
            json.dump(state, f)

    def update(self, change):
        state = self.read()
        change(state)
        self.write(state)

    def pr(self, number):
        return next(p for p in self.read()["pulls"] if p["number"] == number)

    def head(self, branch):
        bare = self.read()["bare"]
        return subprocess.run(["git", "--git-dir", bare, "rev-parse", f"refs/heads/{branch}"], capture_output=True,
                              text=True).stdout.strip()

    def ci(self, branch, conclusion="success", summary="", log=None):
        """GitHub's CI finishes on the branch's head: the `rail` check passes or fails. With `log`, the check run
        is shaped like one from GitHub Actions: no output of its own, and the job's log behind its id."""
        sha = self.head(branch)
        run = {"name": "rail", "status": "completed", "conclusion": conclusion, "output": {"summary": summary}}
        if log is not None:
            run.update(id=7001, app={"slug": "github-actions"}, output={"title": None, "summary": "", "text": None})

        def change(s):
            s["checks"][sha] = [run]
            if log is not None:
                s.setdefault("logs", {})["7001"] = log

        self.update(change)

    def label(self, number, name):
        self.update(lambda s: next(p for p in s["pulls"] if p["number"] == number)["labels"].append(name))

    def person_merges(self, number):
        """A person presses the merge button: GitHub squashes with the PR title and description."""
        pr = self.pr(number)
        env = dict(os.environ, RAIL_FAKE_GITHUB=self.state)
        payload = json.dumps({"merge_method": "squash", "commit_title": f"{pr['title']} (#{number})",
                              "commit_message": pr["body"]})
        subprocess.run([os.path.join(self.bin, "gh"), "api", "--method", "PUT",
                        f"repos/acme/app/pulls/{number}/merge-async", "--input", "-"], input=payload, env=env,
                       capture_output=True, text=True, check=True)


class RailTest(unittest.TestCase):
    def setUp(self):
        # realpath: on macOS the temp folder is behind a symlink (/var -> /private/var), and git and the engine
        # report the resolved path
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="rail-test-"))
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        gitconfig = os.path.join(home, ".gitconfig")
        with open(gitconfig, "w") as f:
            f.write("[user]\n\tname = Rail Test\n\temail = rail@example.com\n[commit]\n\tgpgsign = false\n"
                    "[init]\n\tdefaultBranch = main\n")
        self._env = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        os.environ["GIT_CONFIG_GLOBAL"] = gitconfig
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, name="proj", **kw):
        return Fixture(os.path.join(self.tmp, name), **kw)

    def github_pair(self, **kw):
        """Two clones of a repository on the fake GitHub: git reaches the bare remote through insteadOf, and gh is the
        fake. Returns (a, b, github)."""
        a, b = self.remote_pair(**kw)
        bare = os.path.join(self.tmp, "remote.git")
        github = GitHub(self.tmp, bare)
        for fx in (a, b):
            fx.git("config", "remote.origin.url", GITHUB_URL)
            fx.git("config", f"url.{bare}.insteadOf", GITHUB_URL)
            fx.github = github
        return a, b, github

    def remote_pair(self, **kw):
        """A bare remote and two clones of it: a laptop and a cloud run."""
        seed = self.fixture("seed", **kw)
        bare = os.path.join(self.tmp, "remote.git")
        seed.git("clone", "--quiet", "--bare", seed.root, bare, cwd=self.tmp)
        return Fixture(os.path.join(self.tmp, "a"), remote=bare), Fixture(os.path.join(self.tmp, "b"), remote=bare)
