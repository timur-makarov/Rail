"""rail stats: what the journals of merged tickets say about the work and about the reviewer."""

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import ARCHITECTURE, CONFIG, RailTest, engine, ticket

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
        self.assertEqual(stats["person_changed_nothing"], {"controls": {"tickets": 1, "changed_nothing": 1}})

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
                     "PERSON tickets where the person changed nothing, by why they were PERSON: controls 1 of 1."):
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
        p = self.fixture(config='person_paths = ["**/*.sql"]\n' + CONFIG)
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/report.sql", "select 1;\n", base=p.worktree("1"))
        p.queue_reviews(clean(), clean())
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["raised"], {"person_paths": 1})
        self.assertEqual((stats["stats"]["tiers"]["AUTO"]["merged"], stats["stats"]["tiers"]["PERSON"]["merged"]), (0, 1))
        self.assertIn("Became PERSON at ship or review: 1 (person_paths 1).", stats["text"])
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
    engine()
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
        kinds = {
            # The kinds the ticket held when it was filed, and the one a changed file added at ship.
            "kinds at add": (journal(("accepted", {"by": "person", "tier": "PERSON", "kinds": ["access", "money"]}),
                                     ("tier_raised", {"reason": "kinds", "kind": "data-shape"})),
                             ["access", "money", "data-shape"]),
            "the reviewer": (journal(("accepted", {"by": "engine", "tier": "AUTO", "kinds": []}),
                                     ("tier_raised", {"reason": "reviewer", "kind": "data-exposure",
                                                      "kinds": ["data-exposure", "external-effect"]})),
                             ["data-exposure", "external-effect"]),
        }
        for name, (t, reasons) in kinds.items():
            with self.subTest(name):
                self.assertEqual(stats._person_reasons(t), reasons)
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


