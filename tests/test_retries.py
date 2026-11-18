"""Retries: the budget, the cap, consult and the worker ladder. The reviewer and consult are stand-ins (fake_reviewer.py)."""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket


def events(p, kind=None, nn="1", branch="1-fix-add"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]
    return [e for e in rows if kind is None or e["event"] == kind]


def calc(p, body, nn="1"):
    p.write("src/calc.py", f"def add(a, b):\n    {body}\n", base=p.worktree(nn))


class Consult(RailTest):
    def test_a_setup_that_fails_the_same_way_twice_gets_consults_advice_from_next_then_waits_for_a_person(self):
        setup = 'echo "make: no such tool"; exit 1'
        p = self.fixture(config=CONFIG.replace("[commands]", f"[commands]\nsetup = '{setup}'"))
        p.add(ticket())
        self.assertEqual(p.rail("next", expect=3)["reason"]["code"], "SETUP_FAILED")
        self.assertEqual(events(p, "consulted"), [])
        again = p.rail("next", "--ticket", "1", expect=3)  # setup runs again and fails the same way: the budget
        self.assertEqual((again["owner"], again["reason"]["code"]), ("agent", "SETUP_FAILED"))
        self.assertEqual([(s["step"], s["result"]) for s in again["steps"]], [("setup", "fail"), ("consult", "pass")])
        consulted = events(p, "consulted")
        self.assertEqual([(e["trigger"], e["step"], e["verdict"]) for e in consulted], [("retry_cap", "setup", "change")])
        advice = p.git("show", "1-fix-add:.rail/journal/1-advice.md")
        self.assertIn("retry_cap at 'setup', change", advice)
        self.assertIn("The check expects a + b.", advice)
        stuck = p.rail("next", "--ticket", "1", expect=3)  # once more after consult
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'setup' failed the same way 2 times in a row, then once more after consult ([retry] budget)",
                      stuck["action"]["brief"])
        self.assertEqual(len(events(p, "consulted")), 1)

    def test_with_no_consult_pack_the_budget_goes_straight_to_a_person(self):
        p = self.fixture()
        shutil.rmtree(p.path(".rail", "packs", "consult"))
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "no consult pack")
        p.add(ticket())
        p.rail("next")
        first = p.rail("advance", "1", expect=3)
        self.assertEqual((first["owner"], first["reason"]["code"]), ("agent", "STEP_FAILED"))
        stuck = p.rail("advance", "1", expect=3)  # the same failure again
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'checks' failed the same way 2 times in a row ([retry] budget)", stuck["action"]["brief"])
        self.assertNotIn("consult", stuck["action"]["brief"])
        self.assertEqual(events(p, "consulted"), [])
        asked = p.rail("consult", "1", "Is a + b the right fix?", expect=2)
        self.assertEqual(asked["reason"]["code"], "NO_PACK")
        self.assertIn(".rail/packs/consult", asked["reason"]["message"])

    def test_a_ticket_gets_at_most_three_consults_and_then_the_budget_goes_to_a_person(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        for n in range(3):
            self.assertIn("consult says change", p.rail("consult", "1", f"Question {n + 1}?")["advice"])
        refused = p.rail("consult", "1", "One more?", expect=2)
        self.assertEqual(refused["reason"]["code"], "CONSULT_LIMIT")
        self.assertIn("ticket 1 has had its 3 consults", refused["reason"]["message"])
        self.assertEqual(len(events(p, "consulted")), 3)
        p.rail("advance", "1", expect=3)
        stuck = p.rail("advance", "1", expect=3)  # the budget, and no consult left to ask
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'checks' failed the same way 2 times in a row ([retry] budget)", stuck["action"]["brief"])
        self.assertEqual(len(events(p, "consulted")), 3)

    def test_when_consult_says_stop_the_ticket_waits_for_a_person_at_once(self):
        p = self.fixture()
        p.write(".rail/packs/consult/bin/consult",
                '#!/bin/sh\ncat > /dev/null\necho \'{"verdict": "stop", "advice": "The check contradicts the Why."}\'\n')
        os.chmod(p.path(".rail", "packs", "consult", "bin", "consult"), 0o755)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "a consult pack that says stop")
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)
        second = p.rail("advance", "1", expect=3)  # the same failure again: the budget, and consult is asked
        self.assertEqual([e["verdict"] for e in events(p, "consulted")], ["stop"])
        self.assertEqual((second["owner"], second["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'checks' failed the same way 2 times in a row, and consult said a person must decide"
                      " (its advice is in .rail/journal/1-advice.md) ([retry] budget)", second["action"]["brief"])
        self.assertIn("The check contradicts the Why.", p.git("show", "1-fix-add:.rail/journal/1-advice.md"))
        self.assertEqual(p.rail("next")["owner"], "human")  # no further attempt is offered

    def test_a_consult_pack_that_answers_nothing_readable_counts_as_stop(self):
        p = self.fixture()
        p.write(".rail/packs/consult/bin/consult", '#!/bin/sh\necho "consult: no model is configured"\n')
        os.chmod(p.path(".rail", "packs", "consult", "bin", "consult"), 0o755)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "a broken consult pack")
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)
        stuck = p.rail("advance", "1", expect=3)
        self.assertEqual([e["verdict"] for e in events(p, "consulted")], ["stop"])
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("consult said a person must decide", stuck["action"]["brief"])
        self.assertIn("The consult pack failed: consult: no model is configured",
                      p.git("show", "1-fix-add:.rail/journal/1-advice.md"))

    def test_consults_brief_leaves_out_the_workers_own_story(self):
        # The worker writes ## Look at; consult judges from the ticket and the diff, not from the worker's account.
        p = self.fixture()
        saved = os.path.join(self.tmp, "consult-request.json")
        p.write(".rail/packs/consult/bin/consult",
                f'#!/bin/sh\ncat > "{saved}"\necho \'{{"verdict": "proceed", "advice": "Go on."}}\'\n')
        os.chmod(p.path(".rail", "packs", "consult", "bin", "consult"), 0o755)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "a consult pack that keeps its request")
        p.add(ticket(body="\n## Look at\nI am sure the sign flip is the only bug.\n\n"
                          "## Out of scope\nMultiplication stays as it is.\n"))
        p.rail("next")
        self.assertIn("consult says proceed", p.rail("consult", "1", "Is a + b the right fix?")["advice"])
        with open(saved) as f:
            text = json.load(f)["ticket_text"]
        self.assertIn("add subtracts instead of adding.", text)  # ## Why
        self.assertIn("Multiplication stays as it is.", text)  # the section after ## Look at stays
        self.assertNotIn("## Look at", text)
        self.assertNotIn("I am sure the sign flip is the only bug.", text)


