"""rail stats: what the journals of merged tickets say about the work and about the reviewer."""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import ARCHITECTURE, CONFIG, RailTest, ticket

BLOCKING = {"severity": "blocking", "file": "src/calc.py", "line": 1, "claim": "add breaks on None."}
ADVISORY = {"severity": "advisory", "file": "src/calc.py", "claim": "add has no docstring."}
LEAK = {"severity": "blocking", "file": "api/handlers.py", "line": 1, "claim": "201 leaks the row count.",
        "evidence": {"command": "echo no leak", "output": "rows: 3 leaked"}}  # the re-run doesn't show it


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
        shown = BLOCKING | {"evidence": {"command": "echo 'add(None, 1) raised at 0x1f'", "output": "add(None, 2) raised"}}
        p.queue_reviews({"summary": "Found two.", "findings": [shown, ADVISORY]}, clean())
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
        self.assertEqual(review["refuter_overturns"], 1.0)
        self.assertEqual(review["rounds"], {"tickets": 2, "median": 1.5, "one_run": 0.5})  # 1 ran twice, 3 once
        self.assertEqual(review["evidence"], {"rerun": 2, "reproduced": 1, "share": 0.5})
        self.assertEqual(stats["person_changed_nothing"], {"at add": {"tickets": 1, "changed_nothing": 1}})

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
                     "Disputes: 1. The refuter dismissed 1. Refuter overturns: 100%.",
                     "Rounds to pass: median 1.5 review runs for each ticket the reviewer read; 50% merged after one run.",
                     "Evidence reproduced: 1 of 2 blocking findings whose evidence the engine ran again (50%).",
                     "PERSON tickets where the person changed nothing, by why they were PERSON: at add 1 of 1."):
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
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "SPLIT")
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["raised"], {"size": 1})
        self.assertEqual(stats["stats"]["split"], {"offered": 1, "auto": 0, "person": 1})
        self.assertEqual((stats["stats"]["tiers"]["AUTO"]["merged"], stats["stats"]["tiers"]["PERSON"]["merged"]), (0, 1))
        self.assertIn("Became PERSON at ship or review: 1 (size 1).", stats["text"])
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


def engine_stats():
    """The stats module of the engine the launcher under test runs."""
    import railtest
    engine = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(railtest.RAIL))), "engine")
    if engine not in sys.path:
        sys.path.insert(0, engine)
    from rail import stats
    return stats


def journal(*events):
    return SimpleNamespace(events=[{"event": kind, **fields} for kind, fields in events])


APPROVED = ("accepted", {"by": "person", "tier": "PERSON"})


class PersonChangedNothing(RailTest):
    def test_why_a_ticket_was_person_and_whether_the_person_changed_anything(self):
        stats = engine_stats()
        cases = {
            # The contract approved before the work and the merge approved with no note: nothing changed, although
            # the agent shipped twice after the approval.
            "approved and merged": (journal(APPROVED, ("shipped", {"patch_id": "a"}), ("shipped", {"patch_id": "b"}),
                                            ("continued", {"via": "accept"})), True, ["at add"]),
            "a note": (journal(("accepted", {"by": "engine", "tier": "AUTO"}), ("shipped", {"patch_id": "a"}),
                               ("tier_raised", {"reason": "person_paths"}), ("continued", {"note": "rename it"})),
                       False, ["person_paths"]),
            "a commit after": (journal(("accepted", {"by": "engine", "tier": "AUTO"}), ("shipped", {"patch_id": "a"}),
                                       ("tier_raised", {"reason": "size"}), ("continued", {}),
                                       ("shipped", {"patch_id": "b"})), False, ["size"]),
            "a rebase after": (journal(("accepted", {"by": "engine", "tier": "AUTO"}), ("shipped", {"patch_id": "a"}),
                                       ("tier_raised", {"reason": "reviewer"}), ("continued", {}),
                                       ("shipped", {"patch_id": "a"})), True, ["reviewer"]),
            "an owner answer": (journal(APPROVED, ("shipped", {"patch_id": "a"}),
                                        ("finding", {"id": "F1", "outcome": "declined", "by": "owner"})), False, ["at add"]),
            "an amend": (journal(APPROVED, ("amended", {"changed": ["done_contract"]}), ("shipped", {"patch_id": "a"})),
                         False, ["at add"]),
        }
        for name, (t, nothing, reasons) in cases.items():
            with self.subTest(name):
                self.assertEqual(stats._person_changed_nothing(t), nothing)
                self.assertEqual(stats._person_reasons(t), reasons)


MUL_CHECK = "python3 -c \"import sys; sys.path.insert(0, 'src'); import mul; assert mul.mul(2, 3) == 6\""


class Reverts(RailTest):
    def test_a_reverted_ticket_and_checks_green_on_the_base_are_counted(self):
        p = self.fixture()
        # 1: its only check is already green on the base, so it can't show the work was done.
        p.add(ticket(check="grep -q add src/calc.py"))
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(clean())
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        # 2: its check is red on the base.
        p.add(ticket(title="Add mul", check=MUL_CHECK))
        p.rail("next")
        p.write("src/mul.py", "def mul(a, b):\n    return a * b\n", base=p.worktree("2"))
        p.queue_reviews(clean())
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        # A person reverts ticket 1 with git revert: its journal leaves the base branch with its code.
        p.git("revert", "--no-edit", p.git("log", "--grep=^Ticket: 1$", "--format=%H", "main").strip())

        stats = p.rail("stats")["stats"]
        self.assertEqual((stats["merged"], stats["tiers"]["AUTO"]["reverted"], stats["tiers"]["PERSON"]["reverted"]),
                         (2, 1, 0))
        self.assertEqual(stats["base_checks"], {"tickets": 2, "all_green": 1})
        text = p.rail("stats", raw=True).stdout
        self.assertRegex(text, r"\nreverted afterwards +1 +0\n")
        self.assertIn("Every check already green on the base: 1 of 2 tickets whose checks ran there before the work.",
                      text)

    def test_a_revert_made_with_githubs_button_counts_by_its_pull_request(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        a.rail("next")
        a.fix_calc("1")
        a.rail("advance", "1")
        github.ci("1-fix-add", "success")
        self.assertEqual(a.rail("advance", "1")["state"], "merged")
        self.assertEqual(a.rail("stats")["stats"]["tiers"]["AUTO"]["reverted"], 0)
        # GitHub's Revert button opens a pull request; its squash says which pull request it reverts.
        b.git("pull", "--quiet")
        b.git("commit", "--quiet", "--allow-empty", "-m", 'Revert "1: fix add" (#2)', "-m", "Reverts acme/app#1")
        b.git("push", "--quiet", "origin", "HEAD:main")
        self.assertEqual(a.rail("stats")["stats"]["tiers"]["AUTO"]["reverted"], 1)
