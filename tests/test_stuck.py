"""A ticket at the retry cap gets one diagnosis from a run that did not write the change, and the answer says what
happens to it (rail docs retries). With no answer to act on, an AUTO ticket is dropped with a record and a PERSON
ticket waits. A drop never removes anything before its mark is written."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, CONFIG, RailTest, ticket

CAPPED = CONFIG + "\n[retry]\nbudget = 9\ncap = 2\n"  # two failures of any kind are the cap; consult never comes


def fail_twice(p, nn="1"):
    """Two failed ships at 'checks', each a different failure."""
    for body in ("return a - b", "return a * b"):
        p.write("src/calc.py", f"def add(a, b):\n    {body}\n", base=p.worktree(nn))
        last = p.rail("advance", nn, expect=3)
    return last


def said(answer, reason="Read the journal and the change.", **more):
    """A diagnosis, as the stand-in for the triage run answers it."""
    return {"answer": answer, "reason": reason, **more}


CANNOT_TELL = said("cannot-tell")


def events(p, kind, branch="1-fix-add"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if e["event"] == kind]


def diagnoses(p):
    """The briefs of the diagnosis runs the stand-in was given."""
    return [b for b in p.briefs() if b["brief"].startswith("# One question") and "stuck)" in b["brief"].splitlines()[0]]


def mark(p, nn="1"):
    """The drop mark on the remote's counter branch: its subject and the note it keeps."""
    p.git("fetch", "--quiet", "origin", "+refs/heads/rail/ids:refs/remotes/origin/rail/ids")
    for entry in p.git("log", "--format=%s%x1f%b%x1e", "origin/rail/ids").split("\x1e"):
        subject, _, body = entry.strip().partition("\x1f")
        if subject == f"rail drop {nn}":
            return json.loads(body.strip()) if body.strip() else {}
    return None


class Stuck(RailTest):
    def test_an_auto_ticket_at_the_cap_is_dropped_with_a_record(self):
        a, b, github = self.github_pair(config=CAPPED)
        github.update(lambda s: s["issues"].append({"number": 12, "title": "Add can't add", "body": "add(2, 3) gives -1.",
                                                    "labels": ["rail"], "state": "open"}))
        a.rail("intake", "github")
        written = os.path.join(self.tmp, "1.md")
        with open(written, "w") as f:
            f.write(ticket(title="Add can't add", front=('external_id = "github#12"',)))
        a.rail("amend", "1", "--file", written)
        a.rail("next")
        capped = fail_twice(a)
        self.assertEqual((capped["owner"], capped["reason"]["code"], capped["action"]["brief"]),
                         ("agent", "DIAGNOSE", "rail next --ticket 1"))
        a.queue_reviews(CANNOT_TELL)
        dropped = a.rail("next", "--ticket", "1")
        self.assertEqual((dropped["state"], dropped["reason"]["code"]), ("dropped", "DROPPED"))
        self.assertFalse(os.path.exists(a.worktree("1")))
        self.assertEqual(a.git("branch", "--list", "1-*"), "")
        self.assertEqual(github.pr(1)["state"], "closed")
        note = mark(a)
        self.assertEqual(note["event"], "requested")  # rail stats still reads where the ticket came from
        self.assertEqual((note["dropped"]["by"], note["dropped"]["step"]), ("engine", "checks"))
        self.assertTrue(note["dropped"]["signature"].startswith("checks:"))
        self.assertIn("stuck: 'checks' failed 2 times since it last passed, whatever the output ([retry] cap)",
                      note["dropped"]["reason"])
        self.assertIn("The diagnosis it got at the cap: `cannot-tell`", note["dropped"]["reason"])
        self.assertEqual(note["dropped"]["diagnosis"], "cannot-tell")
        issue = github.read()["issues"][0]
        self.assertNotIn("rail", issue["labels"])
        comment = " ".join(github.read()["comments"]["12"][0]["body"].split())
        self.assertIn("'checks' failed 2 times since it last passed", comment)
        self.assertIn("The diagnosis it got at the cap: `cannot-tell`, none of the others can be shown", comment)
        self.assertIn("Label this issue `rail` again to retry", comment)
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "dropped")

    def test_a_person_ticket_at_the_cap_still_waits(self):
        p = self.fixture(config=CAPPED)
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        capped = fail_twice(p)
        self.assertEqual((capped["owner"], capped["reason"]["code"]), ("agent", "DIAGNOSE"))  # no wait before its answer
        p.queue_reviews(CANNOT_TELL)
        waiting = p.rail("next", "--ticket", "1")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("person", "RETRY_CAP"))
        self.assertEqual(waiting["action"]["facts"]["diagnosis"]["answer"], "cannot-tell")
        self.assertIn("A run that did not write the change read the attempts once and answered `cannot-tell`",
                      waiting["action"]["brief"])
        self.assertTrue(os.path.exists(p.worktree("1")))
        # The person continues it, and it reaches the cap again: it waits as before, with no second diagnosis.
        p.rail("accept", "1", "try the operator")
        again = fail_twice(p)
        self.assertEqual((again["owner"], again["reason"]["code"]), ("person", "RETRY_CAP"))
        self.assertEqual(len(diagnoses(p)), 1)


