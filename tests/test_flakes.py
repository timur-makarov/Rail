"""Flaky checks: a command that fails and then passes on the same code still fails the ship, and is named as a flake to
the worker, the reviewer, the sweep and rail stats."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

# The checks would otherwise run on the base at the claim, which is the flaky command's first run.
NO_BASE = CONFIG.replace("timeout_secs = 60", "timeout_secs = 60\nbase_checks = false")
TOLD = ("This command failed, then passed when it was run again on the same code. Find why it is not deterministic;"
        " don't add a retry, a sleep or a skip.")


def events(p, ref, name, nn="1"):
    found = [json.loads(line) for line in p.git("show", f"{ref}:.rail/journal/{nn}-events.jsonl").splitlines()]
    return [e for e in found if e["event"] == name]


class Flakes(RailTest):
    def once(self, name):
        """A check that fails the first time it runs and passes from then on."""
        mark = os.path.join(self.tmp, name)
        return f"sh -c 'test -f {mark} || {{ touch {mark}; exit 1; }}' && grep -q 'a + b' src/calc.py"

    def merge(self, p, nn, check, flaky=True):
        p.add(ticket(title=f"Fix add {nn}", check=check))
        p.rail("next")
        p.write("src/calc.py", f"def add(a, b):\n    return a + b  # {nn}\n", base=p.worktree(nn))
        if flaky:
            p.rail("advance", nn, expect=3)
        p.queue_reviews({"summary": "Clean.", "findings": []})
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

    def test_a_check_that_fails_then_passes_on_the_same_code_still_fails_the_ship(self):
        p = self.fixture(config=NO_BASE)
        check = self.once("mark")
        p.add(ticket(check=check))
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["reason"]["code"], failed["steps"][-1]["step"], failed["steps"][-1]["result"]),
                         ("STEP_FAILED", "checks", "fail"))
        self.assertIn(TOLD, failed["action"]["brief"])
        flake = events(p, "1-fix-add", "flake")
        self.assertEqual([(e["step"], e["command"], e["codes"]) for e in flake], [("checks", check, [1, 0])])
        self.assertEqual(flake[0]["patch_id"], events(p, "1-fix-add", "step")[-1]["patch_id"])
        self.assertIn(TOLD, p.rail("next", "--ticket", "1")["action"]["brief"])
        # Another machine has the journal and not this one's kept output: its brief says so too.
        os.remove(p.path(".git", "rail", "cache", "failure", "1"))
        self.assertIn(TOLD, p.rail("next", "--ticket", "1")["action"]["brief"])
        p.queue_reviews({"summary": "Clean.", "findings": []})
        p.rail("advance", "1")
        brief = p.briefs()[0]["brief"]
        self.assertIn(f"## Flaky checks on this change\nEach of these both failed and passed on this same code.", brief)
        self.assertIn(f"- `{check}`", brief)

    def test_a_check_that_always_fails_is_no_flake(self):
        p = self.fixture(config=NO_BASE)
        p.add(ticket())
        p.rail("next")
        failed = p.rail("advance", "1", expect=3)
        self.assertNotIn("failed, then passed", failed["action"]["brief"])
        self.assertEqual(events(p, "1-fix-add", "flake"), [])

    def test_the_sweep_files_a_ticket_for_a_command_flaky_in_two_tickets_and_stats_count_it(self):
        p = self.fixture(config=NO_BASE + "\n[sweep]\nevery = 3\n")
        self.merge(p, "1", self.once("mark1"))
        self.merge(p, "2", self.once("mark2"))
        other = "sh -c 'exit 0' && grep -q 'a + b' src/calc.py"
        self.merge(p, "3", other, flaky=False)
        self.assertEqual(p.rail("next")["reason"]["code"], "SWEEP")
        swept = p.rail("sweep")
        self.assertEqual(swept["reason"]["code"], "SWEEP_TICKETS")
        self.assertIn("Open one ticket for each flaky check", swept["action"]["brief"])
        with open(os.path.join(p.worktree("4"), ".rail", "journal", "4-summary.md")) as f:
            summary = f.read()
        flaky = summary.split("## Flaky checks\n")[1]
        self.assertIn("both failed and passed on the same code, in 2 tickets (1, 2). Check: `for i in $(seq 20); do sh -c",
                      flaky)
        self.assertEqual(flaky.count("\n- "), 0)  # one line: the two tickets' commands are one command
        rows = p.rail("stats")["stats"]["flakes"]
        self.assertEqual(sorted((r["tickets"], r["flakes"], r["runs"], r["share"]) for r in rows.values()),
                         [(1, 1, 2, 0.5), (1, 1, 2, 0.5)])
        self.assertIn("FLAKES", p.rail("stats", raw=True).stdout)

    def test_one_flake_in_one_ticket_files_nothing(self):
        p = self.fixture(config=NO_BASE + "\n[sweep]\nevery = 1\n")
        self.merge(p, "1", self.once("mark"))
        self.assertEqual(p.rail("next")["reason"]["code"], "SWEEP")
        self.assertEqual(p.rail("sweep")["reason"]["code"], "SWEEP_EMPTY")

    def test_a_pass_and_a_failure_on_one_patch_in_two_ships_is_a_flake_too(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
        from rail import flakes
        step = {"event": "step", "step": "checks", "status": "ran", "patch_id": "a"}
        journal = [dict(step, result="pass", detail="pytest -q"), dict(step, result="fail", detail="pytest -q: exit 1"),
                   dict(step, result="fail", detail="make: command not found", status="could_not_run"),
                   dict(step, step="verify", result="fail", detail="red base", counted=False),
                   dict(step, step="verify", result="pass", detail="exit 0")]
        self.assertEqual(flakes.of(journal), [{"step": "checks", "command": "pytest -q", "patch_id": "a"}])
        self.assertEqual(flakes.runs(journal), {"pytest -q": 2, "verify": 2})