class Ladder(RailTest):
    def test_the_ladder_holds_at_its_last_rung(self):
        p = self.fixture(config=CONFIG + '\n[worker]\nladder = ["model-small:low", "model-big:high"]\n')
        p.add(ticket())
        claimed = p.rail("next")
        self.assertEqual((claimed["action"]["model"], claimed["action"]["effort"]), ("model-small", "low"))
        first = p.rail("advance", "1", expect=3)  # AssertionError
        self.assertEqual((first["action"]["model"], first["action"]["effort"]), ("model-big", "high"))
        calc(p, "return a + c")  # NameError: a new failure, the second attempt
        second = p.rail("advance", "1", expect=3)
        self.assertEqual((second["reason"]["code"], second["action"]["model"], second["action"]["effort"]),
                         ("STEP_FAILED", "model-big", "high"))
        again = p.rail("next")
        self.assertEqual((again["reason"]["code"], again["action"]["model"]), ("STEP_FAILED", "model-big"))


class ReviewRetries(RailTest):
    def test_failed_review_runs_count_as_the_same_failure_whatever_their_reasons(self):
        # A review run's output differs from run to run, so its failures are counted plainly: two failed runs are the
        # budget, whatever went wrong in each. Neither is a timeout, so the review isn't stuck.
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        ghost = {"severity": "blocking", "file": "src/missing.py", "claim": "x"}
        p.queue_reviews({"summary": "Read it.", "findings": [ghost]}, {"raw": "not json at all"}, {"raw": "nor this"})
        first = p.rail("advance", "1", expect=3)
        self.assertIn("src/missing.py isn't a tracked file", first["steps"][-1]["detail"])
        self.assertNotIn("consult says", first["action"]["brief"])
        second = p.rail("advance", "1", expect=3)
        self.assertEqual(second["steps"][-2]["detail"], "invalid output: the output is not JSON")
        self.assertEqual((second["owner"], second["reason"]["code"]), ("agent", "REVIEW"))  # not STUCK_REVIEW
        self.assertIn("consult says change", second["action"]["brief"])
        runs = [e for e in events(p, "step") if e["step"] == "review"]
        self.assertNotEqual(runs[0]["detail"], runs[1]["detail"])
        self.assertEqual(runs[0]["signature"], runs[1]["signature"])
        stuck = p.rail("advance", "1", expect=3)
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'review' failed the same way 2 times in a row, then once more after consult",
                      stuck["action"]["brief"])