class Outcomes(RailTest):
    def history(self, config=CONFIG):
        """Three merged AUTO tickets: 1 is reverted afterwards, and 3 says 2 caused it."""
        p = self.fixture(config=config)
        p.add(ticket(check="grep -q add src/calc.py"))
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(clean())
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        p.add(ticket(title="Add mul", check=MUL_CHECK))
        p.rail("next")
        p.write("src/mul.py", "def mul(a, b):\n    return a * b\n", base=p.worktree("2"))
        p.queue_reviews(clean())
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        p.git("revert", "--no-edit", p.git("log", "--grep=^Ticket: 1$", "--format=%H", "main").strip())
        p.add(ticket(title="mul of None", check=MUL_CHECK.replace("mul.mul(2, 3) == 6", "mul.mul(None, 3) == 0"),
                     front=('caused_by = "2"',)))
        p.rail("next")
        p.write("src/mul.py", "def mul(a, b):\n    return (a or 0) * (b or 0)\n", base=p.worktree("3"))
        p.queue_reviews(clean())
        p.rail("advance", "3")
        self.assertEqual(p.rail("advance", "3")["state"], "merged")
        return p

    def test_what_became_of_the_merged_tickets_comes_first(self):
        p = self.history(CONFIG + "\n[stats]\nheld_days = 0\n")
        out = p.rail("stats")["stats"]["outcomes"]
        auto = out["tiers"]["AUTO"]
        self.assertEqual({k: auto[k] for k in ("merged", "reverted", "caused_fix", "old_enough", "held")},
                         {"merged": 3, "reverted": 1, "caused_fix": 1, "old_enough": 3, "held": 1})  # only 3 held
        self.assertEqual((auto["review_usd"], auto["worker_usd"], auto["cost_per_ticket"]), (0.03, 0.0, 0.01))
        self.assertEqual(auto["acts"], {"total": 0, "median": 0, "none": 3})
        self.assertEqual((out["held_days"], out["names_cause"]), (0, 1))
        self.assertEqual((out["by_worker"], out["by_profile"]), ({}, {}))  # no group of five tickets
        text = p.rail("stats", raw=True).stdout
        self.assertLess(text.index("OUTCOMES"), text.index("TICKETS"))
        self.assertRegex(text, r"\ncaused a fix ticket +1 +0\n")
        self.assertRegex(text, r"\nheld, of those merged 0 days ago or more +1 of 3 +0 of 0\n")
        self.assertRegex(text, r"\ncost for each merged ticket +\$0\.01 +-\n")
        self.assertIn("Merged tickets that name the ticket that caused them (caused_by): 1 of 3.", text)

    def test_a_ticket_merged_today_is_not_yet_counted_as_held(self):
        p = self.history()
        auto = p.rail("stats")["stats"]["outcomes"]["tiers"]["AUTO"]
        self.assertEqual((auto["merged"], auto["old_enough"], auto["held"]), (3, 0, 0))
        self.assertRegex(p.rail("stats", raw=True).stdout, r"\nheld, of those merged 14 days ago or more +0 of 0 +0 of 0\n")

    def test_a_persons_acts_are_counted_for_each_merged_ticket(self):
        p = self.fixture()
        p.add(ticket(title="Add a status code", tier="PERSON", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("accept", "1")
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("1"))
        p.queue_reviews({"summary": "One.", "findings": [ADVISORY | {"file": "api/handlers.py"}]},
                        {"summary": "No leak.", "findings": []})
        p.rail("advance", "1")
        self.assertEqual(p.rail("answer", "1", "F1", "parked", "--owner")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        person = p.rail("stats")["stats"]["outcomes"]["tiers"]["PERSON"]
        self.assertEqual(person["acts"], {"total": 3, "median": 3, "none": 0})  # two approvals and one finding decided
        self.assertRegex(p.rail("stats", raw=True).stdout, r"\na person's acts, median for a ticket +- +3\n")

    def test_a_split_shows_groups_of_five_and_sums_the_smaller_ones(self):
        stats = engine_stats()
        groups = {"big": dict(stats._outcome_row(), merged=5, reverted=1, acts=[0] * 5, review_usd=1.0),
                  "small": dict(stats._outcome_row(), merged=2, acts=[1, 0]),
                  "smaller": dict(stats._outcome_row(), merged=1, caused_fix=1, acts=[2])}
        split = stats._split(groups)
        self.assertEqual(list(split), ["big", "other"])
        self.assertEqual((split["big"]["reverted"], split["big"]["cost_per_ticket"]), (1, 0.2))
        self.assertEqual((split["other"]["merged"], split["other"]["caused_fix"], split["other"]["acts"]["total"]), (3, 1, 3))
        self.assertEqual(stats._split({"small": dict(stats._outcome_row(), merged=4, acts=[0] * 4)}), {})


def at(minute):
    return f"2026-03-01T{10 + minute // 60:02d}:{minute % 60:02d}:00Z"


def timed(*events):
    """A journal whose events are (minute, kind, fields)."""
    return SimpleNamespace(ticket=None, events=[{"event": kind, "at": at(minute), **fields} for minute, kind, fields in events])


class WhereTheTimeGoes(RailTest):
    def test_the_lines_come_from_the_journals_with_their_medians_and_shares(self):
        engine()
        from rail import timing
        from rail.util import parse_iso

        def merged(minute):
            return parse_iso(at(minute)).timestamp()

        tickets = {
            # 1: accepted at once, claimed at 2, shipped at 20, merged at 30. Its rebase after the ship took 30s.
            "1": timed((0, "requested", {}), (0, "accepted", {"by": "engine", "scope_paths": ["src/**"]}),
                       (2, "claimed", {}), (10, "step", {"step": "checks", "duration_ms": 60000}),
                       (20, "shipped", {}), (25, "step", {"step": "rebase", "duration_ms": 30000})),
            # 2: the same scope, accepted at 5 while 1 was claimed, so it rested until 1 merged: claimed at 32.
            "2": timed((5, "requested", {}), (5, "accepted", {"by": "engine", "scope_paths": ["src/calc.py"]}),
                       (32, "claimed", {}), (40, "step", {"step": "checks", "duration_ms": 180000}),
                       (45, "shipped", {}), (95, "continued", {"wait": "MERGE_BY_PERSON"})),
            # 3: another scope, a PERSON ticket whose contract waited 20 minutes for its approval.
            "3": timed((10, "requested", {}), (30, "accepted", {"by": "person", "scope_paths": ["api/**"]}),
                       (31, "claimed", {}), (50, "worked", {"minutes": 12.0}), (50, "shipped", {})),
            # 4: not merged, and claimed after the others: it held nothing back.
            "4": timed((0, "requested", {}), (0, "accepted", {"by": "engine", "scope_paths": ["src/**"]}),
                       (200, "claimed", {})),
        }
        merged_at = {"1": merged(30), "2": merged(100), "3": merged(60)}
        found = timing.collect(tickets, merged_at, ["1", "2", "3"])
        rows = {row["key"]: row for row in found["lines"]}
        # Request to merge: 30, 95 and 50 minutes, 175 in all.
        self.assertEqual((found["tickets"], found["request_to_merge_secs"]), (3, 3000.0))
        self.assertEqual((rows["claim_behind_overlap"]["count"], rows["claim_behind_overlap"]["median_secs"],
                          rows["claim_behind_overlap"]["share"]), (1, 1620.0, round(27 / 175, 3)))
        self.assertEqual((rows["claim"]["count"], rows["claim"]["median_secs"]), (2, 90.0))  # 2 minutes and 1
        self.assertEqual((rows["step:checks"]["count"], rows["step:checks"]["median_secs"],
                          rows["step:checks"]["per_ticket_secs"]), (2, 120.0, 80.0))
        self.assertEqual((rows["shipped_to_merged"]["median_secs"], rows["shipped_to_merged"]["share"]),
                         (600.0, round(75 / 175, 3)))  # 10, 55 and 10 minutes
        self.assertEqual((rows["person:MERGE_BY_PERSON"]["median_secs"], rows["person:MERGE_BY_PERSON"]["share"]),
                         (3000.0, round(50 / 175, 3)))
        self.assertEqual(rows["person:APPROVE_CONTRACT"]["median_secs"], 1200.0)  # an older journal names no wait
        self.assertEqual(rows["worker"]["median_secs"], 720.0)
        self.assertEqual(found["rebases_after_ship"], 0.33)
        self.assertEqual(found["lines"][0]["key"], "shipped_to_merged")  # the slowest line first
        shares = [row["share"] for row in found["lines"]]
        self.assertEqual(shares, sorted(shares, reverse=True))

    def test_a_persons_act_records_the_wait_it_answered_and_stats_print_the_lines(self):
        p = self.fixture()
        p.add(ticket(title="Add a status code", tier="PERSON", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("accept", "1")
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("1"))
        p.queue_reviews(clean(), clean())
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        events = [json.loads(line) for line in p.git("show", "main:.rail/journal/1-events.jsonl").splitlines()]
        self.assertEqual([e["wait"] for e in events if e["event"] in ("accepted", "continued")],
                         ["APPROVE_CONTRACT", "MERGE_BY_PERSON"])
        answer = p.rail("stats")
        keys = [row["key"] for row in answer["stats"]["time"]["lines"]]
        for key in ("claim", "shipped_to_merged", "step:checks", "step:review", "person:APPROVE_CONTRACT",
                    "person:MERGE_BY_PERSON"):
            self.assertIn(key, keys)
        self.assertIn("WHERE THE TIME GOES", answer["text"])
        self.assertIn("waiting for a person, MERGE_BY_PERSON", answer["text"])


class Responsibility(RailTest):
    def test_an_auto_ticket_whose_fix_is_a_person_ticket_with_a_kind_held_that_kind(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews(clean())
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        p.add(ticket(title="Stored sums changed shape", tier="PERSON", front=('caused_by = "1"',)))
        answer = p.rail("stats")
        self.assertEqual(answer["stats"]["auto_held_a_kind"], {"tickets": 1, "kinds": {"data-shape": 1}})
        self.assertIn("AUTO tickets that held a kind (a later PERSON ticket names one as its cause): 1 (data-shape 1).",
                      answer["text"])

    def test_drops_are_counted_from_the_marks_once_the_branches_are_gone(self):
        from test_stuck import CAPPED, fail_twice
        a, b, github = self.github_pair(config=CAPPED)
        a.add(ticket())
        a.rail("next")
        fail_twice(a)
        self.assertEqual(a.rail("next", "--ticket", "1")["state"], "dropped")  # the engine, at the retry cap
        a.add(ticket(title="Other", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        a.rail("drop", "2", "--reason", "not needed")
        a.add(ticket(title="Third", scope=("docs/**",), check="grep -q sum docs/guide.md"))
        a.rail("drop", "3", "--by", "person")
        self.assertEqual(a.git("branch", "--list", "[123]-*"), "")
        b.rail("status")  # another clone, which never had the branches
        answer = b.rail("stats")
        self.assertEqual(answer["stats"]["drops"], {"total": 3, "by": {"agent": 1, "engine": 1, "person": 1},
                                                    "stuck_steps": {"checks": 1}})
        self.assertIn("Dropped: 3. By the engine at the retry cap 1, by an agent 1, by a person 1. The engine's drops,"
                      " by the step that kept failing: checks 1.", answer["text"])
