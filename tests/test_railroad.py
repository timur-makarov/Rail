"""End-to-end railroad tests on fixture projects."""

import json
import os
import subprocess
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import ARCHITECTURE, CHECK_ADD, CONFIG, FAKE, RailTest, ticket

CHECK_ADD_PIPED = CHECK_ADD + " 2>&1 | tail -5"


def read(path):
    with open(path) as f:
        return f.read()


def failed_step(answer):
    """(step, detail) of the step that failed. The steps after it are listed as not_run."""
    failed = [s for s in answer["steps"] if s.get("result") == "fail"]
    assert len(failed) == 1, answer["steps"]
    assert all(s["status"] == "not_run" for s in answer["steps"][answer["steps"].index(failed[0]) + 1:])
    return failed[0]["step"], failed[0].get("detail")


class AddToMerge(RailTest):
    """A ticket runs from add to a local merge."""

    def test_a_ticket_runs_from_add_to_local_merge(self):
        p = self.fixture()
        added = p.add(ticket())
        self.assertEqual((added["ticket"], added["state"], added["owner"]), ("1", "accepted", "agent"))
        self.assertEqual(added["reason"]["code"], "CLAIM")
        self.assertEqual(added["branch"], "1-fix-add")

        claimed = p.rail("next")
        self.assertEqual((claimed["ticket"], claimed["state"], claimed["reason"]["code"]), ("1", "implementing", "IMPLEMENT"))
        self.assertEqual(claimed["cwd"], ".claude/worktrees/1")
        self.assertEqual(claimed["action"]["kind"], "agent_task")
        self.assertIn("rail advance 1", claimed["action"]["brief"])
        self.assertTrue(os.path.isdir(p.worktree("1")))

        failed = p.rail("advance", cwd=p.worktree("1"), expect=3)
        self.assertEqual(failed["reason"]["code"], "STEP_FAILED")
        self.assertEqual(failed_step(failed)[0], "checks")
        self.assertIn("AssertionError", failed["action"]["brief"])
        self.assertEqual(p.rail("next")["reason"]["code"], "STEP_FAILED")

        p.fix_calc("1")
        shipped = p.rail("advance", cwd=p.worktree("1"))
        self.assertEqual((shipped["state"], shipped["cwd"]), ("merge-ready", "."))
        self.assertEqual(shipped["action"], {"kind": "script", "brief": "rail advance 1", "command": "rail advance 1"})
        # An AUTO ticket: the engine accepted its contract, the reviewer checks the change, and the engine merges it.
        self.assertEqual([s["step"] for s in shipped["steps"]],
                         ["ticket-lint", "assumptions", "scope", "rules", "size", "doc-lint", "verify", "checks", "review"])

        merged = p.rail("advance", "1")
        self.assertEqual((merged["state"], merged["owner"], merged["reason"]["code"]), ("merged", "none", "MERGED"))

        subject, body = p.git("log", "-1", "--format=%s%x00%b", "main").split("\x00")
        self.assertEqual(subject, "1: fix add")
        self.assertIn("Ticket: 1\nTier: AUTO\nReview: reviewer", body)
        self.assertIn("| check: python3 -c", body)
        self.assertEqual(p.git("show", "main:src/calc.py"), "def add(a, b):\n    return a + b\n")
        self.assertEqual(read(p.path("src", "calc.py")), "def add(a, b):\n    return a + b\n")
        events = [json.loads(l)["event"] for l in p.git("show", "main:.rail/journal/1-events.jsonl").splitlines()]
        self.assertEqual(events[:3], ["requested", "accepted", "claimed"])
        self.assertEqual(events[-2:], ["shipped", "step"])  # the ship, then the review run on what shipped
        self.assertFalse(os.path.exists(p.worktree("1")))
        self.assertNotIn("1-fix-add", p.git("branch"))

        self.assertEqual(p.rail("next")["reason"]["code"], "NO_WORK")
        self.assertEqual(p.rail("status")["tickets"][0]["state"], "merged")

    def test_main_checkout_with_unrelated_changes_still_merges(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        p.write("notes.txt", "my own work\n")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertEqual(read(p.path("notes.txt")), "my own work\n")


class Ship(RailTest):
    def test_changes_outside_scope_fail_and_nothing_is_committed(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("api/handlers.py", "def handle():\n    return 500\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        step, detail = failed_step(failed)
        self.assertEqual(step, "scope")
        self.assertIn("api/handlers.py", detail)
        self.assertEqual(p.git("log", "-1", "--format=%s", "1-fix-add").strip(), "1: ship failed")
        self.assertIn("api/handlers.py", p.git("status", "--porcelain", cwd=p.worktree("1")))

    def test_a_tickets_branch_carries_no_other_tickets_file(self):
        # New tickets come in through rail add, each on its own branch with its own approval. A ticket file written
        # into another ticket's branch would reach the base branch with that ticket's merge.
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        tree = p.worktree("1")
        p.write(".rail/tickets/99.md", ticket(title="Change the engine", tier="PERSON", scope=(".rail/engine/**",)), base=tree)
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed)[0], "scope")
        self.assertIn(".rail/tickets/99.md", failed_step(failed)[1])
        # Committed by hand, it is found on the branch all the same.
        p.git("add", "-A", cwd=tree)
        p.git("commit", "--quiet", "-m", "1: by hand", cwd=tree)
        failed = p.rail("advance", "1", expect=3)
        self.assertIn(("scope", "fail", "outside scope: .rail/tickets/99.md"),
                      [(s["step"], s.get("result"), s.get("detail")) for s in failed["steps"]])
        # The ticket's own file is its own to change, and a ticket may name other files there in scope_paths.
        p.git("rm", "--quiet", ".rail/tickets/99.md", cwd=tree)
        p.git("commit", "--quiet", "-m", "1: undo", cwd=tree)
        p.write(".rail/tickets/1.md", read(os.path.join(tree, ".rail/tickets/1.md")) + "\n## Look at\nThe sum.\n", base=tree)
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")  # it shipped: the scope check passed

    def test_non_ascii_paths_are_in_scope(self):
        p = self.fixture(files={"café/menu.md": "# Menu\n",
                                "ARCHITECTURE.md": ARCHITECTURE + "| menu | café/** | the menu |\n"})
        p.add(ticket(scope=("src/**", "café/**")))
        p.rail("next")
        p.fix_calc("1")
        p.write("café/menu.md", "# Menu\n\nCoffee.\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertIn("café/**", p.rail("context", "1")["areas"][-1]["paths"])

    def test_open_assumed_row_is_verified_before_ship(self):
        p = self.fixture()
        p.add(ticket(body="\n## Assumptions\n- ASSUMED: nobody calls add with strings.\n"))
        brief = p.rail("next")
        self.assertEqual(brief["reason"]["code"], "VERIFY_ASSUMPTIONS")
        self.assertIn("nobody calls add with strings", brief["action"]["brief"])
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("assumptions", "1 open"))
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        text = read(path).replace("ASSUMED: nobody", "VERIFIED: nobody")
        p.write(".rail/tickets/1.md", text, base=p.worktree("1"))
        self.assertEqual(p.rail("next")["reason"]["code"], "IMPLEMENT")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")

    def test_an_assumed_row_nobody_can_check_is_decided_not_asked(self):
        # The row is the agent's: a worker that stops to ask leaves no label for the person and blocks the queue.
        p = self.fixture()
        p.add(ticket(tier="PERSON", body="\n## Assumptions\n- ASSUMED: finance wants the new column last.\n"))
        p.rail("accept", "1")
        brief = p.rail("next")
        self.assertEqual((brief["reason"]["code"], brief["owner"]), ("VERIFY_ASSUMPTIONS", "agent"))
        self.assertNotIn("ask the person", brief["action"]["brief"])
        self.assertIn("decided, not checked:", brief["action"]["brief"])
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        text = read(path).replace("ASSUMED: finance", "VERIFIED: decided, not checked: finance")
        p.write(".rail/tickets/1.md", text, base=p.worktree("1"))
        self.assertEqual(p.rail("next")["reason"]["code"], "IMPLEMENT")

    def test_a_change_to_a_person_path_makes_the_ticket_person_at_ship(self):
        p = self.fixture(config='person_paths = ["**/*.sql"]\n' + CONFIG)
        self.assertEqual(p.add(ticket())["tier"], "AUTO")
        p.rail("next")
        p.fix_calc("1")
        p.write("src/report.sql", "select 1;\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        # The engine accepted the contract as AUTO. The change it shipped is a person's to merge, with both reviews.
        self.assertEqual((shipped["state"], shipped["tier"], shipped["reason"]["code"]),
                         ("merge-ready", "PERSON", "MERGE_BY_PERSON"))
        self.assertEqual([s["step"] for s in shipped["steps"]][-2:], ["review", "security"])
        raised = [e for e in journal(p) if e["event"] == "tier_raised"]
        self.assertEqual((raised[0]["from"], raised[0]["to"], raised[0]["reason"], raised[0]["detail"]),
                         ("AUTO", "PERSON", "person_paths", "src/report.sql"))

    def test_a_change_inside_skip_paths_merges_with_no_reviewer(self):
        # The paths decide whether a change is reviewed, never the ticket's author. One file outside them is enough
        # for the reviewer to read the whole change.
        p = self.fixture(config=CONFIG.replace("[review]", '[review]\nskip_paths = ["docs/**"]'),
                         files={"docs/guide.md": "# Guide\n",
                                "ARCHITECTURE.md": ARCHITECTURE + "| docs | docs/** | the guide |\n"})
        p.add(ticket(title="Say what add does", scope=("docs/**", "src/**"), check="grep -q sum docs/guide.md"))
        p.rail("next")
        p.write("docs/guide.md", "# Guide\n\nadd returns the sum.\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["steps"][-1]["step"]), ("merge-ready", "checks"))
        self.assertEqual(p.briefs(), [])  # no reviewer ran
        p.rail("advance", "1")
        body = p.git("log", "-1", "--format=%b", "main")
        self.assertIn("| review | not needed: every changed file is in [review] skip_paths |", body)
        self.assertIn("Ticket: 1\nTier: AUTO\nReview: none", body)

        p.add(ticket(title="Fix add and say so", scope=("docs/**", "src/**")))
        p.rail("next")
        p.fix_calc("2")
        p.write("docs/guide.md", "# Guide\n\nadd returns the sum, now for real.\n", base=p.worktree("2"))
        shipped = p.rail("advance", "2")
        self.assertEqual((shipped["state"], shipped["steps"][-1]["step"]), ("merge-ready", "review"))
        self.assertIn("docs/guide.md", p.briefs()[-1]["brief"])

    def test_migration_needs_reversibility_and_rollback(self):
        p = self.fixture(files={"db/migrations/001.sql": "create table t (id int);\n",
                                "ARCHITECTURE.md": ARCHITECTURE + "| db | db/** | schema and migrations |\n"})
        added = p.add(ticket(title="Add a column", scope=("db/**", "src/**")))
        self.assertEqual((added["tier"], added["state"], added["owner"]), ("PERSON", "new", "human"))
        p.rail("accept", "1")
        p.rail("next")
        p.fix_calc("1")
        p.write("db/migrations/002.sql", "alter table t add column c int;\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("migration", "missing reversibility, rollback"))
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        text = read(path).replace('tier = "PERSON"', 'tier = "PERSON"\nreversibility = "expand-contract"\nrollback = "drop column c"')
        p.write(".rail/tickets/1.md", text, base=p.worktree("1"))
        ready = p.rail("advance", "1")
        self.assertEqual((ready["state"], ready["owner"], ready["reason"]["code"]), ("merge-ready", "human", "MERGE_BY_PERSON"))
        self.assertEqual([s["step"] for s in ready["steps"]][-2:], ["review", "security"])

    def test_base_moved_rebases_and_ships_again_before_merge(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add a status code", scope=("api/**",),
                     check="grep -q 201 api/handlers.py"))
        p.rail("next", session="a")
        p.rail("next", session="b")
        p.fix_calc("1")
        p.rail("advance", "1", session="a")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("2"))
        p.rail("advance", "2", session="b")
        self.assertEqual(p.rail("advance", "1", session="a")["state"], "merged")
        merged = p.rail("advance", "2", session="b")
        self.assertEqual(merged["state"], "merged")
        self.assertEqual(merged["steps"][0], {"step": "rebase", "status": "ran", "result": "pass", "detail": "onto main"})
        self.assertEqual(p.git("log", "--format=%s", "main").splitlines()[:2], ["2: add a status code", "1: fix add"])

    def test_a_change_with_no_file_in_it_does_not_ship(self):
        # A second ticket for work already on the base: its check passes before any edit, and it must not merge empty.
        p = self.fixture()
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n")
        p.git("commit", "--quiet", "-am", "fix add by hand")
        p.add(ticket())
        p.rail("next")
        empty = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(empty), ("change", "no file changed"))
        self.assertIn("rail drop 1 --reason", empty["action"]["brief"])
        self.assertEqual(p.rail("drop", "1", "--reason", "already done: on main")["state"], "dropped")

    def test_rebase_conflict_returns_the_ticket_to_implementing(self):
        p = self.fixture()
        p.add(ticket(title="Rewrite add"))
        p.rail("next", session="b")
        p.write("src/calc.py", "def add(a, b):\n    return sum((a, b))\n", base=p.worktree("1"))
        p.rail("advance", "1", session="b")
        # Another person's change to the same line lands on the base: two tickets can't be on these paths at once.
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n")
        p.git("commit", "--quiet", "-am", "fix add by hand")
        failed = p.rail("advance", "1", session="b", expect=3)
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["result"]), ("rebase", "fail"))
        self.assertIn("src/calc.py", failed["steps"][0]["detail"])
        self.assertEqual(failed["state"], "implementing")


def journal(p, nn="1", branch="1-fix-add"):
    return [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]


class Commands(RailTest):
    """How the engine runs a configured command, and what it records when the command can't start."""

    def test_a_failure_inside_a_pipe_fails_the_check(self):
        # In sh (dash on Linux) a pipe's status is its last command's, so `CHECK | tail` passed with CHECK failing.
        p = self.fixture()
        p.add(ticket(check=CHECK_ADD_PIPED))
        p.rail("next")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("checks", f"{CHECK_ADD_PIPED}: exit 1"))
        self.assertIn("AssertionError", failed["action"]["brief"])
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")

    def test_a_verify_that_cannot_start_could_not_run_and_is_never_taken_for_a_red_base(self):
        p = self.fixture(config=CONFIG.replace("python3 -m py_compile src/calc.py", "no-such-test-runner --all"))
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")  # PERSON: at the retry budget or cap it waits for a person
        p.rail("next")
        p.fix_calc("1")
        first = p.rail("advance", "1", expect=3)
        verify = [s for s in first["steps"] if s["step"] == "verify"][0]
        self.assertEqual((verify["status"], verify["result"], verify["detail"]),
                         ("could_not_run", "fail", "could not run (exit 127: command not found)"))
        self.assertEqual(first["reason"]["code"], "STEP_FAILED")
        self.assertIn("Ship of ticket 1 could not run 'verify'.", first["action"]["brief"])
        self.assertIn("no-such-test-runner: command not found", first["action"]["brief"])  # the shell's own line
        self.assertIn("Nothing was checked", first["action"]["brief"])
        again = p.rail("next", "--ticket", "1")["action"]["brief"]  # with the output the advance answer showed
        self.assertIn("could not run 'verify': could not run (exit 127: command not found).\n$ no-such-test-runner", again)
        self.assertIn("no-such-test-runner: command not found\n\nNothing was checked", again)
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "verify"][-1]
        self.assertEqual((recorded["status"], recorded["result"]), ("could_not_run", "fail"))
        self.assertNotIn("counted", recorded)  # an attempt like any other: the budget bounds it
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "STEP_FAILED")  # not RED_BASE
        self.assertEqual(len(p.rail("status")["tickets"]), 1)  # and no fix ticket for the base
        second = p.rail("advance", "1", expect=3)  # the budget: consult advises, one more attempt
        self.assertIn("consult says", second["action"]["brief"])
        capped = p.rail("advance", "1", expect=3)
        self.assertEqual((capped["owner"], capped["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertIn("Its last attempt at 'verify' (could not run (exit 127: command not found)) could not run",
                      capped["action"]["brief"])

    def test_a_check_that_cannot_start_says_so_and_a_failing_one_does_not(self):
        p = self.fixture()
        p.add(ticket(check="./src/calc.py"))  # there, but not executable: 126
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        check = failed["steps"][-1]
        self.assertEqual((check["step"], check["status"], check["detail"]),
                         ("checks", "could_not_run", "./src/calc.py: could not run (exit 126: found but could not be run)"))
        fails = [e for e in journal(p) if e["event"] == "step" and e["step"] == "verify"]
        self.assertEqual([(e["status"], e["result"]) for e in fails], [("ran", "pass")])

    def test_a_reviewer_that_cannot_start_reviewed_nothing(self):
        p = self.fixture(config=CONFIG.replace(f"python3 {FAKE}\"\n\n[consult]", "no-such-reviewer\"\n\n[consult]"))
        p.add(ticket(tier="AUTO"))
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        review = [s for s in failed["steps"] if s["step"] == "review"][0]
        self.assertEqual((review["status"], review["result"], review["detail"]),
                         ("could_not_run", "fail", "could not run (exit 127: command not found)"))
        self.assertEqual(failed["state"], "reviewing")
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "review"]
        self.assertEqual([e["status"] for e in recorded], ["could_not_run"])


class Claim(RailTest):
    def test_setup_runs_in_the_worktree_with_its_include_files_and_reruns_after_a_failure(self):
        setup = 'test -f .env && test "$RAIL_TICKET" = 1'
        p = self.fixture(config=CONFIG.replace("[commands]", f"[commands]\nsetup = '{setup}'"),
                         files={".worktreeinclude": ".env\n", ".gitignore": ".claude/worktrees/\n__pycache__/\n.env\n"})
        p.add(ticket())
        failed = p.rail("next", expect=3)  # setup is a step, so a failed setup exits 3
        self.assertEqual((failed["reason"]["code"], failed["steps"][0]["result"]), ("SETUP_FAILED", "fail"))
        p.write(".env", "TOKEN=local\n")
        p.write(".env", "TOKEN=local\n", base=p.worktree("1"))
        rerun = p.rail("next", "--ticket", "1")
        self.assertEqual((rerun["reason"]["code"], rerun["steps"][0]["result"]), ("IMPLEMENT", "pass"))
        p.rail("drop", "1")
        p.add(ticket(title="Fix add again"))
        self.assertEqual(p.rail("next", expect=3)["reason"]["code"], "SETUP_FAILED")  # ticket 2: RAIL_TICKET is 2
        self.assertEqual(read(os.path.join(p.worktree("2"), ".env")), "TOKEN=local\n")

    def test_a_branch_that_belongs_to_no_ticket_is_left_alone(self):
        p = self.fixture()
        p.git("branch", "7-old-experiment")
        self.assertEqual(p.rail("next")["reason"]["code"], "NO_WORK")
        self.assertIn("7-old-experiment", p.git("branch"))
        self.assertEqual(p.rail("status")["leftovers"],
                         [{"kind": "branch", "ref": "7-old-experiment", "reason": "no ticket; left for you"}])
        self.assertEqual(p.add(ticket())["ticket"], "1")


class TicketLint(RailTest):
    def test_add_rejects_a_malformed_ticket_and_takes_no_id(self):
        p = self.fixture()
        cases = {
            "vacuous Check": ticket(check="true"),
            "did you mean 'scope_paths'": ticket(front=('scope_path = ["x"]',)),
            "put the command in backticks": ticket().replace("`python3", "python3").replace("== 5\"`", "== 5\""),
            "tier must be one of": ticket(tier="URGENT"),
        }
        for needle, text in cases.items():
            with self.subTest(needle):
                failed = p.add(text, expect=3)
                self.assertEqual(failed["reason"]["code"], "TICKET_LINT")
                self.assertIn(needle, failed["action"]["brief"])
        self.assertEqual(p.git("branch", "--list", "[0-9]*"), "")
        self.assertEqual(p.add(ticket())["ticket"], "1")


class Approval(RailTest):
    def test_a_person_tickets_contract_waits_for_a_person_then_runs(self):
        p = self.fixture()
        added = p.add(ticket(tier="PERSON"))
        self.assertEqual((added["state"], added["owner"], added["action"]["kind"]), ("new", "human", "human_wait"))
        self.assertIn("rail accept 1", added["action"]["brief"])
        waiting = p.rail("next")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("human", "WAITING_HUMAN"))
        self.assertEqual(waiting["waits"][0]["ticket"], "1")
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "APPROVE_CONTRACT")
        accepted = p.rail("accept", "1", "keep the API stable")
        self.assertEqual(accepted["state"], "accepted")
        event = json.loads(p.git("show", "1-fix-add:.rail/journal/1-events.jsonl").splitlines()[-1])
        self.assertEqual((event["by"], event["via"], event["note"]), ("person", "accept", "keep the API stable"))
        self.assertEqual(p.rail("accept", "1", expect=2)["reason"]["code"], "NOTHING_TO_ACCEPT")
        self.assertEqual(p.rail("next")["state"], "implementing")

    def test_a_scope_that_reaches_a_person_path_makes_the_ticket_person_at_add(self):
        p = self.fixture()
        added = p.add(ticket(scope=(".github/workflows/**",)))
        self.assertEqual((added["tier"], added["state"], added["reason"]["code"]), ("PERSON", "new", "APPROVE_CONTRACT"))
        self.assertIn('tier = "PERSON"', p.git("show", "1-fix-add:.rail/tickets/1.md"))  # the ticket says so


class Parallel(RailTest):
    def test_after_waits_for_the_earlier_merge(self):
        p = self.fixture()
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.add(ticket(front=('after = ["1"]',)))
        self.assertEqual(p.rail("next")["ticket"], "1")
        self.assertEqual(p.rail("next", "--ticket", "2", session="b")["reason"]["code"], "WAITING_AFTER")
        self.assertEqual(p.rail("next", session="b")["reason"]["code"], "NO_WORK")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("1"))
        p.rail("advance", "1")
        p.rail("advance", "1")
        nxt = p.rail("next", session="b")
        self.assertEqual((nxt["ticket"], nxt["state"]), ("2", "implementing"))

    def test_a_claim_starts_from_the_current_base(self):
        p = self.fixture()
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.add(ticket(front=('after = ["1"]',)))
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("1"))
        p.rail("advance", "1")
        p.rail("advance", "1")
        p.rail("next")
        self.assertIn("201", read(os.path.join(p.worktree("2"), "api", "handlers.py")))
        self.assertEqual(p.git("merge-base", "--is-ancestor", "main", "2-fix-add"), "")

    def test_a_dropped_dependency_waits_for_a_person(self):
        p = self.fixture()
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.add(ticket(tier="PERSON", front=('after = ["1"]',)))
        p.rail("accept", "2")  # PERSON: a person decides; on AUTO the agent does (test_stuck.py)
        p.rail("drop", "1")
        waiting = p.rail("next")
        self.assertEqual((waiting["owner"], waiting["waits"][0]["needs"]), ("human", "AFTER_DROPPED"))

    def test_overlapping_scope_is_not_claimed_and_claims_belong_to_sessions(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add subtract"))
        self.assertEqual(p.rail("next", session="a")["ticket"], "1")
        other = p.rail("next", session="b")
        self.assertEqual(other["reason"]["code"], "NO_WORK")
        self.assertEqual([h["ticket"] for h in other["held"]], ["1"])
        self.assertEqual(p.rail("next", "--ticket", "2", session="b")["reason"]["code"], "SCOPE_OVERLAP")
        self.assertEqual(p.rail("next", session="a")["ticket"], "1")

    def test_a_ticket_in_review_or_ci_still_blocks_one_on_the_same_paths(self):
        # Shipped is not merged: the second ticket would start from a base the first is about to change.
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add subtract"))
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        self.assertNotEqual(p.rail("status")["tickets"][0]["state"], "implementing")
        self.assertEqual(p.rail("next", "--ticket", "2", session="b")["reason"]["code"], "SCOPE_OVERLAP")

    def test_takeover_records_the_new_session(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next", session="a")
        taken = p.rail("next", "--ticket", "1", session="b")
        self.assertEqual(taken["reason"]["code"], "IMPLEMENT")
        claims = [json.loads(l) for l in p.git("show", "1-fix-add:.rail/journal/1-events.jsonl").splitlines()
                  if json.loads(l)["event"] == "claimed"]
        self.assertEqual([(c["session"], c["takeover"]) for c in claims], [("a", False), ("b", True)])
        self.assertEqual([h["ticket"] for h in p.rail("next", session="a")["held"]], ["1"])


class Remote(RailTest):
    def test_two_clones_never_take_the_same_id_or_claim(self):
        a, b = self.remote_pair()
        results = []

        def run_both(work):
            threads = [threading.Thread(target=work, args=(fx,)) for fx in (a, b)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        def add_three(fx):
            for i in range(3):
                title = f"T{i}{os.path.basename(fx.root)}"
                results.append(fx.add(ticket(title=title, scope=(f"{title.lower()}/**",))))

        run_both(add_three)
        self.assertEqual(sorted(int(r["ticket"]) for r in results), [1, 2, 3, 4, 5, 6])
        # One counter branch holds all six IDs: a cloud session can't delete branches, so there is none per ID.
        self.assertEqual(a.git("ls-remote", "origin", "refs/heads/rail/*").split()[1::2], ["refs/heads/rail/ids"])
        a.git("fetch", "--quiet")
        self.assertEqual(a.git("log", "--format=%s", "origin/rail/ids").splitlines(),
                         [f"rail id {n}" for n in (6, 5, 4, 3, 2, 1)])  # its own small chain, apart from the project

        claims = {}
        run_both(lambda fx: claims.update({fx.root: fx.rail("next", session=os.path.basename(fx.root))}))
        claimed = [c["ticket"] for c in claims.values() if c["state"] == "implementing"]
        self.assertEqual(len(claimed), 2, claims)
        self.assertNotEqual(claimed[0], claimed[1], claims)

    def test_an_id_taken_after_our_fetch_is_refused_and_the_next_is_taken(self):
        a, b = self.remote_pair()
        b.git("config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
        self.assertEqual(a.add(ticket())["ticket"], "1")
        self.assertEqual(b.add(ticket(title="Other", scope=("api/**",)))["ticket"], "2")
        self.assertEqual(b.git("ls-remote", "origin", "refs/heads/rail/*").count("refs/heads/rail/"), 1)

    def test_a_dropped_ticket_whose_branch_was_deleted_keeps_its_id_and_its_text(self):
        a, b = self.remote_pair()
        a.add(ticket())
        a.rail("drop", "1", "--reason", "not needed")  # with a plain git remote the engine deletes the branch too
        self.assertEqual(a.git("ls-remote", "origin", "refs/heads/1-*"), "")
        row = b.rail("status")["tickets"][0]
        self.assertEqual((row["ticket"], row["state"], row["title"]), ("1", "dropped", "Fix add"))
        self.assertEqual(b.add(ticket(title="Other", scope=("api/**",)))["ticket"], "2")  # the ID is never reused

    def test_a_claim_made_offline_after_the_base_moved_still_reaches_the_remote(self):
        a, b = self.remote_pair()
        a.add(ticket())
        b.git("commit", "--quiet", "--allow-empty", "-m", "base moves")
        b.git("push", "--quiet", "origin", "main")
        a.git("fetch", "--quiet")
        remote = os.path.join(self.tmp, "remote.git")
        os.rename(remote, remote + ".away")
        a.rail("next", session="a")  # offline: the claim rebases onto the new base and can't push
        os.rename(remote + ".away", remote)
        a.fix_calc("1")
        a.rail("advance", "1", session="a")
        self.assertEqual(a.git("rev-parse", "1-fix-add"), a.git("ls-remote", "origin", "refs/heads/1-fix-add").split()[0] + "\n")
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "in-ci")

    def test_with_a_remote_ship_pushes_and_waits_for_the_forge(self):
        a, b = self.remote_pair()
        a.add(ticket())
        a.rail("next", session="a")
        a.fix_calc("1")
        shipped = a.rail("advance", "1", session="a")
        self.assertEqual((shipped["state"], shipped["reason"]["code"]), ("in-ci", "FORGE_UNAVAILABLE"))
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "in-ci")
        self.assertIn("shipped", b.git("show", "origin/1-fix-add:.rail/journal/1-events.jsonl"))


class Drop(RailTest):
    def test_drop_ends_a_ticket_and_its_id_is_never_reused(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        dropped = p.rail("drop", "1", "--reason", "not needed")
        self.assertEqual(dropped["state"], "dropped")
        self.assertFalse(os.path.exists(p.worktree("1")))
        self.assertEqual(p.git("branch", "--list", "1-*"), "")
        self.assertEqual(p.add(ticket(title="Fix add again"))["ticket"], "2")
        self.assertEqual([r["state"] for r in p.rail("status")["tickets"]], ["dropped", "accepted"])
        self.assertEqual(p.rail("drop", "1")["state"], "dropped")


class Reading(RailTest):
    def test_status_lists_leftovers_it_cannot_remove(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        dropped = p.rail("drop", "1")
        self.assertEqual(dropped["leftovers"][0]["kind"], "worktree")
        self.assertTrue(os.path.exists(p.worktree("1")))
        self.assertEqual(p.rail("next")["leftovers"][0]["ref"], ".claude/worktrees/1")
        status = p.rail("status")
        self.assertEqual(status["leftovers"][0]["ref"], ".claude/worktrees/1")
        text = p.rail("status", raw=True).stdout
        self.assertIn("TICKET", text)
        self.assertIn("leftovers:", text)

    def test_context_returns_matching_areas_and_a_digest(self):
        p = self.fixture()
        p.add(ticket(scope=("api/**",)))
        found = p.rail("context", "1")
        self.assertEqual([a["area"] for a in found["areas"]], ["api"])
        self.assertIn("src/ (1 files)", found["digest"])
        self.assertEqual(len(p.rail("context")["areas"]), 2)


class Worker(RailTest):
    """next names the model and effort for a ticket's work; the engine itself starts no agent."""

    def test_the_ladder_climbs_one_rung_per_failed_attempt(self):
        p = self.fixture()
        p.add(ticket())
        claimed = p.rail("next")
        self.assertEqual((claimed["reason"]["code"], claimed["action"]["model"], claimed["action"]["effort"]),
                         ("IMPLEMENT", "claude-sonnet-5-5", "medium"))
        self.assertIn("model: claude-sonnet-5-5, effort medium", p.rail("next", raw=True).stdout)
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["action"]["model"], failed["action"]["effort"]), ("claude-sonnet-5-5", "high"))
        again = p.rail("next")
        self.assertEqual((again["reason"]["code"], again["action"]["effort"]), ("STEP_FAILED", "high"))
        p.fix_calc("1")
        shipped = p.rail("advance", "1")
        self.assertNotIn("model", shipped["action"])  # a script for the engine, not work for an agent

    def test_a_person_ticket_starts_higher(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        claimed = p.rail("next")
        self.assertEqual((claimed["action"]["model"], claimed["action"]["effort"]), ("claude-opus-5-5", "medium"))

    def test_writing_a_contract_names_the_contract_model(self):
        p = self.fixture()
        request = os.path.join(self.tmp, "request.md")
        with open(request, "w") as f:
            f.write("add(2, 3) gives -1.\n")
        p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix add", "--brief", request)
        drafting = p.rail("next")
        self.assertEqual((drafting["reason"]["code"], drafting["action"]["model"], drafting["action"]["effort"]),
                         ("TICKET_LINT", "claude-opus-5-5", "high"))
        p.write(".rail/config.toml", CONFIG + '\n[worker]\ncontract = ""\n')
        self.assertEqual(p.rail("next")["action"]["model"], "claude-sonnet-5-5")  # empty: the ladder's rung
        p.write(".rail/config.toml", CONFIG + '\n[worker]\ncontract = "claude-opus-5-5"\n')
        self.assertIn("worker.contract must be model:effort", p.rail("status", expect=2)["reason"]["message"])

    def test_an_empty_ladder_names_no_model(self):
        p = self.fixture(config=CONFIG + "\n[worker]\nladder = []\n")
        p.add(ticket())
        claimed = p.rail("next")
        self.assertEqual(claimed["action"]["kind"], "agent_task")
        self.assertNotIn("model", claimed["action"])
        self.assertNotIn("effort", claimed["action"])

    def test_a_rung_that_is_not_model_and_effort_is_a_config_error(self):
        p = self.fixture(config=CONFIG + '\n[worker]\nladder = ["claude-sonnet-5-5:medium", "claude-opus-5-5:hard"]\n')
        failed = p.rail("status", expect=2)
        self.assertIn("worker.ladder[1] must be model:effort", failed["reason"]["message"])
        p.write(".rail/config.toml", CONFIG + '\n[worker]\nperson_ladder = [":high"]\n')
        self.assertIn("worker.person_ladder[0]", p.rail("status", expect=2)["reason"]["message"])


class Usage(RailTest):
    def test_usage_errors_exit_2_with_one_shape(self):
        p = self.fixture()
        self.assertEqual(p.rail("frobnicate", expect=2)["ok"], False)
        self.assertEqual(p.rail("advance", "99", expect=2)["reason"]["code"], "NO_TICKET")

    def test_unknown_config_key_fails_with_a_suggestion(self):
        p = self.fixture(config='base_brnch = "main"\n')
        failed = p.rail("status", expect=2)
        self.assertIn("did you mean 'base_branch'", failed["reason"]["message"])

    def test_outside_a_project(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        subprocess.run(["git", "init", "--quiet", empty], check=True)
        p = self.fixture()
        self.assertEqual(p.rail("next", cwd=empty, expect=2)["reason"]["code"], "NOT_A_PROJECT")


if __name__ == "__main__":
    unittest.main()
