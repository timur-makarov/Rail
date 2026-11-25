"""The bench's first part, with no model anywhere: the project file, the sealed copy, the grade and admission."""

import os
import subprocess

from benchtest import BENCH_CLI, BenchTest

from bench import admit, common, grade, sealed, sets

FIXED_ADD = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n\n\ndef div(a, b):\n    return a / b\n"


def patch_of(root, files):
    """A patch from the sealed copy's start commit that writes `files`."""
    for path, text in files.items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    return grade.diff(root, "HEAD")


class ProjectFile(BenchTest):
    def test_the_fixture_loads_with_its_four_situations(self):
        p = self.project()
        self.assertEqual([s.id for s in p.situations], ["calc-01", "calc-02", "calc-flaky", "calc-null"])
        s = p.situation("calc-01")
        self.assertEqual(s.title, "add() gives the wrong answer")
        self.assertEqual(p.slug, "acme/calc")
        self.assertEqual(p.package_of("calc/ops.py", "."), ".")
        self.assertEqual(p.set, "fixture")

    def test_an_unknown_key_is_refused_and_named(self):
        for old, new, word in (('kind = "crash"', 'kind = "crash"\nsevere = true', "severe"),
                               ('language = "python"', 'language = "python"\nowner = "x"', "owner"),
                               ("[rail.config.commands]", "[review]\nx = 1\n\n[rail.config.commands]", "review")):
            with self.subTest(word=word):
                with open(self.project_file) as f:
                    backup = f.read()
                self.edit_project(old, new)
                with self.assertRaises(common.BenchError) as e:
                    self.project()
                self.assertIn(word, str(e.exception))
                with open(self.project_file, "w") as f:
                    f.write(backup)

    def test_a_bad_value_is_refused(self):
        for old, new, word in (('kind = "crash"', 'kind = "bad"', "kind"),
                               ('half = "held"', 'half = "later"', "half"),
                               ('closed = 2026-12-02', 'closed = "soon"', "closed"),
                               ('hidden_tests = ["tests/test_div.py"]', 'hidden_tests = ["../x.py"]', "hidden_tests"),
                               ('hidden_tests = ["tests/test_div.py"]', 'hidden_tests = "tests/test_div.py"', "type"),
                               ('half = "held"', 'half = "held"\nextra = [{kind = "fault"}]', "not built yet"),
                               ('id = "calc-02"', 'id = "calc-01"', "twice")):
            with self.subTest(word=word):
                with open(self.project_file) as f:
                    backup = f.read()
                self.edit_project(old, new)
                with self.assertRaises(common.BenchError) as e:
                    self.project()
                self.assertIn(word, str(e.exception))
                with open(self.project_file, "w") as f:
                    f.write(backup)

    def test_package_rules(self):
        p = self.project()
        os.makedirs(os.path.join(self.tmp, "w", "crates", "a", "src"))
        open(os.path.join(self.tmp, "w", "crates", "a", "Cargo.toml"), "w").close()
        for rule, path, want in (("dir", "pkg/sub/x.go", "pkg/sub"), ("top", "pkg/sub/x.go", "pkg"),
                                 ("top", "x.go", "."), ("nearest:Cargo.toml", "crates/a/src/lib.rs", "crates/a"),
                                 ("nearest:Cargo.toml", "src/main.rs", "."),
                                 ("regex:^(packages/[^/]+)/", "packages/web/src/a.ts", "packages/web")):
            p.commands["package_of"] = rule
            self.assertEqual(p.package_of(path, os.path.join(self.tmp, "w")), want, rule)


