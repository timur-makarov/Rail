"""rail stats: what the journals of merged tickets say about the work and about the reviewer."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import ARCHITECTURE, CONFIG, RailTest, ticket

BLOCKING = {"severity": "blocking", "file": "src/calc.py", "line": 1, "claim": "add breaks on None."}
ADVISORY = {"severity": "advisory", "file": "src/calc.py", "claim": "add has no docstring."}
LEAK = {"severity": "blocking", "file": "api/handlers.py", "line": 1, "claim": "201 leaks the row count."}


def clean():
    return {"summary": "Read the diff, ran the check.", "findings": []}


class Stats(RailTest):
    def project(self):
        """Three merged tickets: an AUTO one the reviewer read, an AUTO one inside skip_paths, and a PERSON one."""
        config = 'person_paths = ["api/**"]\n' + CONFIG.replace("[review]", '[review]\nskip_paths = ["docs/**"]')
        p = self.fixture(config=config, files={"docs/guide.md": "# Guide\n",
                                               "ARCHITECTURE.md": ARCHITECTURE + "| docs | docs/** | the guide |\n"})
        # 1: the check fails once, the reviewer finds a blocking and an advisory finding, the author fixes one and
        # declines the other.
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)
        p.fix_calc("1")
        p.queue_reviews({"summary": "Found two.", "findings": [BLOCKING, ADVISORY]}, clean())
        p.rail("advance", "1", expect=3)
        p.write("src/calc.py", "def add(a, b):\n    return (a or 0) + (b or 0)\n", base=p.worktree("1"))
        p.rail("answer", "1", "F1", "fixed", "None counts as 0.")
        p.rail("answer", "1", "F2", "declined", "The project has no docstrings.")
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        # 2: a docs change, which [review] skip_paths lets merge with no reviewer.
        p.add(ticket(title="Explain sum", scope=("docs/**",), check="grep -q sum docs/guide.md"))
        p.rail("next")
        p.write("docs/guide.md", "# Guide\nsum\n", base=p.worktree("2"))
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        # 3: a PERSON ticket. The security seat's blocking finding goes to the refuter, who dismisses it.
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("accept", "3")
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("3"))
        p.queue_reviews(clean(), {"summary": "One leak.", "findings": [LEAK]}, {"summary": "No leak.", "findings": []})
        self.assertEqual(p.rail("advance", "3")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "3")
        self.assertEqual(p.rail("advance", "3")["state"], "merged")
        return p

    def test_the_numbers_come_from_the_journals_of_merged_tickets(self):
        p = self.project()
        p.add(ticket(title="Not started", scope=("src/**",)))
        answer = p.rail("stats")
        self.assertEqual(answer["reason"]["code"], "STATS")
        stats = answer["stats"]
        self.assertEqual((stats["merged"], stats["left_out"]), (3, 1))
        auto, person = stats["tiers"]["AUTO"], stats["tiers"]["PERSON"]
        self.assertEqual((auto["merged"], auto["reviewed"], auto["no_person"], auto["first_try"]), (2, 1, 2, 1))
        self.assertEqual((person["merged"], person["reviewed"], person["no_person"], person["first_try"]), (1, 1, 0, 1))
        self.assertIsNotNone(auto["median_minutes"])
        self.assertEqual(stats["steps"]["checks"], {"runs": 5, "failed": 1, "could_not_run": 0})
        self.assertEqual(stats["steps"]["review"], {"runs": 3, "failed": 1, "could_not_run": 0})
        review = stats["review"]
        self.assertEqual({role: row["runs"] for role, row in review["roles"].items()},
                         {"review": 3, "security": 1, "refuter": 1})
        self.assertEqual(review["cost_usd"], 0.05)
        self.assertEqual(review["models"], {"fake-model": {"runs": 5, "cost_usd": 0.05, "blocking": 2, "fixed": 1}})
        self.assertEqual(review["blocking"], {"total": 2, "fixed": 1, "dismissed": 1})
        self.assertEqual(review["advisory"], {"total": 1, "declined": 1})
        self.assertEqual(review["disputes"], {"dismissed": 1})
        self.assertEqual(review["hit_rate"], 0.5)

        text = p.rail("stats", raw=True).stdout
        for line in ("Rail stats: 3 merged tickets. Not counted: 1 not merged.",
                     "TICKETS                   AUTO  PERSON",
                     "merged with no review        1       0",
                     "checks                5       1              0",
                     "total        5  $0.05",
                     "$0.03 for each ticket the reviewer read.",
                     "fake-model     5  $0.05         2      1",
                     "Blocking findings: 2. Fixed 1, dismissed by the refuter 1.",
                     "Hit rate: 50% of the decided ones ended in a fix.",
                     "Advisory findings: 1. Declined 1.",
                     "Disputes: 1. The refuter dismissed 1."):
            self.assertIn(line, text)
        self.assertEqual(p.git("status", "--porcelain"), "")  # stats only reads

    def test_since_counts_only_what_merged_from_that_day_on(self):
        p = self.project()
        self.assertEqual(p.rail("stats", "--since", "2020-01-01")["stats"]["merged"], 3)
        later = p.rail("stats", "--since", "2100-01-01")
        self.assertEqual((later["stats"]["merged"], later["stats"]["left_out"]), (0, 3))
        self.assertEqual(later["text"], "No ticket has merged since 2100-01-01, so there is nothing to count yet.")
        failed = p.rail("stats", "--since", "soon", expect=2)
        self.assertIn("--since takes a date like 2026-01-31, not 'soon'", failed["reason"]["message"])

    def test_a_ticket_that_became_person_at_ship_is_counted_under_person_with_the_reason(self):
        p = self.fixture(config=CONFIG + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/more.py", "".join(f"x{i} = {i}\n" for i in range(12)), base=p.worktree("1"))
        p.queue_reviews(clean(), clean())
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["raised"], {"size": 1})
        self.assertEqual((stats["stats"]["tiers"]["AUTO"]["merged"], stats["stats"]["tiers"]["PERSON"]["merged"]), (0, 1))
        self.assertIn("Became PERSON at ship: 1 (size 1).", stats["text"])
        self.assertIn("No step failed.", stats["text"])

    def test_with_nothing_merged_only_where_the_tickets_came_from_is_counted(self):
        p = self.fixture()
        self.assertEqual(p.rail("stats")["text"], "No ticket has merged, so there is nothing to count yet.")
        p.add(ticket())
        answer = p.rail("stats")
        self.assertEqual(answer["stats"]["merged"], 0)
        self.assertTrue(answer["text"].startswith("Rail stats: no ticket has merged yet."))
        self.assertEqual(answer["stats"]["grilling"]["groups"]["not grilled"]["open"], 1)
        self.assertEqual(list(answer["stats"]["grilling"]["channels"]), ["session"])
        self.assertIn("GRILLING", answer["text"])
