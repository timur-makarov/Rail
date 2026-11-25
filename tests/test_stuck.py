"""STUCK: an AUTO ticket at the retry cap is dropped with a record, and a drop never removes anything before its mark
is written. A PERSON ticket keeps every wait (proposals/responsibility.md, Part 4)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

CAPPED = CONFIG + "\n[retry]\nbudget = 9\ncap = 2\n"  # two failures of any kind are the cap; consult never comes


def fail_twice(p, nn="1"):
    """Two failed ships at 'checks', each a different failure."""
    for body in ("return a - b", "return a * b"):
        p.write("src/calc.py", f"def add(a, b):\n    {body}\n", base=p.worktree(nn))
        last = p.rail("advance", nn, expect=3)
    return last


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
                         ("agent", "STUCK", "rail next --ticket 1"))
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
        issue = github.read()["issues"][0]
        self.assertNotIn("rail", issue["labels"])
        comment = " ".join(github.read()["comments"]["12"][0]["body"].split())
        self.assertIn("'checks' failed 2 times since it last passed", comment)
        self.assertIn("Label this issue `rail` again to retry", comment)
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "dropped")

    def test_a_person_ticket_at_the_cap_still_waits(self):
        p = self.fixture(config=CAPPED)
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        capped = fail_twice(p)
        self.assertEqual((capped["owner"], capped["reason"]["code"]), ("human", "RETRY_CAP"))
        self.assertTrue(os.path.exists(p.worktree("1")))


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
        self.assertEqual(mark(a)["dropped"], {"by": "agent", "reason": "not needed"})


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
        self.assertEqual(json.loads(note)["dropped"], {"by": "agent", "reason": "it only made sense with the status code"})