class SealedCopy(BenchTest):
    def test_one_commit_no_remote_no_other_ref_and_no_hidden_test_or_fix_inside(self):
        s = self.situation("calc-01")
        dest = sealed.build(self.store, s)
        copy = os.path.join(dest, "copy")
        self.assertEqual(sealed.ok_sealed(copy), [])
        self.assertFalse(os.path.exists(os.path.join(copy, "tests", "test_add.py")))
        with open(os.path.join(copy, "calc", "ops.py")) as f:
            self.assertIn("a - b", f.read())
        # the hidden tests and the fix are beside the copy, not in it
        self.assertTrue(os.path.exists(os.path.join(dest, "hidden", "tests", "test_add.py")))
        with open(os.path.join(dest, "fix.diff")) as f:
            fix = f.read()
        self.assertIn("+    return a + b", fix)
        self.assertNotIn("test_add.py", fix)
        # nothing of the upstream history: the fix's commit is not an object in the copy
        meta = sealed.meta(self.store, s)
        found = subprocess.run(["git", "cat-file", "-e", meta["fix"]], cwd=copy, capture_output=True)
        self.assertNotEqual(found.returncode, 0)

    def test_the_same_start_gives_the_same_commit(self):
        a = sealed.build(self.store, self.situation("calc-01"))
        b = sealed.build(self.store, self.situation("calc-02"))
        head = [common.git(["rev-parse", "HEAD"], os.path.join(d, "copy")).strip() for d in (a, b)]
        self.assertEqual(head[0], head[1])
        self.assertEqual(head[0], sealed.meta(self.store, self.situation("calc-01"))["commit"])

    def test_setup_runs_once_while_it_is_built_and_its_failure_says_why(self):
        self.edit_project('setup = ""', 'setup = "echo fetched > .fetched"')
        dest = sealed.build(self.store, self.situation("calc-01"))
        self.assertTrue(os.path.exists(os.path.join(dest, "copy", ".fetched")))
        self.edit_project('setup = "echo fetched > .fetched"', 'setup = "echo no network; exit 4"')
        with self.assertRaises(common.BenchError) as e:
            sealed.build(self.store, self.situation("calc-02"))
        self.assertIn("exit 4", str(e.exception))
        self.assertIn("no network", str(e.exception))


class Grade(BenchTest):
    def setUp(self):
        super().setUp()
        self.s = self.situation("calc-01")
        sealed.build(self.store, self.s)
        self.work = sealed.fresh(self.store, self.s, os.path.join(self.tmp, "work"))

    def grade(self, patch, rounds=3):
        return grade.grade(self.store, self.s, patch, rounds=rounds)

    def test_the_fix_is_right_and_the_red_test_at_start_is_left_out(self):
        result = self.grade(patch_of(self.work, {"calc/ops.py": FIXED_ADD}))
        self.assertTrue(result["right"], result.get("why"))
        self.assertEqual(result["packages"], ["."])
        self.assertEqual(len(result["rounds"]), 3)
        pkg = result["rounds"][0]["packages"]["."]
        # test_legacy fails on the start commit and still fails: left out
        self.assertEqual(len(pkg["failing"]), 1)
        self.assertIn("test_square_of_two", pkg["failing"][0])
        self.assertEqual(pkg["why"], "only tests red on the start commit fail")

    def test_no_change_is_wrong(self):
        result = self.grade(b"")
        self.assertFalse(result["right"])
        self.assertIn("hidden tests fail", result["why"])

    def test_a_change_that_breaks_a_package_test_is_wrong(self):
        broken = FIXED_ADD.replace("return a * b", "return a * b + 1")
        result = self.grade(patch_of(self.work, {"calc/ops.py": broken}))
        self.assertFalse(result["right"])
        self.assertIn("test_mul", result["why"])

    def test_the_arms_own_test_at_a_hidden_tests_path_is_set_aside(self):
        own = "import unittest\n\n\nclass Mine(unittest.TestCase):\n    def test_mine(self):\n        self.fail('mine')\n"
        result = self.grade(patch_of(self.work, {"calc/ops.py": FIXED_ADD, "tests/test_add.py": own}))
        self.assertTrue(result["right"], result.get("why"))
        self.assertEqual(result["aside"], ["tests/test_add.py"])

    def test_in_dir_mode_a_test_beside_a_hidden_one_is_set_aside_too(self):
        p = self.s.project
        p.clash = "dir"
        self.assertEqual(grade.clashing(p, self.s, ["tests/test_mine.py", "calc/ops.py", "tests/test_add.py"]),
                         ["tests/test_add.py", "tests/test_mine.py"])
        p.clash = "path"
        self.assertEqual(grade.clashing(p, self.s, ["tests/test_mine.py", "calc/ops.py"]), [])

    def test_a_change_that_passes_some_rounds_is_wrong(self):
        counter = os.path.join(self.tmp, "race")
        racy = FIXED_ADD.replace("    return a + b", (
            f"    import os\n    n = int(open({counter!r}).read()) if os.path.exists({counter!r}) else 0\n"
            f"    open({counter!r}, 'w').write(str(n + 1))\n    return a + b if n < 4 else a - b"))
        result = self.grade(patch_of(self.work, {"calc/ops.py": racy}))
        self.assertFalse(result["right"])
        self.assertEqual(result["rounds"][0]["hidden"][0]["exit"], 0)
        self.assertIn("round 2", result["why"])

    def test_a_change_that_does_not_apply_is_wrong_and_says_so(self):
        result = self.grade(b"diff --git a/nope.py b/nope.py\n--- a/nope.py\n+++ b/nope.py\n@@ -1 +1 @@\n-x\n+y\n")
        self.assertFalse(result["right"])
        self.assertFalse(result["applied"])
        self.assertIn("does not apply", result["why"])

    def test_the_change_of_a_working_tree_leaves_out_rail_and_claude_files(self):
        patch = patch_of(self.work, {"calc/ops.py": FIXED_ADD, "notes/new.txt": "new\n", ".claude/settings.local.json": "{}",
                                     ".rail/x": "x"})
        self.assertEqual(sorted(grade.changed_paths(patch)), ["calc/ops.py", "notes/new.txt"])