class DropPending(RailTest):
    def offline(self, a):
        remote = os.path.join(self.tmp, "remote.git")
        os.rename(remote, remote + ".away")
        return lambda: os.rename(remote + ".away", remote)

    def test_a_stuck_drop_with_no_mark_keeps_everything_until_the_mark_is_written(self):
        a, b = self.remote_pair(config=CAPPED)
        a.add(ticket())
        a.rail("next")
        fail_twice(a)
        a.queue_reviews(CANNOT_TELL)
        back = self.offline(a)
        pending = a.rail("next", "--ticket", "1")
        self.assertEqual((pending["state"], pending["owner"], pending["reason"]["code"]), ("dropped", "none", "DROP_PENDING"))
        self.assertTrue(os.path.exists(a.worktree("1")))
        self.assertIn("1-fix-add", a.git("branch", "--list", "1-*"))
        self.assertEqual(a.rail("status")["tickets"][0]["state"], "dropped")
        self.assertTrue(os.path.exists(a.worktree("1")))  # status changes nothing
        back()
        a.rail("next")  # the mark is written now, and the drop finishes
        self.assertFalse(os.path.exists(a.worktree("1")))
        self.assertEqual(a.git("branch", "--list", "1-*"), "")
        self.assertEqual(mark(a)["dropped"]["by"], "engine")

    def test_rail_drop_with_no_mark_keeps_everything_until_the_mark_is_written(self):
        a, b = self.remote_pair()
        a.add(ticket())
        a.rail("next")
        back = self.offline(a)
        pending = a.rail("drop", "1", "--reason", "not needed")
        self.assertEqual((pending["state"], pending["reason"]["code"]), ("dropped", "DROP_PENDING"))
        self.assertEqual([s["status"] for s in pending["steps"] if s["step"] == "drop-mark"], ["unavailable"])
        self.assertTrue(os.path.exists(a.worktree("1")))
        self.assertIn("1-fix-add", a.git("branch", "--list", "1-*"))
        back()
        a.rail("next")
        self.assertFalse(os.path.exists(a.worktree("1")))
        self.assertEqual({k: mark(a)["dropped"].get(k) for k in ("by", "reason", "cost_usd")},
                         {"by": "agent", "reason": "not needed", "cost_usd": None})  # no run reported a cost


