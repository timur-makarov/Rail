"""The answer schema, engine/answer-v1.json: every answer a test reads is checked against it (railtest.check_shape),
and here the check is shown to fail when it should."""

import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import RailTest, check_shape, engine, ticket
from test_review import ADVISORY, BLOCKING, found

engine()
from rail import answers, table  # noqa: E402

ENGINE = os.path.dirname(answers.FILE)
# Facts not every brief is made of: they are there for a host that reads the answer.
NOT_IN_THE_BRIEF = {"title", "branch", "ticket_file", "conflicted"}


def situations(test):
    """Answers with facts, each from a fixture: {code: answer}."""
    p = test.fixture()
    p.add(ticket())
    got = [p.rail("next")]                                   # the ticket's work
    p.rail("advance", "1", expect=3)
    got.append(p.rail("next"))                               # the check fails: nothing was changed
    p.fix_calc("1")
    p.queue_reviews(found(BLOCKING, ADVISORY))
    got.append(p.rail("advance", "1", expect=3))             # the review leaves a blocking finding
    q = test.fixture("person")
    q.add(ticket(tier="PERSON"))
    got.append(q.rail("next", "1"))                          # a person approves the contract
    return {a["reason"]["code"]: a for a in got}


class Schema(RailTest):
    def test_an_answer_with_a_code_a_kind_an_owner_or_a_fact_the_schema_does_not_name_fails(self):
        work = situations(self)["IMPLEMENT"]
        self.assertEqual(answers.check(work, "next"), [])

        def planted(change):
            answer = copy.deepcopy(work)
            change(answer)
            with self.assertRaises(AssertionError):
                check_shape(answer, "next")
            return answers.check(answer, "next")

        self.assertEqual(planted(lambda a: a["reason"].update(code="PLANTED")),
                         ["$.reason.code: the schema names no code 'PLANTED'"])
        self.assertEqual(planted(lambda a: a["action"]["facts"].update(planted=1)),
                         ["$.action.facts: has a key the schema does not name, 'planted'"])
        self.assertEqual(planted(lambda a: a["action"].update(kind="person_wait")),
                         ["$.action.kind: IMPLEMENT is agent_task, not person_wait"])
        self.assertEqual(planted(lambda a: a.update(owner="person")), ["$.owner: IMPLEMENT belongs to agent, not person"])
        self.assertEqual(planted(lambda a: a.update(planted=1)), ["$: has a key the schema does not name, 'planted'"])
        self.assertEqual(planted(lambda a: a["action"]["facts"].pop("scope_paths")), ["$.action.facts: lacks 'scope_paths'"])
        self.assertEqual(planted(lambda a: a["action"]["facts"].update(migration="no")),
                         ["$.action.facts.migration: is str, not boolean"])
        self.assertEqual(planted(lambda a: a["action"].pop("facts")), ["$.action: IMPLEMENT from rail next has no facts"])
        self.assertEqual(planted(lambda a: a["action"].update(brief=a["action"]["brief"] + " And more.")),
                         ["$.action.brief: is not what IMPLEMENT's facts render"])

    def test_a_refusal_with_a_code_the_schema_does_not_name_fails(self):
        p = self.fixture()
        refused = p.rail("advance", "7", expect=2)
        self.assertEqual((refused["reason"]["code"], answers.check(refused)), ("NO_TICKET", []))
        refused["reason"]["code"] = "PLANTED"
        self.assertIn("'PLANTED' is not one of", answers.check(refused)[0])

    def test_a_wait_of_a_kind_the_schema_does_not_name_fails(self):
        wait = situations(self)["APPROVE_CONTRACT"]
        self.assertEqual(wait["action"]["facts"]["wait"], {"kind": "approval", "accept": "rail accept 1",
                                                           "drop": "rail drop 1 --by person"})
        wait["action"]["facts"]["wait"]["kind"] = "favour"
        self.assertEqual(answers.check(wait),
                         ["$.action.facts.wait.kind: 'favour' is not one of approval, grant, hold"])


class Facts(RailTest):
    def test_a_brief_is_what_its_facts_render_and_changes_when_a_fact_is_taken_away(self):
        for code, answer in situations(self).items():
            facts, brief = json.loads(json.dumps(answer["action"]["facts"])), answer["action"]["brief"]
            self.assertEqual(table.render(code, facts), brief, code)
            for key, value in facts.items():
                if key in NOT_IN_THE_BRIEF or value in (None, False, "", [], {}):
                    continue
                less = {k: v for k, v in facts.items() if k != key}
                try:
                    changed = table.render(code, less) != brief
                except KeyError:
                    changed = True  # the renderer can't write the brief without it
                self.assertTrue(changed, f"{code}: the brief is the same without the fact '{key}'")

    def test_the_findings_of_an_answer_are_the_ledgers_rows(self):
        review = situations(self)["ANSWER_FINDINGS"]["action"]["facts"]["findings"]
        self.assertEqual([(x["id"], x["severity"], x.get("file"), x.get("line"), x["claim"]) for x in review],
                         [("F1", "blocking", "src/calc.py", 2, BLOCKING["claim"]),
                          ("F2", "advisory", "src/calc.py", None, ADVISORY["claim"])])
        self.assertEqual(review[0]["check"], BLOCKING["check"])


class Named(RailTest):
    """What the engine can answer, read from its code, is in the schema."""

    def setUp(self):
        super().setUp()
        self.doc = answers.load()

    def test_every_row_of_the_table_is_in_the_schema_with_its_kind_and_owner(self):
        for code, owner, kind, _, _ in table.ROWS:
            named = self.doc["codes"][code]
            self.assertIn(kind, named["kinds"], code)
            self.assertIn(owner, named["owners"], code)

    def test_a_code_has_facts_in_the_schema_just_when_it_has_a_renderer(self):
        self.assertEqual({code for code, named in self.doc["codes"].items() if "facts" in named}, set(table.RENDER))

    def test_every_kind_of_wait_the_table_gives_is_in_the_schema(self):
        kinds = self.doc["$defs"]["wait"]["properties"]["kind"]["enum"]
        self.assertEqual(set(table.WAIT_KINDS.values()), set(kinds))
        for code in table.WAIT_KINDS:
            named = self.doc["codes"][code]
            self.assertIn("wait", named["facts"]["required" if named["kinds"] == ["person_wait"] else "properties"], code)

    def test_every_code_the_engine_names_with_code_equals_is_in_the_schema(self):
        errors = set(self.doc["error"]["properties"]["reason"]["properties"]["code"]["enum"])
        for name in sorted(os.listdir(os.path.join(ENGINE, "rail"))):
            if name.endswith(".py"):
                with open(os.path.join(ENGINE, "rail", name), encoding="utf-8") as f:
                    for code in re.findall(r'\bcode="([A-Z_]+)"', f.read()):
                        self.assertTrue(code in self.doc["codes"] or code in errors, f"{name}: {code}")

    def test_the_schema_goes_into_a_project_with_the_engine(self):
        p = self.fixture()
        self.assertTrue(os.path.exists(p.path(".rail", "engine", "answer-v1.json")))