class Admission(BenchTest):
    def test_the_fixture_admits_two_and_refuses_the_flaky_and_the_null_pass(self):
        p = self.project()
        results = {s.id: admit.admit(self.store, s, self.conf, log=lambda *_: None) for s in p.situations}
        self.assertTrue(results["calc-01"][0], results["calc-01"][1])
        self.assertTrue(results["calc-02"][0], results["calc-02"][1])
        ok, reasons, record = results["calc-flaky"]
        self.assertFalse(ok)
        self.assertEqual(reasons, ["oracle: the hidden tests passed 3 of 4 times with the fix (flaky)"])
        ok, reasons, _ = results["calc-null"]
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith("null: the hidden tests pass on the start commit"))
        self.assertEqual(results["calc-01"][2]["rail"], {"setup": "empty", "verify": "pass"})
        self.assertTrue(os.path.exists(os.path.join(sealed.folder(self.store, p.situation("calc-01")), "admission.toml")))

    def test_rails_verify_red_on_the_start_commit_refuses_it(self):
        self.edit_project('verify = "python3 -m unittest tests.test_ops"', 'verify = "python3 -m unittest tests.test_legacy"')
        ok, reasons, _ = admit.admit(self.store, self.situation("calc-01"), self.conf, log=lambda *_: None)
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith("rail: verify fails on the start commit"), reasons)

    def test_a_request_that_links_the_fix_is_refused(self):
        self.edit_project("It should return 5.", "It should return 5, as https://github.com/acme/calc/pull/8 does.")
        ok, reasons, _ = admit.admit(self.store, self.situation("calc-01"), self.conf, log=lambda *_: None)
        self.assertFalse(ok)
        self.assertIn("request: holds the fix's pull request 8", reasons)

    def test_the_command_line_prints_why(self):
        env = dict(os.environ, BENCH_CONFIG=os.path.join(self.tmp, "bench.toml"))
        with open(env["BENCH_CONFIG"], "w") as f:
            f.write("oracle_runs = 4\n")
        done = subprocess.run([BENCH_CLI, "admit", self.project_file, "--id", "calc-null", "--id", "calc-01"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("calc-01: admitted", done.stdout)
        self.assertIn("calc-null: not admitted\n  - null: the hidden tests pass", done.stdout)


class Loader(BenchTest):
    def test_bench_config_refuses_an_unknown_key(self):
        path = os.path.join(self.tmp, "c.toml")
        with open(path, "w") as f:
            f.write("oracle_run = 3\n")
        with self.assertRaises(common.BenchError) as e:
            common.settings(path)
        self.assertIn("oracle_run", str(e.exception))

    def test_toml_writer_round_trips(self):
        import datetime
        import tomllib

        from bench import tomlw
        data = {"a": "x\"y\n", "b": [1, 2], "c": True, "d": datetime.date(2026, 12, 1),
                "t": {"k": "v", "sub": {"z": 1}}, "rules": [{"id": "r1", "forbid": ["a"]}, {"id": "r2"}],
                "odd key": 1}
        self.assertEqual(tomllib.loads(tomlw.dumps(data)), data)
        self.assertIsInstance(sets.load(self.project_file), sets.Project)
