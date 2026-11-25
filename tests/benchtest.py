"""Test harness for the bench: a throwaway store and the fixture project (tests/bench_fixture), built fresh per test."""

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bench import common, fixture, sets  # noqa: E402

BENCH_CLI = os.path.join(ROOT, "bench", "bench")


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
        self._env = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "BENCH_STORE")}
        os.environ["GIT_CONFIG_GLOBAL"] = gitconfig
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        self.store = os.path.join(self.tmp, "store")
        os.environ["BENCH_STORE"] = self.store
        os.makedirs(self.store)
        self.project_file = fixture.build(os.path.join(self.tmp, "src"))
        self.conf = dict(common.DEFAULTS, oracle_runs=4, grade_rounds=3)

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
