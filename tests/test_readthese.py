"""Read these: a pull request opens with the lines that need a person's eye, built from facts, not by the author."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

CLEAN = {"summary": "Clean.", "findings": []}
BLOCKING = {"severity": "blocking", "file": "src/calc.py", "line": 2, "claim": "add(-1, 1) returns the wrong sign.",
            "check": "a test of add with negative numbers"}
ADVISORY = {"severity": "advisory", "file": "src/calc.py", "line": 1, "claim": "add has no docstring."}
FLAG = '''
[[rules]]
id = "reads-the-environment"
files = "src/**"
forbid = ["os.environ"]
flag = true
why = "new configuration the deploy must set"
'''


def message(p):
    """The squash commit's message: with no remote it is what the pull request's description would be."""
    return p.git("log", "-1", "--format=%B", "main")


def read_these(body):
    return body.split("## Read these\n", 1)[1].split("\n\n## Why", 1)[0].splitlines()


class Body(RailTest):
    def merged(self, p, nn="1"):
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        return message(p)

    def test_a_plain_change_says_nothing_needs_a_persons_eye_and_counts_what_was_checked(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(CLEAN)
        body = self.merged(p)
        self.assertTrue(body.split("\n", 2)[2].startswith("## Read these\n"), body)  # before the author's own words
        self.assertEqual(read_these(body), ["Nothing needs a person's eye.",
                                            "1 other changed line: checked by verify, 1 check and the reviewer."])
        self.assertLess(body.index("## Read these"), body.index("## Look at"))

    def test_markers_flag_rules_manifests_and_gitattributes_are_listed_with_their_lines(self):
        p = self.fixture(config=CONFIG + FLAG, files={"pyproject.toml": "[project]\nname = 'calc'\n"})
        p.add(ticket(scope=("src/**", "pyproject.toml", ".gitattributes")))
        p.rail("next")
        work = p.worktree("1")
        p.write("src/calc.py", "import os\n\n\ndef add(a, b):\n    # SHORTCUT(1): ints only; use Decimal for money\n"
                               "    return a + b\n\n\nLIMIT = os.environ.get('LIMIT')\nMODE = os.environ.get('MODE')\n", base=work)
        p.write("pyproject.toml", "[project]\nname = 'calc'\ndependencies = ['requests']\n", base=work)
        p.write(".gitattributes", "src/gen/** linguist-generated\n", base=work)
        p.queue_reviews(CLEAN)
        listed = read_these(self.merged(p))
        self.assertEqual(listed, [
            "- src/calc.py:5: # SHORTCUT(1): ints only; use Decimal for money (a marker)",
            "- src/calc.py:9-10: reads-the-environment: new configuration the deploy must set (a flag rule)",
            "- .gitattributes: it can mark files as generated, which hides them from the diff and from the size count"
            " (the change)",
            "- pyproject.toml: a manifest changed: what the project depends on or runs (the change)",
            "8 other changed lines: checked by verify, 1 check and the reviewer."])

    def test_a_flag_rule_never_fails_the_ship(self):
        p = self.fixture(config=CONFIG + FLAG)
        p.add(ticket())
        p.rail("next")
        p.write("src/calc.py", "import os\n\n\ndef add(a, b):\n    return a + b + int(os.environ.get('X', 0))\n",
                base=p.worktree("1"))
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "1")
        self.assertEqual([s for s in shipped["steps"] if s["step"] == "rules"][0]["result"], "pass")

    def test_findings_the_machines_decided_against_are_listed_where_they_are(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews({"summary": "Two things.", "findings": [BLOCKING, ADVISORY]},
                        {"summary": "The sign is right: -1 + 1 is 0.", "findings": []})
        p.rail("advance", "1", expect=3)
        p.rail("answer", "1", "F1", "declined", "add(-1, 1) is 0, which is right.")
        p.rail("answer", "1", "F2", "declined", "The name says it.")
        listed = read_these(self.merged(p))
        self.assertEqual(listed[:2], [
            "- src/calc.py:2: F1, a blocking finding the refuter dismissed: add(-1, 1) returns the wrong sign."
            " (the review)",
            "- src/calc.py:1: F2, an advisory finding the author declined: add has no docstring. (the review)"])

    def test_an_amended_done_contract_on_an_auto_ticket_is_on_the_list(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        changed = os.path.join(self.tmp, "1.md")
        with open(changed, "w") as f:
            f.write(ticket(check="python3 -c 'import sys; sys.path.insert(0, \"src\"); import calc; assert calc.add(-1, 1) == 0'",
                           front=('id = "1"',)))
        p.rail("amend", "1", "the first check passed for a wrong reason", "--file", changed)
        p.queue_reviews(CLEAN)
        listed = read_these(self.merged(p))
        self.assertEqual(listed[0], "- The ticket: the Done Contract changed after it was accepted, with no person: the"
                                    " first check passed for a wrong reason (an amend)")


class OnGitHub(RailTest):
    def shipped(self, a, github, code, **kw):
        a.add(ticket(**kw))
        a.rail("next")
        a.write("src/calc.py", code, base=a.worktree("1"))
        a.queue_reviews(CLEAN, CLEAN)
        a.rail("advance", "1")
        github.ci("1-fix-add", "success")

    def test_an_auto_ticket_with_a_list_merges_with_its_items_on_their_lines_and_no_label_for_a_person(self):
        a, b, github = self.github_pair()
        self.shipped(a, github, "def add(a, b):\n    # SHORTCUT(1): ints only; use Decimal for money\n    return a + b\n")
        self.assertIn("## Read these\n- src/calc.py:2: # SHORTCUT(1): ints only; use Decimal for money (a marker)\n"
                      "1 other changed line: checked by verify, 1 check and the reviewer.\n\n## Why", github.pr(1)["body"])
        self.assertEqual(a.rail("advance", "1")["state"], "merged")
        # Nothing asks a person to read a merged AUTO ticket: the list is in the description and the squash message.
        self.assertEqual([name for name in github.pr(1)["labels"] if name not in ("rail",)], [])
        comments = github.read()["line_comments"]["1"]
        self.assertEqual([(c["path"], c["line"]) for c in comments], [("src/calc.py", 2)])
        self.assertEqual(comments[0]["body"], "# SHORTCUT(1): ints only; use Decimal for money (a marker)\n\n<!-- rail -->")
        self.assertIn("## Read these\n- src/calc.py:2:", bare_message(github))

    def test_an_auto_ticket_with_nothing_to_read_gets_no_label_and_no_comment(self):
        a, b, github = self.github_pair()
        self.shipped(a, github, "def add(a, b):\n    return a + b\n")
        self.assertEqual(a.rail("advance", "1")["state"], "merged")
        self.assertEqual(github.read().get("line_comments", {}).get("1", []), [])

    def test_a_person_ticket_shows_why_it_is_a_persons_before_the_merge_and_hears_an_answer_on_a_line(self):
        a, b, github = self.github_pair()
        a.add(ticket(tier="PERSON", front=('person_reason = "money: src/calc.py"',)))
        a.rail("next")  # no approval before the build: the person's one act is the merge
        a.write("src/calc.py", "def add(a, b):\n    return a + b  # TODO(7): floats\n", base=a.worktree("1"))
        a.queue_reviews(CLEAN, CLEAN)
        a.rail("advance", "1")
        github.ci("1-fix-add", "success")
        waiting = a.rail("next")
        self.assertEqual(waiting["waits"][0]["needs"], "MERGE_BY_PERSON")
        body = github.pr(1)["body"]
        self.assertIn("- The ticket: the ticket is PERSON as it was written: money: src/calc.py (the tier)", body)
        self.assertIn("- src/calc.py:2: return a + b # TODO(7): floats (a marker)", body)
        self.assertEqual(len(github.read()["line_comments"]["1"]), 1)
        a.rail("next")
        self.assertEqual(len(github.read()["line_comments"]["1"]), 1)  # once per patch, however many runs pass

        # The person answers the item on its line, and sends the ticket back.
        def answer(s):
            s["line_comments"]["1"].append({"path": "src/calc.py", "line": 2, "body": "Do the floats now, please.",
                                            "user": {"login": "octocat"}, "author_association": "OWNER",
                                            "created_at": "2099-01-01T00:00:00Z"})
        github.update(answer)
        self.assertIn("src/calc.py:2: Do the floats now, please.", cli_note(a))


class Init(RailTest):
    def test_init_marks_the_generated_files_so_github_folds_them(self):
        p = self.fixture(init=False, files={"pyproject.toml": "[project]\nname = 'calc'\n", "uv.lock": "",
                                            ".gitattributes": "*.png binary\n"})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "first")
        first = p.rail("init")
        with open(p.path(".gitattributes")) as f:
            self.assertEqual(f.read(), "*.png binary\n**/*_pb2.py linguist-generated\n**/*_pb2_grpc.py linguist-generated\n")
        self.assertEqual([s["status"] for s in first["steps"] if s["step"] == ".gitattributes"], ["ran"])
        again = p.rail("init")
        self.assertEqual([s["status"] for s in again["steps"] if s["step"] == ".gitattributes"], ["not_run"])

    def test_a_project_with_nothing_generated_gets_no_gitattributes(self):
        p = self.fixture()
        self.assertFalse(os.path.exists(p.path(".gitattributes")))


def bare_message(github):
    import subprocess
    return subprocess.run(["git", "--git-dir", github.read()["bare"], "log", "-1", "--format=%B", "main"],
                          capture_output=True, text=True).stdout


def cli_note(p):
    """What a person said during the wait, as the engine reads it for the next brief."""
    import subprocess
    code = ("import os, sys; sys.path.insert(0, os.environ['E']); from rail import cli; from rail.project import Project;"
            "p = Project(os.getcwd()); p.sync(); t, f = cli.load(p); print(cli.person_comments(p, f['1']))")
    env = dict(os.environ, E=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"),
               RAIL_FAKE_GITHUB=p.github.state, PATH=p.github.bin + os.pathsep + os.environ["PATH"])
    return subprocess.run([sys.executable, "-c", code], cwd=p.root, env=env, capture_output=True, text=True).stdout
