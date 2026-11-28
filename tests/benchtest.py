"""Test harness for the bench: a throwaway store and the fixture project (tests/bench_fixture), built fresh per test."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bench import common, fixture, sets  # noqa: E402

BENCH_CLI = os.path.join(ROOT, "bench", "bench")
DETERMINISTIC = ["GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"]


class BenchTest(unittest.TestCase):
    """Each test gets a temporary folder with a git identity, a store, and the fixture's repository and project file."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="bench-test-"))
        home = os.path.join(self.tmp, "home")
        os.makedirs(home)
        gitconfig = os.path.join(home, ".gitconfig")
        with open(gitconfig, "w") as f:
            f.write("[user]\n\tname = Bench Test\n\temail = bench@example.com\n[commit]\n\tgpgsign = false\n"
                    "[init]\n\tdefaultBranch = main\n")
        self._env = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "BENCH_STORE",
                                                    "BENCH_CONFIG", "GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
        os.environ["GIT_CONFIG_GLOBAL"] = gitconfig
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        self.store = os.path.join(self.tmp, "store")
        os.environ["BENCH_STORE"] = self.store
        os.makedirs(self.store)
        self.project_file = fixture.build(os.path.join(self.tmp, "src"))
        self.conf = dict(common.DEFAULTS, oracle_runs=4, grade_rounds=3,
                         pass_env=common.DEFAULTS["pass_env"] + DETERMINISTIC)
        # A bench config of its own, so the command line in a child process reads the same settings.
        os.environ["BENCH_CONFIG"] = self.config_file = os.path.join(self.tmp, "bench.toml")
        self.write_config()
        # Every commit's date is fixed, so the fake arm's runs give the same commit ids: a restart can be compared
        # with the full run byte for byte, apart from the journal's times.
        for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
            os.environ[key] = "2001-01-01T00:00:00Z"

    def write_config(self, **changes):
        from bench import tomlw
        self.conf.update(changes)
        with open(self.config_file, "w") as f:
            f.write(tomlw.dumps({k: v for k, v in self.conf.items() if k != "store"}))

    def bench(self, *args, expect=0, timeout=900):
        """Run the bench's command line. Returns its output."""
        done = subprocess.run([BENCH_CLI, *args], capture_output=True, text=True, timeout=timeout)
        if expect is not None and done.returncode != expect:
            raise AssertionError(f"bench {' '.join(args)} exited {done.returncode}\n{done.stdout}\n{done.stderr}")
        return done.stdout

    def plan(self, **plan):
        """A fake agent's plan, as a file. Keys left out come from the default plan for the situation."""
        from bench import driver, sealed
        s = self.situation(plan.pop("situation", "calc-01"))
        sealed.build(self.store, s)
        full = driver.default_plan(self.store, s)
        full.update(plan)
        path = os.path.join(self.tmp, f"plan-{len(os.listdir(self.tmp))}.json")
        with open(path, "w") as f:
            json.dump(full, f)
        return path

    def run_fake(self, sid="calc-01", arm="fake", plan=None, n=1):
        """A run of a fake arm through the command line. Returns its Run."""
        from bench import runs
        args = ["run", self.project_file, "--id", sid, "--arm", arm, "--runs", str(n)]
        self.bench(*args, *(["--plan", plan] if plan else []), expect=None)
        return runs.Run(os.path.join(self.store, "runs", f"calc.{sid}.{arm}.{n}"))

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def project(self):
        return sets.load(self.project_file)

    def situation(self, sid="calc-01"):
        return self.project().situation(sid)

    def edit_project(self, old, new):
        with open(self.project_file) as f:
            text = f.read()
        assert old in text, old
        with open(self.project_file, "w") as f:
            f.write(text.replace(old, new, 1))
