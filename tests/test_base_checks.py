"""Base checks: at a ticket's first claim, each Check: line runs once on the untouched base, and is recorded."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, CONFIG, RailTest, ticket

# Green on the base, and it leaves a file behind that the engine must clean up.
GREEN_WRITES = "echo scratch > src/scratch.txt && grep -q add src/calc.py"


def base_events(p, nn="1"):
    with open(os.path.join(p.worktree(nn), ".rail", "journal", f"{nn}-events.jsonl")) as f:
        return [e for e in map(json.loads, f) if e["event"] == "base_checks"]


class BaseChecks(RailTest):
    def test_the_first_claim_records_each_check_red_or_green_on_the_base_and_leaves_the_worktree_clean(self):
        p = self.fixture()
        p.add(ticket(body=f"- Check: `{GREEN_WRITES}`\n"))
        claimed = p.rail("next")
        self.assertEqual((claimed["state"], claimed["owner"]), ("implementing", "agent"))
        self.assertNotIn("base_checks", [s["step"] for s in claimed["steps"]])  # a fact, not a step
        [found] = base_events(p)
        self.assertEqual(found["checks"], [{"command": CHECK_ADD, "result": "red"},
                                           {"command": GREEN_WRITES, "result": "green"}])
        self.assertEqual(found["base"], p.git("rev-parse", "main").strip()[:12])
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")
        self.assertFalse(os.path.exists(os.path.join(p.worktree("1"), "src", "scratch.txt")))

    def test_it_runs_once_per_ticket_not_on_a_resume_or_a_takeover(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.rail("next")
        p.rail("next", "--ticket", "1", session="session-b")  # a takeover
        self.assertEqual(len(base_events(p)), 1)

    def test_switched_off_it_records_nothing(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 60\nbase_checks = false"))
        p.add(ticket())
        self.assertEqual(p.rail("next")["state"], "implementing")
        self.assertEqual(base_events(p), [])

    def test_a_check_that_cannot_start_or_runs_too_long_is_recorded_and_next_goes_on(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 2"))
        p.add(ticket(check="no-such-tool-for-rail --check", body="- Check: `sleep 30 && grep -q add src/calc.py`\n"))
        claimed = p.rail("next")
        self.assertEqual((claimed["state"], claimed["owner"], claimed["reason"]["code"]),
                         ("implementing", "agent", "IMPLEMENT"))
        [found] = base_events(p)
        self.assertEqual([c["result"] for c in found["checks"]], ["could_not_run", "timed_out"])
        # Nothing was spent: the ticket's first ship has its whole retry budget.
        self.assertEqual(p.rail("status")["tickets"][0]["owner"], "agent")

    def test_when_every_check_passed_on_the_base_the_brief_asks_for_a_check_that_fails_now(self):
        p = self.fixture()
        p.add(ticket(check="grep -q add src/calc.py"))  # green on the base: add exists, it is only wrong
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("Every Check: above already passed on the base branch", brief)
        self.assertIn('rail amend 1 "why"', brief)
        # Once the contract has a check that was not run on the base, the line goes.
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace("## Done Contract\n", f"## Done Contract\n- Check: `{CHECK_ADD}`\n"),
                base=p.worktree("1"))
        p.rail("amend", "1")
        self.assertNotIn("already passed on the base branch", p.rail("next")["action"]["brief"])

    def test_when_a_check_failed_on_the_base_the_brief_says_nothing_of_it(self):
        p = self.fixture()
        p.add(ticket(body="- Check: `grep -q add src/calc.py`\n"))  # one red, one green
        self.assertNotIn("already passed on the base branch", p.rail("next")["action"]["brief"])
