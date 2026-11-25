"""Kinds: a person is asked only about what a revert doesn't undo (rail docs kinds)."""

import json
import os
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "config.toml")
AUTH = {"src/auth/x.py": "def allowed(user):\n    return True\n"}
ACCESS = '[kinds]\naccess = ["src/auth/**"]\n\n'


def events(p, branch, kind=None, nn="1"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]
    return [e for e in rows if kind is None or e["event"] == kind]


def front(p, branch, nn="1"):
    text = p.git("show", f"{branch}:.rail/tickets/{nn}.md")
    return text.split("+++")[1]


class Kinds(RailTest):
    def test_a_kind_glob_makes_the_ticket_person_at_add_with_its_reason(self):
        p = self.fixture(config=ACCESS + CONFIG, files=AUTH)
        added = p.add(ticket(title="Check the role", scope=("src/auth/**",)))
        self.assertEqual((added["tier"], added["state"], added["owner"]), ("PERSON", "new", "human"))
        meta = front(p, "1-check-the-role")
        self.assertIn('tier = "PERSON"', meta)
        self.assertIn('person_reason = "access: src/auth/x.py"', meta)
        p.rail("accept", "1")
        accepted = events(p, "1-check-the-role", "accepted")[-1]
        self.assertEqual((accepted["tier"], accepted["kinds"]), ("PERSON", ["access"]))

    def test_an_authors_person_reason_is_kept(self):
        p = self.fixture(config=ACCESS + CONFIG, files=AUTH)
        p.add(ticket(title="Check the role", tier="PERSON", scope=("src/auth/**",),
                     front=('person_reason = "data-exposure: logs the session"',)))
        meta = front(p, "1-check-the-role")
        self.assertIn('person_reason = "data-exposure: logs the session"', meta)
        self.assertEqual(meta.count("person_reason"), 1)

    def test_an_auto_ticket_records_no_kinds(self):
        p = self.fixture(config=ACCESS + CONFIG, files=AUTH)
        p.add(ticket(scope=("src/calc.py",)))
        self.assertEqual(events(p, "1-fix-add", "accepted")[-1]["kinds"], [])

    def test_amend_that_reaches_a_kind_raises_the_tier_and_writes_the_reason(self):
        p = self.fixture(config=ACCESS + CONFIG, files=AUTH)
        self.assertEqual(p.add(ticket(scope=("src/calc.py",)))["tier"], "AUTO")
        p.rail("next")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace('"src/calc.py"', '"src/calc.py", "src/auth/**"'), base=p.worktree("1"))
        amended = p.rail("amend", "1", "the role check lives in auth")
        self.assertEqual(amended["tier"], "PERSON")
        with open(path) as f:
            text = f.read()
        self.assertIn('tier = "PERSON"', text)
        self.assertIn('person_reason = "access: src/auth/x.py"', text)
        accepted = events(p, "1-fix-add", "accepted")[-1]
        self.assertEqual((accepted["via"], accepted["tier"], accepted["kinds"]), ("amend", "PERSON", ["access"]))

    def test_a_changed_file_on_a_kind_raises_the_tier_at_ship_with_the_kind(self):
        # No path at add shows the scope reaches the kind; the file the change adds does.
        p = self.fixture(config='[kinds]\naccess = ["**/*_auth.py"]\n\n' + CONFIG)
        self.assertEqual(p.add(ticket())["tier"], "AUTO")
        p.rail("next")
        p.fix_calc("1")
        p.write("src/role_auth.py", "ROLE = 'admin'\n", base=p.worktree("1"))
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["tier"], shipped["reason"]["code"]), ("PERSON", "MERGE_BY_PERSON"))
        raised = events(p, "1-fix-add", "tier_raised")[0]
        self.assertEqual((raised["reason"], raised["kind"], raised["detail"]), ("kinds", "access", "src/role_auth.py"))

    def test_an_old_config_with_only_person_paths_raises_as_controls(self):
        p = self.fixture(config='person_paths = ["api/**"]\nmigration_paths = []\n' + CONFIG)
        added = p.add(ticket(title="Change the API", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        self.assertEqual(added["tier"], "PERSON")
        self.assertIn('person_reason = "controls: api/handlers.py"', front(p, "1-change-the-api"))

        p.add(ticket(scope=("src/**", "api/**")).replace("Fix add", "Fix add and the API"))
        self.assertIn('person_reason = "controls: api/handlers.py"', front(p, "2-fix-add-and-the-api", "2"))

    def test_the_seed_moves_workflows_and_agent_settings_to_runs_with_secrets(self):
        with open(SEED, "rb") as f:
            seed = tomllib.load(f)
        self.assertEqual(seed["kinds"]["runs-with-secrets"], [".github/workflows/**", ".claude/**"])
        self.assertFalse({".github/workflows/**", ".claude/**"} & set(seed["person_paths"]))
        p = self.fixture()  # a config with no [kinds] gets the same default
        added = p.add(ticket(title="Change the workflow", scope=(".github/workflows/**",), check="test -f AGENTS.md"))
        self.assertEqual(added["tier"], "PERSON")
        self.assertIn('person_reason = "runs-with-secrets: .github/workflows/rail.yml"',
                      front(p, "1-change-the-workflow"))

    def test_lint_fails_a_person_ticket_without_a_kind(self):
        p = self.fixture()
        refused = p.add(ticket(tier="PERSON", front=('person_reason = ""',)), expect=3)
        self.assertEqual(refused["reason"]["code"], "TICKET_LINT")
        self.assertIn("a PERSON ticket needs person_reason", refused["action"]["brief"])
        refused = p.add(ticket(tier="PERSON", front=('person_reason = "big: it is large"',)), expect=3)
        self.assertEqual(refused["reason"]["code"], "TICKET_LINT")
        self.assertIn("person_reason must start with a kind's id", refused["action"]["brief"])
        self.assertEqual(p.add(ticket(tier="PERSON", front=('person_reason = "money: a new paid plan"',)))["tier"],
                         "PERSON")

    def test_an_unknown_kind_in_the_config_is_refused(self):
        p = self.fixture(config='[kinds]\nacess = ["src/auth/**"]\n\n' + CONFIG)
        failed = p.rail("status", expect=2)
        self.assertIn("unknown key 'kinds.acess' (did you mean 'access'?)", failed["reason"]["message"])

    def test_rail_docs_kinds_lists_every_id(self):
        p = self.fixture()
        page = p.rail("docs", "kinds", raw=True).stdout
        for kind in ("data-loss", "data-shape", "data-exposure", "external-effect", "access", "runs-with-secrets",
                     "controls", "infrastructure", "money", "licence", "public-release"):
            self.assertIn(f"`{kind}`", page)


def clean():
    return {"summary": "Read the diff, ran the check.", "findings": []}


class Size(RailTest):
    def test_stats_set_auto_tickets_over_the_cap_beside_those_under_it(self):
        # Size raises no tier, so stats show what a large AUTO change costs: reverted, or named in a fix's caused_by.
        p = self.fixture(config=CONFIG + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/more.py", "".join(f"x{i} = {i}\n" for i in range(12)), base=p.worktree("1"))
        self.assertEqual(p.rail("advance", "1")["reason"]["code"], "SPLIT")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["tier"], "AUTO")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        p.add(ticket(title="Say what add does", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("2"))
        p.queue_reviews(clean())
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        p.add(ticket(title="Fix more", front=('caused_by = "1"',)))
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["size"], {"cap": 10, "over": {"merged": 1, "reverted_or_fixed": 1},
                                                  "under": {"merged": 1, "reverted_or_fixed": 0}})
        self.assertIn("AUTO tickets over [size] cap of 10: 1 merged, 1 reverted or named in a later ticket's"
                      " caused_by. Under it: 1 merged, 0.", stats["text"])
