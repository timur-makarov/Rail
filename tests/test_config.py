"""Settings in .rail/config.toml that change what the engine does, and the errors a bad config gives."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, Fixture, RailTest, ticket  # noqa: E402


def step(answer, name):
    return [s for s in answer["steps"] if s["step"] == name][-1]


class BaseBranch(RailTest):
    def test_the_whole_loop_runs_on_a_base_branch_that_is_not_main(self):
        p = Fixture(os.path.join(self.tmp, "trunk"), init=False)
        p.git("symbolic-ref", "HEAD", "refs/heads/trunk")
        p.rail("init")
        p.write(".rail/config.toml", 'base_branch = "trunk"\n' + CONFIG)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "init")
        added = p.add(ticket())
        self.assertEqual((added["state"], added["branch"]), ("accepted", "1-fix-add"))
        self.assertEqual(p.rail("next")["reason"]["code"], "IMPLEMENT")
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertEqual(p.git("log", "-1", "--format=%s", "trunk").strip(), "1: fix add")
        self.assertEqual(p.git("show", "trunk:src/calc.py"), "def add(a, b):\n    return a + b\n")
        self.assertEqual(p.git("branch", "--list", "main"), "")


class Size(RailTest):
    def test_a_path_in_size_exclude_does_not_count_toward_the_cap(self):
        p = self.fixture(config=CONFIG + '\n[size]\ncap = 10\nexclude = ["src/gen/**"]\n')
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/gen/table.py", "".join(f"x{i} = {i}\n" for i in range(40)), base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["tier"], shipped["reason"]["code"]), ("merge-ready", "AUTO", "MERGE"))
        self.assertEqual(step(shipped, "size")["detail"], "size 2/10")


class Rules(RailTest):
    RULES = ('\n[[rules]]\nid = "no-new-suppressions"\nforbid = ["# noqa"]\nallow = ["src/legacy/**"]\n'
             'fix = "Fix the cause instead of silencing the check."\n'
             '\n[[rules]]\nid = "migrations-home"\nfiles = "**/*.sql"\nonly_in = "db/migrations/**"\n'
             'allow = ["src/fixtures/**"]\nfix = "Use make migration."\n')

    def test_a_path_a_rule_allows_is_skipped_and_the_rule_still_holds_elsewhere(self):
        p = self.fixture(config=CONFIG + self.RULES)
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/legacy/old.py", "import os  # noqa\n", base=p.worktree("1"))
        p.write("src/fixtures/rows.sql", "insert into t values (1);\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], step(shipped, "rules")["result"]), ("merge-ready", "pass"))
        self.assertEqual(p.rail("advance", "1")["state"], "merged")  # ticket 2 has the same scope: it waits for this

        p.add(ticket(title="Silence a warning", scope=("src/**",)))
        p.rail("next", "--ticket", "2", session="b")
        p.write("src/calc.py", "def add(a, b):\n    return a - b  # noqa\n", base=p.worktree("2"))
        p.write("src/report.sql", "select 1;\n", base=p.worktree("2"))
        failed = p.rail("advance", "2", session="b", expect=3)
        self.assertEqual(step(failed, "rules")["detail"], "2 broken: no-new-suppressions")
        self.assertIn("src/calc.py adds '# noqa'", failed["action"]["brief"])
        self.assertIn("src/report.sql is a new file outside db/migrations/**", failed["action"]["brief"])


class Map(RailTest):
    ARCHITECTURE = ("# Architecture\n\n## Areas\n| Area | Paths | Holds |\n|---|---|---|\n"
                    "| calc | src/calc.py | the calculator |\n| parsing | src/parse/** | the parser |\n"
                    "| api | api/** | public HTTP handlers |\n")

    def test_map_depth_is_the_directory_depth_areas_must_cover(self):
        files = {"ARCHITECTURE.md": self.ARCHITECTURE, "src/parse/read.py": "x = 1\n", "src/format/write.py": "y = 2\n"}
        for depth, result in ((1, "pass"), (2, "fail")):
            with self.subTest(depth=depth):
                p = self.fixture(name=f"depth{depth}", config=CONFIG + f"\n[map]\ndepth = {depth}\n", files=files)
                p.add(ticket())
                p.rail("next")
                p.fix_calc("1")
                shipped = p.rail("advance", "1", expect=None)
                self.assertEqual(step(shipped, "doc-lint")["result"], result)
                if result == "fail":
                    self.assertIn("src/format/ is in no ## Areas row", shipped["action"]["brief"])
                    self.assertNotIn("src/parse/", shipped["action"]["brief"])


class Commands(RailTest):
    def test_with_no_verify_the_step_is_not_run_and_the_ticket_ships(self):
        p = self.fixture(config=CONFIG.replace('verify = "python3 -m py_compile src/calc.py"\n', ""))
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], step(shipped, "verify")), ("merge-ready", {"step": "verify", "status": "not_run"}))

    def test_setup_runs_before_verify_is_tried_on_the_base_so_a_failure_stays_the_tickets_own(self):
        # verify needs a file setup makes. When verify fails on the ticket, the engine runs it on the base to tell a
        # red base from the ticket's own failure: setup has to run there first, or every failure looks like a red base.
        config = CONFIG.replace('verify = "python3 -m py_compile src/calc.py"',
                                "setup = 'touch .ready'\n"
                                "verify = 'test -f .ready || { echo no .ready: run setup; exit 1; }; python3 -m compileall -q src'")
        p = self.fixture(config=config, files={".gitignore": ".claude/worktrees/\n__pycache__/\n.ready\n"})
        p.add(ticket())
        claimed = p.rail("next")
        self.assertEqual(step(claimed, "setup")["result"], "pass")
        p.fix_calc("1")
        p.write("src/broken.py", "def broken(:\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["reason"]["code"], step(failed, "verify")["detail"]), ("STEP_FAILED", "exit 1"))
        self.assertIn("broken.py", failed["action"]["brief"])
        self.assertEqual(len(p.rail("status")["tickets"]), 1)  # no fix ticket for a red base


class Validation(RailTest):
    def test_a_bad_config_names_the_key_and_what_is_wrong(self):
        p = self.fixture()
        cases = {
            '[commands]\ntimeout_secs = "60"\n': "config: commands.timeout_secs must be int",
            "[commands]\nbase_checks = 1\n": "config: commands.base_checks must be bool",
            'person_paths = [".github/**", 3]\n': "config: person_paths must be a list of strings",
            'review = "claude -p"\n': "config: review must be a table",
            '[commands]\nverfy = "make test"\n': "config: unknown key 'commands.verfy' (did you mean 'verify'?)",
            'rules = "no-new-suppressions"\n': "config: rules must be an array of tables ([[rules]])",
            '[[rules]]\nid = "x"\nforbids = ["# noqa"]\n': "config: unknown key 'rules[0].forbids' (did you mean 'forbid'?)",
            '[[rules]]\nid = "x"\nforbid = "# noqa"\n': "config: rules[0].forbid must be list",
            '[[rules]]\nforbid = ["# noqa"]\n': "config: rules[0] needs an id",
            '[[projects]]\nname = "api"\npath = ["api/**"]\n': "config: unknown key 'projects[0].path' (did you mean 'paths'?)",
            '[[projects]]\npaths = ["api/**"]\n': "config: projects[0] needs a name",
            '[[projects]]\nname = "api"\npaths = "api/**"\n': "config: projects[0].paths must be list",
            '[[projects]]\nname = "api"\npaths = ["api/**"]\n\n[[projects]]\nname = "api"\npaths = ["web/**"]\n':
                "config: projects[1] needs a name no other entry has; got 'api'",
            'projects = "api"\n': "config: projects must be an array of tables ([[projects]])",
            '[[profiles]]\nname = "go"\n': "config: unknown key 'profiles'",
            '[tests]\npaths = "tests/**"\n': "config: tests.paths must be list",
            "[commands]\nverify = make test\n": "config: .rail/config.toml is not valid TOML",
        }
        for text, message in cases.items():
            with self.subTest(message):
                p.write(".rail/config.toml", text)
                self.assertIn(message, p.rail("status", expect=2)["reason"]["message"])

    def test_a_config_with_a_project_and_test_paths_loads(self):
        p = self.fixture(config=CONFIG + '\n[tests]\npaths = ["**/*_test.go"]\n\n[[projects]]\nname = "api"\n'
                                         'paths = ["api/**"]\nverify = "true"\nuses = ["calc"]\n')
        self.assertEqual(p.rail("status")["reason"]["code"], "STATUS")

    def test_a_packs_own_section_is_taken_only_when_the_pack_is_there(self):
        p = self.fixture(config=CONFIG + '\n[hello]\ngreeting = "hi"\n')
        self.assertIn("config: unknown key 'hello'", p.rail("status", expect=2)["reason"]["message"])
        p.write(".rail/packs/hello/bin/hello", "#!/bin/sh\necho hi\n")
        self.assertEqual(p.rail("status")["reason"]["code"], "STATUS")


class Sources(RailTest):
    def test_a_source_file_that_does_not_load_says_why(self):
        p = self.fixture()
        for text, problem in (
                ("+++\nfetch = 'true'\nmax_open = 1\nLook.\n", "the front matter has no closing '+++' line"),
                ("+++\nfetch = true story\n+++\nLook.\n", "the front matter is not valid TOML"),
                ("+++\nfetch = 'true'\nmax_open = '2'\n+++\nLook.\n", "max_open must be int"),
                ("+++\nfetch = 'true'\nmax_open = true\n+++\nLook.\n", "max_open must be int"),
                ("+++\nmax_open = 2\n+++\nLook.\n", "fetch is missing: the command whose output is the signal"),
                ("+++\nfetch = 'true'\nmax_open = 0\n+++\nLook.\n", "max_open must be 1 or more")):
            with self.subTest(problem):
                p.write(".rail/sources/ci.md", text)
                failed = p.rail("source", "ci", expect=2)
                self.assertEqual(failed["reason"]["code"], "BAD_SOURCE")
                self.assertIn(f".rail/sources/ci.md: {problem}", failed["reason"]["message"])