class AfterDropped(RailTest):
    def setUp(self):
        super().setUp()
        self.p = self.fixture()
        self.p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        self.p.add(ticket(front=('after = ["1"]',)))
        self.p.rail("drop", "1", "--reason", "not needed")

    def test_on_auto_the_contract_writer_decides_instead_of_a_person(self):
        task = self.p.rail("next")
        self.assertEqual((task["ticket"], task["owner"], task["reason"]["code"]), ("2", "agent", "AFTER_DROPPED"))
        self.assertEqual((task["action"]["model"], task["action"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertIn("rail amend 2", task["action"]["brief"])
        self.assertIn('rail drop 2 --reason "why"', task["action"]["brief"])

    def test_removing_the_dropped_ticket_from_after_is_recorded_and_the_ticket_goes_on(self):
        written = os.path.join(self.tmp, "2.md")
        with open(written, "w") as f:
            f.write(ticket())
        self.p.rail("amend", "2", "add does not need the status code", "--file", written)
        rows = [json.loads(l) for l in self.p.git("show", "2-fix-add:.rail/journal/2-events.jsonl").splitlines()]
        amended = [e for e in rows if e["event"] == "amended"][-1]
        self.assertEqual((amended["changed"], amended["reason"]), (["after"], "add does not need the status code"))
        self.assertEqual(self.p.rail("next")["reason"]["code"], "IMPLEMENT")

    def test_dropping_it_is_recorded(self):
        dropped = self.p.rail("drop", "2", "--reason", "it only made sense with the status code")
        self.assertEqual(dropped["state"], "dropped")
        note = open(self.p.path(".git", "rail", "ids", "2.dropped")).read()
        dropped = json.loads(note)["dropped"]
        self.assertEqual((dropped["by"], dropped["reason"]), ("agent", "it only made sense with the status code"))


class Diagnosis(RailTest):
    def capped(self, tier="AUTO", **kw):
        p = self.fixture(config=CAPPED, **kw)
        p.add(ticket(tier=tier))
        p.rail("next")
        fail_twice(p)
        return p

    def test_a_ticket_at_the_cap_gets_one_question_and_nothing_else_before_its_answer(self):
        p = self.capped()
        at_cap = p.rail("advance", "1")  # nothing ships meanwhile
        self.assertEqual((at_cap["state"], at_cap["owner"], at_cap["reason"]["code"]), ("implementing", "agent", "DIAGNOSE"))
        self.assertEqual(at_cap["steps"], [])
        self.assertEqual(events(p, "question"), [])
        p.queue_reviews(CANNOT_TELL)
        p.rail("next", "--ticket", "1")
        (run,) = diagnoses(p)
        self.assertEqual(run["model"], "claude-opus-5-5")  # the contract writer's, [worker] contract
        brief = run["brief"]
        self.assertIn("This ticket's attempts keep failing. Before anything else is done with it: why?", brief)
        for answer in ("contract", "too-large", "approach", "machine", "cannot-tell"):
            self.assertIn(f"- `{answer}`: ", brief)
        self.assertIn("stuck: 'checks' failed 2 times since it last passed", brief)
        self.assertIn(f"- Check: `{CHECK_ADD}`", brief)                # the ticket
        self.assertEqual(brief.count("- step `checks`, signature `checks:"), 2)   # each failed attempt
        self.assertIn("## The output of the last failed attempt", brief)
        self.assertIn("AssertionError", brief)
        self.assertIn("+    return a * b", brief)                       # the change as it stands
        self.assertEqual(json.loads(run["schema"])["properties"]["answer"]["enum"],
                         ["contract", "too-large", "approach", "machine", "cannot-tell"])

    def test_two_runs_with_no_answer_leave_the_ticket_where_it_was(self):
        a, b = self.remote_pair(config=CAPPED)
        a.add(ticket())
        a.rail("next")
        fail_twice(a)
        # The stand-in's queue is empty: it answers as a reviewer does, which is no answer to the question.
        dropped = a.rail("next", "--ticket", "1", expect=3)
        self.assertEqual((dropped["state"], dropped["reason"]["code"]), ("dropped", "DROPPED"))
        self.assertEqual([s["detail"].split(":")[0] for s in dropped["steps"] if s["step"] == "triage"],
                         ["invalid output", "invalid output"])
        self.assertNotIn("diagnosis", mark(a)["dropped"])

    def test_contract_sends_the_contract_writer_to_amend_and_the_amend_gives_a_fresh_budget(self):
        p = self.capped()
        p.queue_reviews(said("contract", evidence="Check: `python3 -c \"import calc\"`"),   # not a line of the ticket
                        said("contract", "The check never tries zero.",
                             evidence=f"- Check: `{CHECK_ADD}`"))
        task = p.rail("next", "--ticket", "1", expect=3)
        self.assertEqual([s["detail"] for s in task["steps"] if s["step"] == "triage"],
                         ["invalid output: this line is not in the Done Contract of the ticket: check: python3 -c"
                          " \"import calc\"", "Q1 stuck: contract"])
        self.assertEqual((task["owner"], task["reason"]["code"], task["action"]["kind"]),
                         ("agent", "STUCK_CONTRACT", "agent_task"))
        self.assertEqual((task["action"]["model"], task["action"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertIn("judged that the contract is at fault, not the work: The check never tries zero.", task["action"]["brief"])
        self.assertIn(f"- Check: `{CHECK_ADD}`", task["action"]["brief"])
        self.assertIn('rail amend 1 "why the contract was wrong"', task["action"]["brief"])
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "STUCK_CONTRACT")  # nothing ships under the old one

        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace("== 5", "== 5 and calc.add(0, 0) == 0"), base=p.worktree("1"))
        amended = p.rail("amend", "1", "the check left zero out")
        self.assertEqual((amended["owner"], amended["reason"]["code"]), ("agent", "STEP_FAILED"))  # a fresh budget and cap
        # At the cap again it is dropped as before, with the diagnosis in the record and no second one.
        again = fail_twice(p)
        self.assertEqual(again["reason"]["code"], "STUCK")
        self.assertEqual(p.rail("next", "--ticket", "1")["state"], "dropped")
        with open(p.path(".git", "rail", "ids", "1.dropped")) as f:
            dropped = json.load(f)["dropped"]
        self.assertEqual((dropped["by"], dropped["diagnosis"]), ("engine", "contract"))
        self.assertEqual(len(diagnoses(p)), 2)

    def test_approach_starts_the_branch_again_and_tells_the_worker_with_a_fresh_budget(self):
        a, b, github = self.github_pair(config=CAPPED)
        a.add(ticket())
        a.rail("next")
        fail_twice(a)
        a.queue_reviews(said("approach", evidence="Each attempt changes the operator to another wrong one. Use +."))
        work = a.rail("next", "--ticket", "1")
        self.assertEqual((work["state"], work["owner"], work["reason"]["code"]), ("implementing", "agent", "IMPLEMENT"))
        self.assertEqual(work["action"]["facts"]["branch"], "1-fix-add--2")
        self.assertEqual(work["action"]["facts"]["restarted"],
                         {"branch": "1-fix-add", "type": "stuck",
                          "note": "Each attempt changes the operator to another wrong one. Use +."})
        self.assertIn("a run that did not write them judged that they shared a mistake. What it names, and what to do"
                      " instead: Each attempt changes the operator to another wrong one. Use +.", work["action"]["brief"])
        with open(os.path.join(a.worktree("1"), "src", "calc.py")) as f:
            self.assertEqual(f.read(), "def add(a, b):\n    return a - b\n")  # none of the attempts' work is here
        self.assertEqual(github.pr(1)["state"], "closed")
        self.assertIn("a diagnosis judged that they share a mistake", github.read()["comments"]["1"][-1]["body"])
        (restarted,) = events(a, "restarted", "1-fix-add--2")
        self.assertEqual((restarted["type"], restarted["branch"], restarted["to"]), ("stuck", "1-fix-add", "1-fix-add--2"))
        # The budget and the cap start again: one more failure is a failed step, not the cap.
        a.write("src/calc.py", "def add(a, b):\n    return a * b\n", base=a.worktree("1"))
        self.assertEqual(a.rail("advance", "1", expect=3)["reason"]["code"], "STEP_FAILED")
        a.fix_calc("1")
        self.assertEqual(a.rail("advance", "1")["state"], "in-ci")
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "in-ci")

    def test_machine_is_the_wait_for_the_machine(self):
        p = self.capped()
        p.queue_reviews(said("machine", "Both attempts end before any test runs.",
                             evidence="ModuleNotFoundError: No module named 'yaml'"))
        wait = p.rail("next", "--ticket", "1")
        self.assertEqual((wait["owner"], wait["reason"]["code"], wait["action"]["facts"]["wait"]["kind"]),
                         ("person", "TOOL_DOWN", "grant"))
        self.assertIn("judged that the machine or a tool is at fault, not the change: Both attempts end before any test"
                      " runs. The failure it names: ModuleNotFoundError: No module named 'yaml'. A person mends that on"
                      " this machine, then continues the ticket: rail accept 1.", wait["action"]["brief"])
        p.rail("accept", "1")
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "STEP_FAILED")
        self.assertEqual(fail_twice(p)["reason"]["code"], "STUCK")  # at the cap again: as before

    def test_too_large_has_the_contract_writer_split_it_and_the_issue_stays_open_until_the_last_part_merges(self):
        a, b, github = self.github_pair(config=CAPPED)
        github.update(lambda s: s["issues"].append({"number": 12, "title": "Add can't add", "body": "add(2, 3) gives -1.",
                                                    "labels": ["rail"], "state": "open"}))
        a.rail("intake", "github")
        written = os.path.join(self.tmp, "1.md")
        with open(written, "w") as f:
            f.write(ticket(title="Add can't add", front=('external_id = "github#12"',)))
        a.rail("amend", "1", "--file", written)
        a.rail("next")
        fail_twice(a)
        a.queue_reviews(said("too-large", "The check needs add fixed and a status code.",
                             evidence="add returns the sum\nthe handler answers 201"))
        task = a.rail("next", "--ticket", "1")
        self.assertEqual((task["owner"], task["reason"]["code"]), ("agent", "STUCK_SPLIT"))
        self.assertEqual(task["action"]["facts"]["external_id"], "github#12")
        self.assertIn("The parts it names:\nadd returns the sum\nthe handler answers 201", task["action"]["brief"])
        self.assertIn("The engine then writes this ticket's issue (github#12) into each of them", task["action"]["brief"])
        self.assertIn('rail drop 1 --reason "split: why" --replaced-by A,B', task["action"]["brief"])

        a.add(ticket(title="Add returns the sum"))
        a.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        a.add(ticket(title="Another matter", scope=("docs/**",), check="grep -q sum docs/guide.md", front=('external_id = "github#40"',)))
        refused = a.rail("drop", "1", "--reason", "split: two parts", "--replaced-by", "2,4", expect=2)
        self.assertEqual(refused["reason"]["code"], "BAD_REPLACEMENT")
        self.assertIn("it names github#40 already", refused["reason"]["message"])
        self.assertEqual(a.rail("drop", "1", "--reason", "split", "--replaced-by", "1", expect=2)["reason"]["code"], "BAD_REPLACEMENT")
        a.rail("drop", "4", "--reason", "not needed")
        a.rail("drop", "1", "--reason", "split: two parts", "--replaced-by", "2,3")
        b.git("fetch", "--quiet", "origin")
        for branch in ("2-add-returns-the-sum", "3-add-a-status-code"):  # the engine wrote the issue into each part
            self.assertIn('external_id = "github#12"', b.git("show", f"origin/{branch}:.rail/tickets/{branch[0]}.md"))
        note = mark(a)["dropped"]
        self.assertEqual((note["by"], note["diagnosis"], note["replaced_by"]), ("agent", "too-large", ["2", "3"]))
        issue = github.read()["issues"][0]
        self.assertEqual((issue["state"], issue["labels"]), ("open", ["rail"]))
        self.assertIn("Ticket 1 was split into ticket 2, 3. Reason: split: two parts. This issue stays open until the"
                      " last of them merges.", github.read()["comments"]["12"][-1]["body"])
        self.assertEqual(a.rail("intake", "github")["created"], [])  # the issue is not taken in again

        # The first part to merge leaves the issue open, and the last closes it.
        self.assertEqual(a.rail("next")["ticket"], "2")
        a.fix_calc("2")
        a.rail("advance", "2")
        first = next(p for p in github.read()["pulls"] if p["head"].startswith("2-"))
        self.assertIn("Part of #12", first["body"])
        github.ci("2-add-returns-the-sum", "success")
        self.assertEqual(a.rail("advance", "2")["state"], "merged")
        self.assertEqual(a.rail("next")["ticket"], "3")
        a.write("api/handlers.py", "def handle():\n    return 201\n", base=a.worktree("3"))
        a.rail("advance", "3")
        last = next(p for p in github.read()["pulls"] if p["head"].startswith("3-"))
        self.assertIn("Closes #12", last["body"])

    def test_stats_count_the_diagnosed_tickets_by_answer_and_those_that_merged_afterwards(self):
        p = self.fixture(config=CAPPED)
        p.add(ticket())
        p.rail("next")
        fail_twice(p)
        p.queue_reviews(said("approach", evidence="Each attempt picks another wrong operator. Use +."))
        p.rail("next", "--ticket", "1")
        p.fix_calc("1")
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next")
        for code in ("202", "203"):
            p.write("api/handlers.py", f"def handle():\n    return {code}\n", base=p.worktree("2"))
            p.rail("advance", "2", expect=3)
        p.queue_reviews(CANNOT_TELL)
        self.assertEqual(p.rail("next", "--ticket", "2")["state"], "dropped")
        answer = p.rail("stats")
        self.assertEqual(answer["stats"]["stuck"], {"diagnosed": 2, "answers": {"approach": 1, "cannot-tell": 1},
                                                    "merged_after": 1})
        self.assertIn("Stuck tickets that got a diagnosis: 2 (approach 1, cannot-tell 1). Merged afterwards,"
                      " themselves or through the tickets that replaced them: 1.", answer["text"])
