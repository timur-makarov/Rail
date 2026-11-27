"""A PERSON ticket takes one act: the merge. A person approves a contract before the build only for a kind the
project names in `approve_contract` (rail docs kinds)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket
from test_review import clean

API = dict(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py")
MONEY = dict(tier="PERSON", front=('person_reason = "money: the price of a plan"',))
ASKED = 'approve_contract = ["money"]\n'


def events(p, branch, kind):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if e["event"] == kind]


def read(path):
    with open(path) as f:
        return f.read()


class OneAct(RailTest):
    def test_a_ticket_on_person_paths_is_built_with_no_wait_and_stops_at_the_persons_merge(self):
        p = self.fixture(config='person_paths = ["api/**"]\n' + CONFIG)
        added = p.add(ticket(**API))
        self.assertEqual((added["tier"], added["owner"], added["reason"]["code"]), ("PERSON", "agent", "ACCEPT_AUTO"))
        work = p.rail("next")
        self.assertEqual((work["state"], work["reason"]["code"]), ("implementing", "IMPLEMENT"))
        (accepted,) = events(p, "1-add-a-status-code", "accepted")
        self.assertEqual((accepted["by"], accepted["tier"], accepted["kinds"]), ("engine", "PERSON", ["controls"]))
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("1"))
        p.queue_reviews(clean(), clean())  # the reviewer, and the security seat a PERSON ticket still gets
        ready = p.rail("advance", "1")
        self.assertEqual((ready["owner"], ready["reason"]["code"]), ("person", "MERGE_BY_PERSON"))
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "MERGE_BY_PERSON")  # the engine does not merge it
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        acts = [e for e in [json.loads(l) for l in p.git("show", "main:.rail/journal/1-events.jsonl").splitlines()]
                if e["event"] == "continued" or (e["event"] == "accepted" and e["by"] == "person")]
        self.assertEqual([(e["event"], e["wait"]) for e in acts], [("continued", "MERGE_BY_PERSON")])  # the one act

    def test_its_amended_contract_is_a_read_these_row_and_no_wait(self):
        a, b, github = self.github_pair(config='person_paths = ["api/**"]\n' + CONFIG)
        a.add(ticket(**API))
        a.rail("next")
        path = os.path.join(a.worktree("1"), ".rail", "tickets", "1.md")
        a.write(".rail/tickets/1.md", read(path).replace("grep -q 201 api/handlers.py",
                                                         "grep -q 'return 201' api/handlers.py"), base=a.worktree("1"))
        amended = a.rail("amend", "1", "the check matched a comment")
        self.assertEqual((amended["owner"], amended["reason"]["code"]), ("agent", "IMPLEMENT"))
        (record,) = events(a, "1-add-a-status-code", "amended")
        self.assertEqual((record["changed"], record["needs_approval"]), (["done_contract"], False))
        a.write("api/handlers.py", "def handle():\n    return 201\n", base=a.worktree("1"))
        a.queue_reviews(clean(), clean())
        a.rail("advance", "1")
        self.assertIn("- The ticket: the Done Contract changed after it was accepted, with no person: the check matched"
                      " a comment (an amend)", github.pr(1)["body"])

    def test_a_kind_the_project_names_waits_before_the_build_and_another_kind_does_not(self):
        p = self.fixture(config=ASKED + CONFIG)
        priced = p.add(ticket(title="Change the price", **MONEY))
        self.assertEqual((priced["owner"], priced["reason"]["code"]), ("person", "APPROVE_CONTRACT"))
        shaped = p.add(ticket(title="Rename a column", tier="PERSON", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        self.assertEqual((shaped["owner"], shaped["reason"]["code"]), ("agent", "ACCEPT_AUTO"))
        work = p.rail("next")
        self.assertEqual((work["ticket"], work["reason"]["code"]), ("2", "IMPLEMENT"))  # the other kind is built
        self.assertEqual(p.rail("next", "1")["reason"]["code"], "APPROVE_CONTRACT")      # the named kind still waits
        p.rail("accept", "1")
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "IMPLEMENT")
        # An amend of its Done Contract waits for the person too, as its contract did.
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace("== 5", "== 5 and calc.add(0, 0) == 0"), base=p.worktree("1"))
        waiting = p.rail("amend", "1", "the check missed zero")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("person", "APPROVE_AMEND"))

    def test_a_kind_reached_by_a_path_waits_where_the_project_names_it(self):
        p = self.fixture(config='approve_contract = ["controls"]\nperson_paths = ["api/**"]\n' + CONFIG)
        self.assertEqual(p.add(ticket(**API))["reason"]["code"], "APPROVE_CONTRACT")

    def test_approve_contract_takes_kind_ids_only(self):
        p = self.fixture()
        p.write(".rail/config.toml", 'approve_contract = ["monney"]\n' + CONFIG)
        refused = p.rail("status", expect=2)
        self.assertIn("approve_contract names 'monney', which is no kind (did you mean 'money'?)", refused["reason"]["message"])


class Refused(RailTest):
    def test_stats_counts_the_person_tickets_a_person_closed_without_a_merge_by_kind(self):
        a, b, github = self.github_pair()
        a.add(ticket(title="Change the price", **MONEY))
        a.add(ticket(title="Fix add"))
        a.rail("next", "--ticket", "1")
        a.fix_calc("1")
        a.queue_reviews(clean(), clean())
        a.rail("advance", "1")
        # The person reads the change and closes its pull request: no merge.
        github.update(lambda s: s["pulls"][0].__setitem__("state", "closed"))
        a.rail("next")
        self.assertFalse(os.path.exists(a.worktree("1")))
        a.rail("drop", "2", "--by", "person")  # an AUTO ticket a person drops is no refusal of a PERSON ticket
        found = a.rail("stats")["stats"]
        self.assertEqual(found["drops"]["by"], {"person": 2})
        self.assertEqual(found["drops"]["person_refused"], {"money": 1})
        text = a.rail("stats", raw=True).stdout
        self.assertIn("PERSON tickets a person closed without a merge, by kind: money 1.", text)
        self.assertEqual(b.rail("stats")["stats"]["drops"]["person_refused"], {"money": 1})  # the mark holds it for every clone

    def test_the_sweep_names_a_kind_a_person_refused_three_times_among_the_last_20(self):
        p = self.fixture(config=CONFIG + "\n[sweep]\nevery = 1\n")
        for n in range(3):
            p.add(ticket(title=f"Change price {n}", **MONEY))
            p.rail("drop", str(n + 1), "--by", "person")
        p.add(ticket(title="Rename a column", tier="PERSON"))
        p.rail("drop", "4", "--by", "person")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("5")
        p.rail("advance", "5")
        p.rail("advance", "5")
        swept = p.rail("sweep")
        self.assertEqual(swept["reason"]["code"], "SWEEP_TICKETS")
        summary = read(os.path.join(p.worktree("6"), ".rail", "journal", "6-summary.md"))
        self.assertIn("## Kinds a person refuses at the merge\n- `money`: a person closed 3 of the last 20 PERSON tickets"
                      " without a merge, and they were of this kind.", summary)
        self.assertIn("puts `money` into `approve_contract`", summary)
        self.assertNotIn("`data-shape`: a person closed", summary)  # once is not a pattern

        # Named in approve_contract, the kind is no longer proposed.
        q = self.fixture("named", config=ASKED + CONFIG + "\n[sweep]\nevery = 1\n")
        for n in range(3):
            q.add(ticket(title=f"Change price {n}", **MONEY))
            q.rail("drop", str(n + 1), "--by", "person")
        q.add(ticket())
        q.rail("next")
        q.fix_calc("4")
        q.rail("advance", "4")
        q.rail("advance", "4")
        q.rail("sweep")
        self.assertIn("## Kinds a person refuses at the merge\n(none)",
                      read(os.path.join(q.worktree("5"), ".rail", "journal", "5-summary.md")))
