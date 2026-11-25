"""Review, contract and retries. The reviewer is a stand-in (fake_reviewer.py)."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

BLOCKING = {"severity": "blocking", "file": "src/calc.py", "line": 2, "claim": "add(-1, 1) returns the wrong sign.",
            "check": "a test of add with negative numbers"}
ADVISORY = {"severity": "advisory", "file": "src/calc.py", "claim": "add has no docstring."}


def clean(summary="Read the diff, ran the check."):
    return {"summary": summary, "findings": []}


def found(*findings, summary="Read the diff, ran the check."):
    return {"summary": summary, "findings": list(findings)}


def events(p, branch, kind=None):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if kind is None or e["event"] == kind]


def review_steps(answer):
    return [s for s in answer["steps"] if s["step"] == "review"]


def read(path):
    with open(path) as f:
        return f.read()


class Review(RailTest):
    def medium(self, p, **kw):
        p.add(ticket(tier="AUTO", **kw))
        p.rail("next")
        p.fix_calc("1")

    def test_a_blocking_finding_is_fixed_and_the_fix_reviewed_again(self):
        p = self.fixture(files={"AGENTS.md": "# Conventions\n\nPrefer small functions.\n"})
        self.medium(p)
        p.queue_reviews(found(BLOCKING, ADVISORY), found(ADVISORY | {"repeats": "F2"}))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["state"], failed["reason"]["code"]), ("reviewing", "ANSWER_FINDINGS"))
        self.assertEqual(failed["steps"][-1]["detail"], "run 1: 1 blocking, 2 findings")
        self.assertIn("F1 (blocking, review) src/calc.py:2: add(-1, 1) returns the wrong sign.", failed["action"]["brief"])
        brief = p.briefs()[0]["brief"]
        self.assertIn("Prefer small functions.", brief)
        self.assertNotIn("rail next --json", brief)  # the ## Rail section stays out of the brief
        self.assertIn("This run's job: Review this change.", brief)
        self.assertNotIn("## The contract as first accepted", brief)  # no amend: the contract is the accepted one
        self.assertIn("Security. This list is a checklist", brief)  # AUTO: the security section is in the one review

        p.write("src/calc.py", "def add(a, b):\n    return b + a\n", base=p.worktree("1"))
        p.rail("answer", "1", "F1", "fixed", "Order no longer matters.")
        p.rail("answer", "1", "F2", "declined", "The project has no docstrings.")
        ready = p.rail("advance", "1")  # the re-review repeats F2: open again, but advisory, so it holds nothing
        self.assertEqual(ready["state"], "merge-ready")
        rereview = p.briefs()[1]["brief"]
        self.assertIn("now fixed (by author): Order no longer matters.", rereview)
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertEqual([r["role"] for r in doc["runs"]], ["review", "review"])
        self.assertNotEqual(doc["runs"][0]["patch_id"], doc["runs"][1]["patch_id"])
        self.assertEqual(doc["runs"][0]["model"], "fake-model")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        body = p.git("log", "-1", "--format=%b", "main")
        self.assertIn("| review | ran, 2 runs by fake-model, 2 findings, 1 open |", body)
        self.assertIn("Advisory findings left open, for the sweep:\n- F2 (advisory, review) src/calc.py: add has no docstring.", body)

    def test_an_open_advisory_finding_alone_reaches_merge_ready_and_is_shown_with_a_blocking_one(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(ADVISORY))
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        q = self.fixture(name="other")
        self.medium(q)
        q.queue_reviews(found(BLOCKING, ADVISORY))
        failed = q.rail("advance", "1", expect=3)
        self.assertIn("- F2 (advisory, review) src/calc.py: add has no docstring.", failed["action"]["brief"])
        q.write("src/calc.py", "def add(a, b):\n    return b + a\n", base=q.worktree("1"))
        q.rail("answer", "1", "F1", "fixed", "Order no longer matters.")
        self.assertEqual(q.rail("advance", "1")["state"], "merge-ready")  # F2 still open

    def test_marking_a_blocking_finding_fixed_without_a_change_needs_a_clean_rereview(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(BLOCKING), found(BLOCKING | {"repeats": "F1"}))
        p.rail("advance", "1", expect=3)
        p.rail("answer", "1", "F1", "fixed", "Done.")
        again = p.rail("advance", "1", expect=3)
        self.assertEqual(review_steps(again)[-1]["detail"], "run 2: 1 blocking, 1 findings")
        self.assertEqual(again["reason"]["code"], "ANSWER_FINDINGS")

    def test_a_disputed_blocking_finding_goes_to_a_refuter(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(BLOCKING), clean("The sign is right: -1 + 1 is 0."))
        p.rail("advance", "1", expect=3)
        disputed = p.rail("answer", "1", "F1", "declined", "add(-1, 1) is 0, which is right.")
        self.assertEqual(disputed["reason"]["code"], "REVIEW")
        done = p.rail("advance", "1")
        self.assertEqual(done["state"], "merge-ready")
        last = events(p, "1-fix-add", "finding")[-1]
        self.assertEqual((last["outcome"], last["by"], last["reason"]), ("declined", "refuter", "The sign is right: -1 + 1 is 0."))
        refuter = p.briefs()[1]["brief"]
        self.assertIn("You are the refuter.", refuter)
        self.assertNotIn("which is right", refuter)  # it never sees the author's argument

    def test_parking_a_blocking_finding_disputes_it_and_the_refuter_decides_whose_problem_it_is(self):
        # Parked meant "a real problem this change didn't cause", and closed a blocking finding with nobody else
        # looking: the author could wave any blocking finding through. Now a fresh refuter decides.
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(BLOCKING), found(BLOCKING | {"repeats": "F1", "severity": "parked"},
                                               summary="Real, but add() was already wrong on main."))
        p.rail("advance", "1", expect=3)
        disputed = p.rail("answer", "1", "F1", "parked", "add() was like this before.")
        self.assertEqual((disputed["state"], disputed["reason"]["code"]), ("reviewing", "REVIEW"))
        self.assertEqual(events(p, "1-fix-add", "finding")[-1]["disputed"], True)
        done = p.rail("advance", "1")
        self.assertEqual(done["state"], "merge-ready", done)
        self.assertEqual(done["steps"][-1]["detail"], "run 2: parked F1")
        last = events(p, "1-fix-add", "finding")[-1]
        self.assertEqual((last["outcome"], last["by"], last["reason"]),
                         ("parked", "refuter", "Real, but add() was already wrong on main."))
        refuter = p.briefs()[1]["brief"]
        self.assertIn("this change didn't cause it, the severity is parked", refuter)
        self.assertNotIn("was like this before", refuter)  # it never sees the author's argument

    def test_a_blocking_finding_the_refuter_upholds_stays_blocking_however_the_author_parks_it(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(BLOCKING), found(BLOCKING | {"repeats": "F1"}, summary="This change made it."))
        p.rail("advance", "1", expect=3)
        p.rail("answer", "1", "F1", "parked")
        upheld = p.rail("advance", "1", expect=3)
        self.assertEqual(upheld["steps"][-1]["detail"], "run 2: upheld F1")
        again = p.rail("answer", "1", "F1", "parked", "Still not mine.")
        self.assertEqual((again["owner"], again["reason"]["code"]), ("human", "FINDING_UPHELD"))
        self.assertIn("parked \"why\" --owner", again["action"]["brief"])
        owner = p.rail("answer", "1", "F1", "parked", "It predates this ticket; ticket 9 fixes it.", "--owner")
        self.assertEqual(owner["state"], "merge-ready")

    def test_an_advisory_finding_parks_without_a_refuter(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(ADVISORY))
        p.rail("advance", "1")
        done = p.rail("answer", "1", "F1", "parked", "The whole module lacks docstrings.")
        self.assertEqual(done["state"], "merge-ready")
        self.assertEqual(len(p.briefs()), 1)

    def test_an_upheld_finding_the_agent_still_disputes_waits_for_a_person(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews(found(BLOCKING), found(BLOCKING | {"repeats": "F1"}, summary="It holds."))
        p.rail("advance", "1", expect=3)
        p.rail("answer", "1", "F1", "declined", "It is fine.")
        upheld = p.rail("advance", "1", expect=3)
        self.assertEqual((upheld["steps"][-1]["step"], upheld["steps"][-1]["detail"]), ("refuter", "run 2: upheld F1"))
        waiting = p.rail("answer", "1", "F1", "declined", "Still fine.")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("human", "FINDING_UPHELD"))
        owner = p.rail("answer", "1", "F1", "declined", "Negative inputs never happen here.", "--owner")
        self.assertEqual(owner["state"], "merge-ready")

    def test_a_person_ticket_runs_the_security_seat_with_a_refuter_and_a_person_approves_the_merge(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        p.fix_calc("1")
        leak = {"severity": "blocking", "file": "src/calc.py", "claim": "The result is logged with the user's token."}
        p.queue_reviews(clean(), found(leak), clean("Nothing is logged at all."))
        ready = p.rail("advance", "1")
        self.assertEqual([s["step"] for s in ready["steps"]][-3:], ["review", "security", "refuter"])
        self.assertEqual((ready["state"], ready["owner"], ready["reason"]["code"]), ("merge-ready", "human", "MERGE_BY_PERSON"))
        briefs = [b["brief"] for b in p.briefs()]
        self.assertIn("Security is the security seat's job", briefs[0])
        self.assertIn("You are the security seat.", briefs[1])
        approved = p.rail("accept", "1")
        self.assertEqual(approved["reason"]["code"], "MERGE")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")

    def test_the_security_step_says_how_many_blocking_findings_it_sent_to_the_refuter(self):
        leak = {"severity": "blocking", "file": "src/calc.py", "claim": "The result is logged with the user's token."}
        for name, seat, detail in (("leak", found(leak), "run 2: 0 blocking, 1 more blocking to the refuter, 1 findings"),
                                   ("quiet", clean(), "run 2: 0 blocking, 0 findings")):
            with self.subTest(seat=name):
                p = self.fixture(name=name)
                p.add(ticket(tier="PERSON"))
                p.rail("accept", "1")
                p.rail("next")
                p.fix_calc("1")
                p.queue_reviews(clean(), seat, clean("Nothing is logged at all."))
                ready = p.rail("advance", "1")
                security = [s for s in ready["steps"] if s["step"] == "security"][-1]
                self.assertEqual((security["result"], security["detail"]), ("pass", detail))

    def test_invalid_output_twice_waits_for_a_person_and_counts_against_no_one(self):
        p = self.fixture()
        self.medium(p)
        ghost = {"severity": "blocking", "file": "src/missing.py", "claim": "x"}
        p.queue_reviews(found(ghost), {"raw": "not json at all"})
        stuck = p.rail("advance", "1", expect=3)  # the invalid run is started once more at once, like a timeout
        details = [s.get("detail") for s in review_steps(stuck)]
        self.assertIn("src/missing.py isn't a tracked file", details[0])
        self.assertEqual(details[1], "invalid output: the output is not JSON")
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "STUCK_REVIEW"))
        self.assertIn("its output was invalid", stuck["action"]["brief"])
        runs = [e for e in events(p, "1-fix-add", "step") if e["step"] == "review"]
        self.assertEqual([e.get("counted") for e in runs], [False, False])  # the worker ladder reads only counted ones
        self.assertEqual(p.rail("accept", "1", "the reviewer's schema was out of date")["reason"]["code"], "REVIEW")

    def test_invalid_output_once_then_a_valid_review_carries_on_with_the_ladder_where_it_was(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews({"raw": "garbage"}, found(BLOCKING))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual([s.get("detail") for s in review_steps(failed)],
                         ["invalid output: the output is not JSON", "run 1: 1 blocking, 1 findings"])
        self.assertEqual(failed["reason"]["code"], "ANSWER_FINDINGS")
        # One counted failure, the blocking run: the ladder's second rung, as without the invalid run.
        self.assertEqual((failed["action"]["model"], failed["action"]["effort"]), ("claude-sonnet-5-5", "high"))

    def test_the_worktree_is_reset_after_each_run(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews({"touch": "scratch_test.py", **clean()})
        p.rail("advance", "1")
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")

    PROBE = "grep -c 'reviewer was here' src/calc.py\necho \"probe ran at $(date +%s)\"\n"

    def test_the_engine_reruns_evidence_with_the_scratch_file_and_without_the_tracked_edit(self):
        p = self.fixture()
        self.medium(p)
        quoted = {"command": "sh probe.sh", "output": "probe ran at 1700000000"}
        p.queue_reviews({"touch": "probe.sh", "script": self.PROBE, **found(BLOCKING | {"evidence": quoted})})
        failed = p.rail("advance", "1", expect=3)
        evidence = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))["runs"][0]["findings"][0]["evidence"]
        self.assertEqual(evidence["rerun"]["exit"], 0)
        self.assertTrue(evidence["rerun"]["output_tail"].startswith("0\n"))  # the reviewer's edit to calc.py is gone
        self.assertTrue(evidence["reproduced"])  # the number differs, and normalises away
        self.assertEqual(evidence["scripts"], {"probe.sh": self.PROBE})
        self.assertIn("probe.sh, the reviewer's scratch file", failed["action"]["brief"])
        self.assertIn("grep -c 'reviewer was here' src/calc.py", failed["action"]["brief"])
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")

    def test_evidence_that_does_not_reproduce_is_recorded_and_the_finding_stays(self):
        p = self.fixture()
        self.medium(p)
        quoted = {"command": "sh probe.sh", "output": "add(-1, 1) == 2"}
        p.queue_reviews({"touch": "probe.sh", "script": self.PROBE, **found(BLOCKING | {"evidence": quoted})})
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed["reason"]["code"], "ANSWER_FINDINGS")
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertFalse(doc["runs"][0]["findings"][0]["evidence"]["reproduced"])
        self.assertEqual(doc["runs"][0]["findings"][0]["severity"], "blocking")

    def test_an_evidence_rerun_past_the_timeout_is_recorded_and_the_review_stands(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 2"))
        self.medium(p)
        slow = BLOCKING | {"evidence": {"command": "echo started; sleep 30", "output": "started"}}
        p.queue_reviews(found(slow))
        answer = p.rail("advance", "1", expect=3)
        # The run is not a timeout: its blocking finding holds the ticket, as without the slow evidence.
        self.assertEqual((review_steps(answer)[-1]["detail"], answer["reason"]["code"]),
                         ("run 1: 1 blocking, 1 findings", "ANSWER_FINDINGS"))
        evidence = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))["runs"][0]["findings"][0]["evidence"]
        self.assertEqual((evidence["rerun"]["exit"], evidence["reproduced"]), (None, False))
        self.assertIn("started", evidence["rerun"]["output_tail"])

    def test_invalid_output_still_resets_the_worktree(self):
        p = self.fixture()
        self.medium(p)
        p.queue_reviews({"touch": "probe.sh", **found({"severity": "blocking", "file": "src/missing.py", "claim": "x"})})
        p.rail("advance", "1", expect=3)
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")

    def test_two_timeouts_wait_for_a_person(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 2"))
        self.medium(p)
        p.queue_reviews("timeout", "timeout")
        stuck = p.rail("advance", "1", expect=3)
        self.assertEqual([s.get("detail") for s in stuck["steps"] if s["step"] == "review"], ["timeout", "timeout"])
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "STUCK_REVIEW"))
        timeouts = [e for e in events(p, "1-fix-add", "step") if e["step"] == "review"]
        self.assertEqual([e.get("counted") for e in timeouts], [False, False])
        self.assertEqual(p.rail("accept", "1", "the test server waited on stdin")["reason"]["code"], "REVIEW")


class Retry(RailTest):
    def test_at_the_budget_consult_advises_then_a_person_continues(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)
        p.write("src/calc.py", "def add(a, b):\n    return a * b\n", base=p.worktree("1"))
        second = p.rail("advance", "1", expect=3)
        self.assertIn("consult says change: The check expects a + b.", second["action"]["brief"])
        consulted = events(p, "1-fix-add", "consulted")[0]
        self.assertEqual((consulted["trigger"], consulted["step"], consulted["verdict"], consulted["same_model"]),
                         ("retry_cap", "checks", "change", False))
        advice = p.git("show", "1-fix-add:.rail/journal/1-advice.md")
        self.assertIn("retry_cap at 'checks', change", advice)
        p.write("src/calc.py", "def add(a, b):\n    return a ** b\n", base=p.worktree("1"))
        capped = p.rail("advance", "1", expect=3)
        self.assertEqual((capped["owner"], capped["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertEqual(p.rail("next")["reason"]["code"], "WAITING_HUMAN")
        p.rail("accept", "1", "the check wants plain addition")
        continued = p.rail("next")
        self.assertEqual(continued["reason"]["code"], "STEP_FAILED")
        self.assertIn('A person said: "the check wants plain addition".', continued["action"]["brief"])
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")

    def test_approving_an_amend_gives_a_fresh_budget(self):
        p = self.fixture(config=CONFIG.replace("[commands]", "[commands]").replace("timeout_secs = 60", "timeout_secs = 60")
                         .replace("[consult]", "[retry]\nbudget = 1\n\n[consult]"))
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        p.rail("advance", "1", expect=3)  # the check fails: the budget of 1 is used, consult advises
        p.rail("advance", "1", expect=3)  # the attempt after consult fails too
        self.assertEqual(p.rail("next")["reason"]["code"], "WAITING_HUMAN")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace("== 5", "== 5 and calc.add(1, 1) == 2"), base=p.worktree("1"))
        self.assertEqual(p.rail("amend", "1")["reason"]["code"], "APPROVE_AMEND")
        approved = p.rail("accept", "1")
        self.assertNotEqual(approved["owner"], "human", approved["reason"]["code"] + " " + approved["action"]["brief"][:300])

    def calc(self, p, body):
        p.write("src/calc.py", f"def add(a, b):\n    {body}\n", base=p.worktree("1"))

    def test_the_same_failure_twice_makes_consult_due_and_two_different_ones_do_not(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)  # AssertionError
        self.calc(p, "return a + c")      # NameError: a new failure is progress
        second = p.rail("advance", "1", expect=3)
        self.assertEqual((second["owner"], second["reason"]["code"]), ("agent", "STEP_FAILED"))
        self.assertNotIn("consult says", second["action"]["brief"])
        self.assertEqual(events(p, "1-fix-add", "consulted"), [])
        third = p.rail("advance", "1", expect=3)  # the NameError again, with nothing changed
        self.assertIn("consult says change", third["action"]["brief"])
        fails = [e for e in events(p, "1-fix-add", "step") if e["step"] == "checks"]
        self.assertTrue(all(e["signature"].startswith("checks:") for e in fails))
        self.assertNotEqual(fails[0]["signature"], fails[1]["signature"])
        self.assertEqual(fails[1]["signature"], fails[2]["signature"])

    def test_the_cap_sends_new_failures_to_a_person_and_a_person_resets_budget_and_cap(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)  # 1: AssertionError
        for n, body in enumerate(["return a + c", "return a - b", "return a + c"], 2):
            self.calc(p, body)
            self.assertEqual(p.rail("advance", "1", expect=3)["reason"]["code"], "STEP_FAILED", n)
        self.calc(p, "return a - b")
        capped = p.rail("advance", "1", expect=3)  # 5: never the same twice in a row, and still a person looks
        self.assertEqual((capped["owner"], capped["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'checks' failed 5 times since it last passed, whatever the output ([retry] cap)",
                      capped["action"]["brief"])
        self.assertEqual(events(p, "1-fix-add", "consulted"), [])
        p.rail("accept", "1", "read the check")
        after = p.rail("advance", "1", expect=3)  # the same failure as the fifth: a fresh budget counts it once
        self.assertEqual((after["owner"], after["reason"]["code"]), ("agent", "STEP_FAILED"))
        self.assertNotIn("consult says", after["action"]["brief"])
        again = p.rail("advance", "1", expect=3)
        self.assertIn("consult says change", again["action"]["brief"])
        stuck = p.rail("advance", "1", expect=3)
        self.assertEqual((stuck["owner"], stuck["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("'checks' failed the same way 2 times in a row, then once more after consult ([retry] budget)",
                      stuck["action"]["brief"])

    def test_consult_on_request(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        asked = p.rail("consult", "1", "Is a + b the right fix?")
        self.assertIn("consult says change", asked["advice"])
        # A wrong check the agent can amend is not a "stop": the pack's brief says so.
        self.assertIn("a check that is plainly wrong is not\n                    one: the agent amends it with rail amend",
                      [b for b in p.briefs() if b["consult"]][0]["brief"])
        self.assertEqual(events(p, "1-fix-add", "consulted")[0]["trigger"], "request")


class Contract(RailTest):
    def test_weakening_a_check_after_claim_fails_until_amended(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        weaker = read(path).replace("assert calc.add(2, 3) == 5", "assert calc.add(0, 0) == 0")
        p.write(".rail/tickets/1.md", weaker, base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertIn("differs from the accepted one; change it with rail amend 1", failed["steps"][0]["detail"])
        amended = p.rail("amend", "1")
        self.assertEqual(amended["state"], "implementing")
        record = events(p, "1-fix-add", "amended")[0]
        self.assertEqual((record["changed"], record["needs_approval"]), (["done_contract"], False))
        empty = p.rail("advance", "1", expect=3)  # the weaker check passes with no work done: nothing to ship
        self.assertEqual([s["step"] for s in empty["steps"] if s.get("result") == "fail"], ["change"])
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        # Nobody approved the amend, so the reviewer also gets the contract as first accepted.
        brief = p.briefs()[0]["brief"]
        self.assertIn("## The contract as first accepted\nAn amend nobody approved changed", brief)
        self.assertIn("assert calc.add(2, 3) == 5", brief.split("## The contract as first accepted")[1].split("## The diff")[0])

    def test_lowering_the_tier_after_claim_fails(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        p.fix_calc("1")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace('tier = "PERSON"', 'tier = "AUTO"'), base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertIn("below the accepted PERSON", failed["steps"][0]["detail"])
        self.assertEqual(p.rail("amend", "1", expect=2)["reason"]["message"], "the tier can't go below the accepted PERSON")

    def test_a_person_tickets_done_contract_change_needs_approval_and_a_wider_scope_does_not(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace('["src/**"]', '["src/**", "api/**"]'), base=p.worktree("1"))
        widened = p.rail("amend", "1")
        self.assertEqual(widened["reason"]["code"], "IMPLEMENT")
        self.assertEqual(events(p, "1-fix-add", "amended")[0]["added_paths"], ["api/**"])
        text = read(path).replace("== 5", "== 5 and calc.add(0, 0) == 0")
        p.write(".rail/tickets/1.md", text, base=p.worktree("1"))
        waiting = p.rail("amend", "1")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("human", "APPROVE_AMEND"))
        self.assertEqual(p.rail("accept", "1")["reason"]["code"], "IMPLEMENT")


class Bugs(RailTest):
    def test_a_hand_written_review_file_is_ignored_and_the_reviewer_runs(self):
        p = self.fixture()
        p.add(ticket(tier="AUTO"))
        p.rail("next")
        p.fix_calc("1")
        fake = {"schema": "review/v1", "ticket": "1", "runs": [{"run": 1, "role": "review", "patch_id": "x", "findings": []}]}
        p.write(".rail/journal/1-review.json", json.dumps(fake), base=p.worktree("1"))
        p.rail("advance", "1")
        self.assertEqual(len(p.briefs()), 1)
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertEqual(doc["runs"][0]["patch_id"] != "x", True)

    def test_a_commit_after_the_review_is_reviewed_again(self):
        p = self.fixture()
        p.add(ticket(tier="AUTO"))
        p.rail("next")
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # changed after review\n", base=p.worktree("1"))
        p.git("commit", "--quiet", "-am", "1: sneak", cwd=p.worktree("1"))
        self.assertEqual(p.rail("next")["state"], "implementing")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(p.briefs()), 2)

    def test_rules_check_added_lines_even_with_color_ui_always(self):
        rules = '\n[[rules]]\nid = "no-new-suppressions"\nforbid = ["eslint-disable", "@ts-ignore", "# noqa", ".skip("]\n' \
                'fix = "Fix the cause instead of silencing the check."\n'
        p = self.fixture(config=CONFIG + rules)
        p.git("config", "color.ui", "always")
        p.add(ticket())
        p.rail("next")
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # noqa\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        step = [s for s in failed["steps"] if s.get("result") == "fail"][0]
        self.assertEqual((step["step"], step["detail"]), ("rules", "1 broken: no-new-suppressions"))
        self.assertIn("Fix the cause instead of silencing the check.", failed["action"]["brief"])
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")

    def test_the_seeds_shortcut_rule_refuses_a_marker_without_its_ticket(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "config.toml")) as f:
            rule = "\n[[rules]]\n" + f.read().split("[[rules]]")[2]  # the second rule of the seed, as it ships
        self.assertIn("shortcut-names-its-ticket", rule)
        p = self.fixture(config=CONFIG + rule)
        p.add(ticket())
        p.rail("next")
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # SHORTCUT: ints only\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        step = [s for s in failed["steps"] if s.get("result") == "fail"][0]
        self.assertEqual((step["step"], step["detail"]), ("rules", "1 broken: shortcut-names-its-ticket"))
        self.assertIn("this ticket's number", failed["action"]["brief"])
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # SHORTCUT(1): ints only; use Decimal for money\n",
                base=p.worktree("1"))
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")


class Shape(RailTest):
    def test_only_in_keeps_new_files_in_their_home(self):
        rule = '\n[[rules]]\nid = "migrations-home"\nfiles = "**/*.sql"\nonly_in = "db/migrations/**"\nfix = "Use make migration."\n'
        p = self.fixture(config=CONFIG + rule)
        p.add(ticket(scope=("src/**",)))
        p.rail("next")
        p.fix_calc("1")
        p.write("src/schema.sql", "create table t (id int);\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertIn("is a new file outside db/migrations/**", failed["action"]["brief"])

    def test_over_the_size_cap_an_auto_ticket_becomes_person_and_lockfiles_do_not_count(self):
        p = self.fixture(config=CONFIG + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/package-lock.json", "{}\n" * 50, base=p.worktree("1"))
        p.write("src/gen.py", "x = 1\n" * 40, base=p.worktree("1"))
        p.write(".gitattributes", "src/gen.py linguist-generated\n")
        p.git("add", ".gitattributes")
        p.git("commit", "--quiet", "-m", "generated files")
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("size", brief)
        p.write("src/more.py", "".join(f"x{i} = {i}\n" for i in range(12)), base=p.worktree("1"))
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "SPLIT")  # offered a split first
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["tier"], shipped["reason"]["code"]), ("PERSON", "MERGE_BY_PERSON"))  # too much to merge unread
        raised = events(p, "1-fix-add", "tier_raised")[0]
        self.assertEqual((raised["reason"], raised["to"], raised["detail"]),
                         ("size", "PERSON", "14 changed lines, over the cap of 10"))
        size = [s for s in shipped["steps"] if s["step"] == "size"][0]
        self.assertEqual(size["detail"], "size 14/10")

    def test_the_migration_brief_comes_with_a_migration_ticket(self):
        p = self.fixture(files={"db/migrations/001.sql": "create table t (id int);\n"})
        p.add(ticket(scope=("db/**", "src/**")))
        p.rail("accept", "1")
        self.assertIn("Migrations: expand, then contract.", p.rail("next")["action"]["brief"])


class Split(RailTest):
    BIG = "".join(f"x{i} = {i}\n" for i in range(12))

    def over_the_cap(self, config=CONFIG):
        p = self.fixture(config=config + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/more.py", self.BIG, base=p.worktree("1"))
        return p

    def test_over_the_cap_an_auto_ticket_is_offered_a_split_once_then_becomes_person(self):
        p = self.over_the_cap()
        offered = p.rail("advance", "1")
        self.assertEqual((offered["state"], offered["owner"], offered["tier"], offered["reason"]["code"]),
                         ("implementing", "agent", "AUTO", "SPLIT"))
        brief = offered["action"]["brief"]
        for text in ("This change is 14 lines, over [size] cap of 10.", "git branch split/1-rest", "rail amend 1",
                     'after = ["1"]', "split from ticket 1", "the ticket becomes PERSON and a person merges it"):
            self.assertIn(text, brief)
        # Not a failure: no step failed, so no attempt is spent and the model ladder stays at its first rung.
        self.assertEqual([s["step"] for s in offered["steps"] if s.get("result") == "fail"], [])
        self.assertEqual(offered["action"]["effort"], "medium")
        self.assertEqual([s["status"] for s in offered["steps"] if s["step"] in ("verify", "checks")], ["not_run"] * 2)
        self.assertEqual(events(p, "1-fix-add", "tier_raised"), [])
        split = events(p, "1-fix-add", "split_offered")
        self.assertEqual([(e["size"], e["cap"]) for e in split], [(14, 10)])
        self.assertEqual(p.rail("next")["reason"]["code"], "SPLIT")
        # The agent can't split it: advance as it is.
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["tier"], shipped["reason"]["code"]),
                         ("merge-ready", "PERSON", "MERGE_BY_PERSON"))
        self.assertEqual([e["reason"] for e in events(p, "1-fix-add", "tier_raised")], ["size"])
        self.assertEqual(len(events(p, "1-fix-add", "split_offered")), 1)
        # CI agrees with the ship: the patch shipped as PERSON, and CI neither offers a split nor fails on the size.
        ci = os.path.join(self.tmp, "ci")
        subprocess.run(["git", "clone", "--quiet", p.root, ci], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", "1-fix-add").strip()], cwd=ci, check=True)
        result = subprocess.run([os.path.join(ci, ".rail", "bin", "rail"), "ci", "--json"], cwd=ci, capture_output=True,
                                text=True, env=dict(os.environ, RAIL_BRANCH="1-fix-add"))
        self.assertEqual((result.returncode, json.loads(result.stdout)["tier"]), (0, "PERSON"), result.stdout)

    def test_the_offer_is_made_once_even_for_a_changed_patch(self):
        p = self.over_the_cap()
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "SPLIT")
        p.write("src/more.py", self.BIG + "y = 1\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["tier"], shipped["reason"]["code"]), ("PERSON", "MERGE_BY_PERSON"))
        self.assertEqual(len(events(p, "1-fix-add", "split_offered")), 1)

    def test_a_split_under_the_cap_ships_auto_with_a_narrowed_contract(self):
        p = self.over_the_cap()
        p.rail("advance", "1")
        wt = p.worktree("1")
        p.git("branch", "split/1-rest", cwd=wt)
        p.git("rm", "--quiet", "src/more.py", cwd=wt)
        p.git("commit", "--quiet", "-m", "keep the first part", cwd=wt)
        with open(os.path.join(wt, ".rail/tickets/1.md")) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace("calc.add(2, 3) == 5", "calc.add(1, 1) == 2"), base=wt)
        amended = p.rail("amend", "1")  # an AUTO ticket's narrowed contract needs no person
        self.assertEqual((amended["owner"], amended["tier"]), ("agent", "AUTO"))
        self.assertFalse(events(p, "1-fix-add", "amended")[-1]["needs_approval"])
        rest = ticket(title="Add more", front=('after = ["1"]',),
                      body="\n## Request\nSplit from ticket 1.\n\n## Look at\nThe code is on split/1-rest.\n")
        self.assertEqual(p.add(rest)["reason"]["code"], "WAITING_AFTER")
        p.queue_reviews(clean())
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["tier"]), ("merge-ready", "AUTO"))
        self.assertEqual(events(p, "1-fix-add", "tier_raised"), [])
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["split"], {"offered": 1, "auto": 1, "person": 0})
        self.assertIn("Offered a split over [size] cap: 1. Shipped AUTO afterwards: 1; became PERSON for size: 0.",
                      stats["text"])

    def test_a_person_path_over_the_cap_is_raised_at_once_with_no_offer(self):
        p = self.over_the_cap(config='person_paths = ["**/*.sql"]\n' + CONFIG)
        p.write("src/report.sql", "select 1;\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["tier"], shipped["reason"]["code"]), ("PERSON", "MERGE_BY_PERSON"))
        self.assertEqual([e["reason"] for e in events(p, "1-fix-add", "tier_raised")], ["person_paths"])
        self.assertEqual(events(p, "1-fix-add", "split_offered"), [])


class CIReview(RailTest):
    def test_ci_needs_a_complete_review_for_the_patch(self):
        p = self.fixture()
        p.add(ticket(tier="AUTO"))
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(found(BLOCKING))
        p.rail("advance", "1", expect=3)
        ci = os.path.join(self.tmp, "ci")
        subprocess.run(["git", "clone", "--quiet", p.root, ci], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", "1-fix-add").strip()], cwd=ci, check=True)
        result = subprocess.run([os.path.join(ci, ".rail", "bin", "rail"), "ci", "--json"], cwd=ci, capture_output=True,
                                text=True, env=dict(os.environ, RAIL_BRANCH="1-fix-add"))
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertEqual(json.loads(result.stdout)["steps"][-1]["detail"], "no complete review for this patch")


class Answer(RailTest):
    def test_a_decline_needs_a_reason_and_a_finding_must_exist(self):
        p = self.fixture()
        p.add(ticket(tier="AUTO"))
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(found(ADVISORY))
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")  # an open advisory holds nothing, yet takes an answer
        self.assertEqual(p.rail("answer", "1", "F1", "declined", expect=2)["reason"]["message"], "a decline needs a reason")
        self.assertEqual(p.rail("answer", "1", "F9", "fixed", expect=2)["reason"]["code"], "NO_FINDING")
        self.assertEqual(p.rail("answer", "1", "f1", "parked", "Old code.")["state"], "merge-ready")


class Guidance(RailTest):
    def test_review_md_at_the_root_and_above_a_changed_file_reaches_every_brief_and_others_stay_out(self):
        p = self.fixture(files={"REVIEW.md": "Always flag a float used for money.\n",
                                "src/REVIEW.md": "Never report the order of arguments.\n",
                                "api/REVIEW.md": "Flag every new endpoint.\n"})
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(clean(), clean())
        p.rail("advance", "1")
        briefs = [b["brief"] for b in p.briefs()]
        self.assertEqual(len(briefs), 2)  # the review and the security seat
        for brief in briefs:
            self.assertIn("## The project's review guidance (from REVIEW.md)", brief)
            root = brief.index("For the whole repository (REVIEW.md):\nAlways flag a float used for money.")
            self.assertLess(brief.index("## The project's conventions (from AGENTS.md)"), root)
            self.assertLess(root, brief.index("For src/ (src/REVIEW.md):\nNever report the order of arguments."))
            self.assertNotIn("Flag every new endpoint.", brief)

    def test_without_review_md_the_section_is_left_out(self):
        p = self.fixture()
        Review.medium(self, p)
        p.rail("advance", "1")
        self.assertNotIn("review guidance", p.briefs()[0]["brief"])

    def test_review_md_is_cut_at_the_cap_and_the_brief_says_which_files(self):
        p = self.fixture(files={"REVIEW.md": "r" * 5000 + "\n", "src/REVIEW.md": "s" * 5000 + "TAIL\n"})
        Review.medium(self, p)
        p.rail("advance", "1")
        brief = p.briefs()[0]["brief"]
        self.assertIn("r" * 5000, brief)
        self.assertIn("s" * 3000, brief)
        self.assertNotIn("TAIL", brief)
        self.assertIn("(Cut at 8000 characters: src/REVIEW.md.)", brief)


class BaseGreen(RailTest):
    LINE = "Every check in the Done Contract already passed on the base branch before this work began"

    def test_when_every_check_was_green_on_the_base_the_review_brief_says_so(self):
        p = self.fixture()
        Review.medium(self, p, check="grep -q add src/calc.py")
        p.rail("advance", "1")
        brief = p.briefs()[0]["brief"]
        self.assertIn("scope_paths: src/**.\n\n" + self.LINE, brief)
        self.assertIn("Look at whether the change is tested.\n\n## The diff", brief)

    def test_a_check_red_on_the_base_leaves_the_line_out(self):
        p = self.fixture()
        p.add(ticket(body="- Check: `grep -q add src/calc.py`\n"))  # one green, one red
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        self.assertNotIn(self.LINE, p.briefs()[0]["brief"])


class NeedsPerson(RailTest):
    ASKED = "It adds the first retry wrapper, which other calls will copy."

    def test_a_reviewer_asking_for_a_person_makes_an_auto_ticket_person(self):
        p = self.fixture()
        Review.medium(self, p)
        p.queue_reviews(clean() | {"needs_person": self.ASKED}, clean(), clean())
        ready = p.rail("advance", "1")
        # From the raise on, it is a PERSON ticket: the security seat runs, and a person merges.
        self.assertEqual((ready["state"], ready["tier"], ready["reason"]["code"]), ("merge-ready", "PERSON", "MERGE_BY_PERSON"))
        self.assertEqual([s["step"] for s in ready["steps"]][-2:], ["review", "security"])
        self.assertIn("The reviewer asked for a person: " + self.ASKED, ready["action"]["brief"])
        raised = events(p, "1-fix-add", "tier_raised")
        self.assertEqual([(e["from"], e["to"], e["reason"], e["detail"]) for e in raised],
                         [("AUTO", "PERSON", "reviewer", self.ASKED)])
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertEqual(doc["runs"][0]["needs_person"], self.ASKED)
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertIn("The reviewer asked for a person: " + self.ASKED, p.git("log", "-1", "--format=%b", "main"))
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["raised"], {"reviewer": 1})
        self.assertEqual(stats["stats"]["tiers"]["PERSON"]["merged"], 1)
        self.assertIn("Became PERSON at ship or review: 1 (reviewer 1).", stats["text"])

    def test_on_a_person_ticket_it_is_recorded_and_changes_nothing_else(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(clean() | {"needs_person": self.ASKED}, clean() | {"needs_person": ""})
        ready = p.rail("advance", "1")
        self.assertEqual((ready["state"], ready["tier"], ready["reason"]["code"]), ("merge-ready", "PERSON", "MERGE_BY_PERSON"))
        self.assertEqual(events(p, "1-fix-add", "tier_raised"), [])
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertEqual([r.get("needs_person") for r in doc["runs"]], [self.ASKED, None])
        self.assertIn("The reviewer asked for a person: " + self.ASKED, ready["action"]["brief"])
