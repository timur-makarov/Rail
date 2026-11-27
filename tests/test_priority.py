"""A ticket a person marked to go first: the line in the ticket, the label on its pull request or on its issue."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import APPROVE, CONFIG, RailTest, ticket

FIRST = ('priority = "first"',)
DOCS = dict(title="Write the guide", scope=("docs/**",), check="test -f docs/guide.md")


def row(fx, nn):
    return next(r for r in fx.rail("status")["tickets"] if r["ticket"] == nn)


class Line(RailTest):
    def test_rail_next_takes_the_ticket_marked_first_before_one_with_a_lower_number(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(front=FIRST, **DOCS))
        self.assertEqual((row(p, "1").get("first"), row(p, "2")["first"], row(p, "2")["note"]), (None, True, "goes first"))
        taken = p.rail("next")
        self.assertEqual((taken["ticket"], taken["reason"]["code"]), ("2", "IMPLEMENT"))

    def test_two_tickets_marked_first_go_in_the_order_of_their_numbers(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(front=FIRST, **DOCS))
        p.add(ticket(title="Add a licence", scope=("LICENSE",), check="test -f LICENSE", front=FIRST))
        self.assertEqual(p.rail("next")["ticket"], "2")

    def test_the_work_a_session_holds_comes_before_new_work_marked_first(self):
        p = self.fixture()
        p.add(ticket())
        self.assertEqual(p.rail("next")["ticket"], "1")
        p.add(ticket(front=FIRST, **DOCS))
        self.assertEqual(p.rail("next")["ticket"], "1")
        self.assertEqual(p.rail("next", session="session-b")["ticket"], "2")  # new work for a session with none

    def test_lint_refuses_a_priority_that_is_not_first(self):
        p = self.fixture()
        refused = p.add(ticket(front=('priority = "soon"',)), expect=3)
        self.assertEqual(refused["reason"]["code"], "TICKET_LINT")
        self.assertIn('priority must be "first", or left out', refused["action"]["brief"])

    def test_rail_amend_marks_a_filed_ticket_and_the_journal_says_what_changed(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(**DOCS))
        marked = os.path.join(self.tmp, "2.md")
        with open(marked, "w") as f:
            f.write(ticket(front=FIRST, **DOCS))
        p.rail("amend", "2", "the release waits for the guide", "--file", marked)
        events = [json.loads(line) for line in p.git("show", "2-write-the-guide:.rail/journal/2-events.jsonl").splitlines()]
        amended = next(e for e in events if e["event"] == "amended")
        self.assertEqual((amended["changed"], amended["needs_approval"]), (["priority"], False))
        self.assertEqual(p.rail("next")["ticket"], "2")


class Label(RailTest):
    def test_the_label_on_the_issue_a_ticket_came_from_puts_it_first(self):
        a, b, github = self.github_pair()
        github.update(lambda s: s["issues"].extend(
            {"number": n, "title": f"Request {n}", "body": "Please.", "labels": labels, "state": "open"}
            for n, labels in ((12, ["rail"]), (13, ["rail", "rail:first"]))))
        taken = a.rail("next")
        self.assertEqual((taken["ticket"], taken["reason"]["code"]), ("2", "TICKET_LINT"))
        self.assertEqual((row(a, "1").get("first"), row(a, "2")["first"]), (None, True))

    def test_the_label_on_a_tickets_pull_request_puts_it_first(self):
        a, b, github = self.github_pair(config=APPROVE + CONFIG)
        a.add(ticket(tier="PERSON"))
        a.add(ticket(tier="PERSON", **DOCS))
        for number in (1, 2):
            github.label(number, "rail:go")
        github.label(2, "rail:first")
        taken = a.rail("next")
        self.assertEqual((taken["ticket"], taken["reason"]["code"]), ("2", "IMPLEMENT"))
