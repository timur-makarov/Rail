"""Old tests run against the new code: at ship the checks run once more with the base's version of the test files the
change edits, and a command that then fails raises the triage question `old-test` (rail docs triage)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, FAKE, RailTest, ticket
from test_review import clean
from test_triage import said

CALC = "def add(a, b):\n    return a {op} b\n\n\ndef negate(a):\n    return {negated}\n"
TEST = "import sys\nsys.path.insert(0, 'src')\nimport calc\n\n{first}assert calc.negate(0) == 0\n"
OLD = TEST.format(first="assert calc.negate(2) == -2\n")
WEAKER = TEST.format(first="")
RUN_TESTS = 'for t in tests/test_*.py; do [ -e "$t" ] || continue; python3 "$t" || exit 1; done'
ASKS = "- Negating is dropped: negate returns its argument."


def config(log, paths='["tests/**"]'):
    return f"""\
[commands]
verify = '''echo verify >> {log}; python3 -m py_compile src/calc.py && {RUN_TESTS}'''
timeout_secs = 60

[tests]
paths = {paths}

[map]
ignore = ["tests", "checks"]

[review]
command = "python3 {FAKE}"

[consult]
command = "python3 {FAKE} --consult"
"""


def events(p, kind, branch="1-fix-add"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if e["event"] == kind]


class OldTests(RailTest):
    def project(self, body="", **kw):
        self.log = os.path.join(self.tmp, "verify.log")
        p = self.fixture(config=config(self.log, **kw), files={
            "src/calc.py": CALC.format(op="-", negated="-a"), "tests/test_calc.py": OLD, "REVIEW.md": "Flag a float.\n"})
        p.add(ticket(scope=("src/**", "tests/**", "REVIEW.md"), body=body))
        p.rail("next")
        return p

    def change(self, p, negated="a", **files):
        """The work: add is mended, negate becomes `negated`, and the test files are as given."""
        wt = p.worktree("1")
        p.write("src/calc.py", CALC.format(op="+", negated=negated), base=wt)
        for path, text in files.items():
            path = path.replace("__", "/") + ".py"
            if text is None:
                os.remove(os.path.join(wt, path))
            else:
                p.write(path, text, base=wt)

    def verifies(self):
        with open(self.log) as f:
            return len(f.read().split())

    def test_a_test_that_lost_an_assertion_is_run_as_the_base_had_it_and_raises_one_question_before_any_review(self):
        p = self.project()
        self.change(p, tests__test_calc=WEAKER)
        p.queue_reviews(said("lost", "negate(2) is 2 now, and nothing in the ticket is about negate."))
        stopped = p.rail("advance", "1", expect=3)
        ran = events(p, "base_tests")
        self.assertEqual(len(ran), 1)
        self.assertEqual((ran[0]["files"], ran[0]["patch_id"]), (["tests/test_calc.py"], events(p, "shipped")[-1]["patch_id"]))
        self.assertEqual([(c["step"], c["result"]) for c in ran[0]["commands"]], [("verify", "red"), ("checks", "green")])
        self.assertIn("AssertionError", ran[0]["commands"][0]["output"])
        asked = events(p, "question")
        self.assertEqual([(q["id"], q["type"], q["key"]) for q in asked], [("Q1", "old-test", "tests/test_calc.py")])
        self.assertEqual(asked[0]["fact"]["commands"], [ran[0]["commands"][0]["command"]])
        self.assertIn("passed with the change's tests and failed with the base branch's version of tests/test_calc.py.",
                      asked[0]["fact"]["said"])

        # The run saw the old test's diff, the command with its output, and the ticket's Why and Done Contract;
        # of the rest of the change, nothing.
        (run,) = p.briefs()
        for text in ("# One question about ticket 1 (Q1, old-test)", "-assert calc.negate(2) == -2",
                     f"`git show {ran[0]['base']}:tests/test_calc.py`", "## The command, with the old tests in place",
                     "AssertionError", "## The ticket's Why\nadd subtracts instead of adding.",
                     f"## The ticket's Done Contract\n- Check: `{CHECK_ADD}`",
                     "- `contract`: the contract asks for this change in behaviour. Evidence: the Done Contract line or the"
                     " sentence of ## Why that asks for it, word for word.",
                     "- `moved`: the behaviour is kept;", "- `lost`: behaviour is lost that the contract does not ask for."):
            self.assertIn(text, run["brief"])
        self.assertNotIn("return a + b", run["brief"])

        # Answered `lost`, triage fails, and the worker's brief holds the command and the answer.
        self.assertEqual((stopped["state"], stopped["reason"]["code"], stopped["steps"][-1]["detail"]),
                         ("implementing", "STEP_FAILED", "Q1 old-test: lost"))
        brief = stopped["action"]["brief"]
        for text in ("failed with the base branch's version of tests/test_calc.py.",
                     "Its answer: `lost`, behaviour is lost that the contract does not ask for.",
                     "Its reason: negate(2) is 2 now, and nothing in the ticket is about negate.",
                     'amend it so that it says so (rail amend 1 "why")'):
            self.assertIn(text, brief)
        # The worktree is the change again, with nothing left behind.
        with open(os.path.join(p.worktree("1"), "tests", "test_calc.py")) as f:
            self.assertEqual(f.read(), WEAKER)
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")

        # The worker keeps the behaviour: the old test passes again, so the next patch is asked about nothing.
        self.change(p, negated="-a", tests__test_calc=WEAKER)
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual([c["result"] for c in events(p, "base_tests")[-1]["commands"]], ["green", "green"])
        self.assertEqual(len(events(p, "question")), 1)

    def test_contract_with_a_line_of_the_ticket_and_moved_with_a_test_of_the_change_let_it_go_on(self):
        p = self.project(body=f"{ASKS}\n")
        self.change(p, tests__test_calc=WEAKER)
        p.queue_reviews(said("contract", evidence="Negating is kept."),     # not in the ticket: the run is repeated
                        said("contract", evidence=ASKS), clean())
        went = p.rail("advance", "1", expect=3)  # 3: the first run failed on the way
        self.assertEqual(went["state"], "merge-ready")
        self.assertEqual([(a["answer"], a["evidence_ok"]) for a in events(p, "answered")],
                         [("contract", False), ("contract", True)])
        # The reviewer is told what the change did to its own checks, and how the question was answered.
        review = p.briefs()[-1]["brief"]
        section = review.split("## Changes to what checks this change\n")[1].split("\n## ")[0]
        self.assertIn("- tests/test_calc.py: a test file, edited, and the base had it", section)
        self.assertIn("- With the base branch's version of tests/test_calc.py in place:", section)
        self.assertIn("red, `" + CHECK_ADD + "` green.", section)
        self.assertIn(f"- A triage run was asked about that (Q1) and answered `contract`: Read the ticket. It named: {ASKS}",
                      section)

    def test_moved_names_a_test_file_the_change_touches(self):
        p = self.project()
        moved = TEST.format(first="assert calc.negate(-2) == -2\n")
        self.change(p, tests__test_calc=WEAKER, tests__test_sign=moved)
        p.queue_reviews(said("moved", evidence="src/calc.py"),            # in the change, and no test file
                        said("moved", evidence="tests/test_other.py"),    # not in the change
                        clean())
        waits = p.rail("advance", "1", expect=3)
        self.assertEqual(waits["reason"]["code"], "STUCK_REVIEW")
        self.assertEqual([s["detail"] for s in events(p, "step") if s["step"] == "triage"], [
            "invalid output: 'src/calc.py' is not under [tests] paths",
            "invalid output: 'tests/test_other.py' is not a file the change touches"])
        p.rail("accept", "1")
        p.queue_reviews(said("moved", evidence="`tests/test_sign.py`"), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(events(p, "answered")[-1]["evidence_ok"], True)

    def test_an_edited_test_that_keeps_the_behaviour_is_green_and_raises_nothing(self):
        p = self.project()
        self.change(p, negated="-a", tests__test_calc=OLD + "assert calc.add(1, 1) == 2\n")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual([c["result"] for c in events(p, "base_tests")[0]["commands"]], ["green", "green"])
        self.assertEqual(events(p, "question"), [])
        self.assertEqual(self.verifies(), 2)  # the ship's own run, and the one with the base's test

    def test_a_deleted_test_is_put_back_for_the_run_and_a_renamed_one_under_its_old_path(self):
        p = self.project()
        self.change(p, tests__test_calc=None)
        p.queue_reviews(said("lost"))
        p.rail("advance", "1", expect=3)
        gone = events(p, "base_tests")[0]
        self.assertEqual((gone["files"], gone["commands"][0]["result"]), (["tests/test_calc.py"], "red"))
        self.assertFalse(os.path.exists(os.path.join(p.worktree("1"), "tests", "test_calc.py")))
        self.assertIn("deleted file mode", p.briefs()[0]["brief"])

        q = self.fixture("renamed", config=config(os.path.join(self.tmp, "other.log")), files={
            "src/calc.py": CALC.format(op="-", negated="-a"), "tests/test_calc.py": OLD})
        q.add(ticket(scope=("src/**", "tests/**", "checks/**")))
        q.rail("next")
        self.change(q, tests__test_calc=None, checks__sign=WEAKER + "# moved out of tests/\n")  # outside [tests] paths
        q.queue_reviews(said("lost"))
        q.rail("advance", "1", expect=3)
        moved = events(q, "base_tests")[0]
        self.assertEqual((moved["files"], moved["commands"][0]["result"]), (["tests/test_calc.py"], "red"))
        self.assertIn("rename from tests/test_calc.py", q.briefs()[0]["brief"])
        self.assertEqual(q.git("status", "--porcelain", cwd=q.worktree("1")), "")

    def test_a_new_test_file_is_the_authors_and_an_empty_tests_paths_switches_it_off(self):
        p = self.project()
        self.change(p, negated="-a", tests__test_add="import sys\nsys.path.insert(0, 'src')\nimport calc\n\n"
                                                      "assert calc.add(2, 3) == 5\n")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual((events(p, "base_tests"), self.verifies()), ([], 1))
        review = p.briefs()[-1]["brief"]
        self.assertIn("## Changes to what checks this change", review)
        self.assertIn("- tests/test_add.py: a test file, new in this change", review)

        off = self.fixture("off", config=config(os.path.join(self.tmp, "off.log"), paths="[]"), files={
            "src/calc.py": CALC.format(op="-", negated="-a"), "tests/test_calc.py": OLD})
        off.add(ticket(scope=("src/**", "tests/**")))
        off.rail("next")
        self.change(off, tests__test_calc=WEAKER)
        off.queue_reviews(clean())
        self.assertEqual(off.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual((events(off, "base_tests"), events(off, "question")), ([], []))
        self.assertNotIn("## Changes to what checks this change", off.briefs()[-1]["brief"])

    def test_a_clean_rebase_does_not_run_it_again(self):
        p = self.project(body=f"{ASKS}\n")
        self.change(p, tests__test_calc=WEAKER)
        p.queue_reviews(said("contract", evidence=ASKS), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(self.verifies(), 2)
        p.write("api/handlers.py", "def handle():\n    return 204\n")
        p.git("commit", "--quiet", "-am", "a change on the base that touches nothing of the ticket's")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertEqual((len(events(p, "base_tests", "main")), len(events(p, "question", "main"))), (1, 1))
        self.assertEqual(self.verifies(), 3)  # the ship after the rebase ran verify once, and not with the old test

    def test_a_changed_review_md_is_named_to_the_reviewer(self):
        p = self.project()
        self.change(p, negated="-a")
        p.write("REVIEW.md", "Flag nothing.\n", base=p.worktree("1"))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertIn("## Changes to what checks this change", p.briefs()[-1]["brief"])
        self.assertIn("- REVIEW.md: review guidance, edited, and the base had it", p.briefs()[-1]["brief"])
