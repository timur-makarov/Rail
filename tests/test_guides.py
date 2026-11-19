"""Guides: the [guides] page a brief names when its situation applies, the `guided` event, and what stats makes of it."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, Fixture, RailTest, ticket

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed")
SKILL = ".claude/skills/{}/SKILL.md"
PAGES = {"start": "rail-build", "stuck": "rail-debug", "findings": "rail-findings", "conflict": "rail-conflict",
         "contract": "rail-blast-radius", "split": "rail-slice", "setup": "rail-verify"}
BLOCKING = {"severity": "blocking", "file": "src/calc.py", "line": 2, "claim": "add(-1, 1) returns the wrong sign."}


def guides(**pages):
    """A [guides] table: the seed's pages, with any key given here set to that path, or left out when None."""
    lines = ["", "[guides]"]
    for key, name in PAGES.items():
        path = pages.get(key, SKILL.format(name))
        if path is not None:
            lines.append(f'{key} = "{path}"')
    return CONFIG + "\n".join(lines) + "\n"


def line(situation):
    return f"Guide: read {SKILL.format(PAGES[situation])} and follow it."


def events(p, branch="1-fix-add", nn="1", kind="guided"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]
    return [e for e in rows if e["event"] == kind]


class Situations(RailTest):
    def test_start_is_named_in_the_first_implement_brief_only(self):
        p = self.fixture(config=guides())
        p.add(ticket())
        first = p.rail("next")
        self.assertEqual(first["reason"]["code"], "IMPLEMENT")
        self.assertTrue(first["action"]["brief"].endswith("\n\n" + line("start")), first["action"]["brief"])
        self.assertEqual(first["guide"], {"situation": "start", "path": SKILL.format("rail-build")})
        self.assertEqual([(e["situation"], e["path"]) for e in events(p)], [("start", SKILL.format("rail-build"))])
        again = p.rail("next")
        self.assertEqual(again["reason"]["code"], "IMPLEMENT")
        self.assertNotIn("Guide:", again["action"]["brief"])
        self.assertNotIn("guide", again)
        self.assertEqual(len(events(p)), 1)

    def test_stuck_is_named_once_the_same_failure_repeats(self):
        p = self.fixture(config=guides())
        p.add(ticket())
        p.rail("next")
        first = p.rail("advance", "1", expect=3)
        self.assertEqual(first["reason"]["code"], "STEP_FAILED")
        self.assertNotIn("Guide:", first["action"]["brief"])
        second = p.rail("advance", "1", expect=3)  # the same failure again: consult advises, and the guide is named
        self.assertEqual(second["reason"]["code"], "STEP_FAILED")
        self.assertIn("consult says", second["action"]["brief"])
        self.assertIn(line("stuck"), second["action"]["brief"])
        self.assertEqual(second["guide"]["situation"], "stuck")
        self.assertIn(line("stuck"), p.rail("next")["action"]["brief"])
        self.assertEqual([e["situation"] for e in events(p)], ["start", "stuck"])  # one event per situation

    def test_findings_are_named_with_the_review_findings(self):
        p = self.fixture(config=guides())
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews({"summary": "Read it.", "findings": [BLOCKING]})
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed["reason"]["code"], "ANSWER_FINDINGS")
        self.assertIn(line("findings"), failed["action"]["brief"])
        self.assertEqual(failed["guide"]["situation"], "findings")
        self.assertEqual([e["situation"] for e in events(p)], ["start", "findings"])

    def test_split_is_named_in_the_split_brief(self):
        p = self.fixture(config=guides() + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/more.py", "".join(f"x{i} = {i}\n" for i in range(12)), base=p.worktree("1"))
        offered = p.rail("advance", "1")
        self.assertEqual(offered["reason"]["code"], "SPLIT")
        self.assertIn(line("split"), offered["action"]["brief"])
        self.assertEqual([e["situation"] for e in events(p)], ["start", "split"])

    def test_contract_is_named_for_a_ticket_that_came_in_as_a_request(self):
        p = self.fixture(config=guides())
        brief = os.path.join(self.tmp, "brief.txt")
        with open(brief, "w") as f:
            f.write("Customers see negative totals.\n")
        p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix totals", "--brief", brief)
        stub = p.rail("next")
        self.assertEqual(stub["reason"]["code"], "TICKET_LINT")
        self.assertIn(line("contract"), stub["action"]["brief"])
        self.assertEqual([e["situation"] for e in events(p, "1-proj-7-fix-totals")], ["contract"])

    def test_setup_is_named_in_the_init_task_with_no_event(self):
        p = Fixture(os.path.join(self.tmp, "fresh"), init=False)
        p.rail("init")  # the seed config, with its [guides] table
        task = p.rail("next")
        self.assertEqual(task["reason"]["code"], "INIT_TASK")
        self.assertIn(line("setup"), task["action"]["brief"])
        self.assertEqual(task["guide"], {"situation": "setup", "path": SKILL.format("rail-verify")})

    def test_conflict_is_named_by_the_ship_that_met_the_conflict(self):
        # The agent starts the rebase from this brief, so the page for it is named here and not only mid-rebase.
        a, b = self.remote_pair(config=guides())
        a.add(ticket())
        a.rail("next")
        a.fix_calc("1")
        b.git("pull", "--quiet")
        b.write("src/calc.py", "def add(a, b):\n    return b + a  # theirs\n")
        b.git("commit", "--quiet", "-am", "theirs")
        b.git("push", "--quiet", "origin", "main")
        failed = a.rail("advance", "1", expect=3)
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["result"]), ("rebase", "fail"))
        self.assertIn(line("conflict"), failed["action"]["brief"])
        self.assertEqual(failed["guide"]["situation"], "conflict")

    def test_conflict_is_named_while_a_rebase_is_stopped_and_nothing_is_written(self):
        a, b = self.remote_pair(config=guides())
        a.add(ticket())
        a.rail("next")
        tree = a.worktree("1")
        a.write("src/calc.py", "def add(a, b):\n    return a + b\n", base=tree)
        a.git("commit", "--quiet", "-am", "1: mine", cwd=tree)
        b.git("pull", "--quiet")
        b.write("src/calc.py", "def add(a, b):\n    return b + a  # theirs\n")
        b.git("commit", "--quiet", "-am", "theirs")
        b.git("push", "--quiet", "origin", "main")
        a.git("fetch", "--quiet")
        subprocess.run(["git", "rebase", "origin/main"], cwd=tree, capture_output=True, text=True)
        tip = a.git("rev-parse", "1-fix-add")
        told = a.rail("next")
        self.assertEqual(told["reason"]["code"], "REBASING")
        self.assertIn(line("conflict"), told["action"]["brief"])
        self.assertEqual(told["guide"]["situation"], "conflict")
        self.assertEqual(a.git("rev-parse", "1-fix-add"), tip)  # no guided event: the engine writes nothing mid-rebase


class Off(RailTest):
    def test_with_no_guides_table_no_brief_names_a_guide(self):
        p = self.fixture()  # the test config has no [guides] table, as no project before this change had
        p.add(ticket())
        for answer in (p.rail("next"), p.rail("advance", "1", expect=3), p.rail("advance", "1", expect=3)):
            self.assertNotIn("Guide:", answer["action"]["brief"])
            self.assertNotIn("guide", answer)
        self.assertEqual(events(p), [])
        self.assertNotIn("guides", {s["step"] for s in p.rail("doctor", expect=None)["steps"]})

    def test_a_deleted_key_names_no_guide(self):
        p = self.fixture(config=guides(start=None))
        p.add(ticket())
        self.assertNotIn("Guide:", p.rail("next")["action"]["brief"])
        self.assertEqual(events(p), [])

    def test_a_page_that_is_not_there_names_nothing_and_doctor_says_so(self):
        p = self.fixture(config=guides(start="docs/build.md"))
        p.add(ticket())
        self.assertNotIn("Guide:", p.rail("next")["action"]["brief"])
        self.assertEqual(events(p), [])
        found = {s["step"]: s for s in p.rail("doctor", expect=None)["steps"]}
        self.assertEqual(found["guides"]["result"], "fail")
        self.assertIn("start = docs/build.md", found["guides"]["detail"])

    def test_an_unknown_key_is_a_config_error(self):
        p = self.fixture(config=CONFIG + '\n[guides]\nstarting = "x.md"\n')
        failed = p.rail("next", expect=2)
        self.assertIn("unknown key 'guides.starting' (did you mean 'start'?)", failed["reason"]["message"])


class Stats(RailTest):
    def merge(self, p, nn, path, text):
        p.rail("next", "--ticket", nn)
        p.write(path, text, base=p.worktree(nn))
        p.queue_reviews({"summary": "Read it.", "findings": []})
        self.assertEqual(p.rail("advance", nn)["state"], "merge-ready")
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

    def test_stats_counts_tickets_with_the_start_guide_beside_the_rest(self):
        p = self.fixture(config=guides(start=None).replace("[consult]", "[retry]\nbudget = 1\n\n[consult]"))
        p.add(ticket())
        p.rail("next")
        p.rail("advance", "1", expect=3)  # the budget of 1 is used: consult advises
        self.assertEqual(p.rail("advance", "1", expect=3)["reason"]["code"], "RETRY_CAP")  # then a person looks
        p.rail("accept", "1", "fix add")
        self.merge(p, "1", "src/calc.py", "def add(a, b):\n    return a + b\n")
        stats = p.rail("stats")
        self.assertNotIn("GUIDES", stats["text"])  # nothing was guided yet
        p.write(".rail/config.toml", guides())
        p.git("commit", "--quiet", "-am", "name the start guide")
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        self.merge(p, "2", "api/handlers.py", "def handle():\n    return 201\n")
        stats = p.rail("stats")
        found = stats["stats"]["guides"]
        self.assertEqual({k: found["guided"][k] for k in ("tickets", "failed_steps", "review_runs", "waited")},
                         {"tickets": 1, "failed_steps": 0, "review_runs": 1, "waited": 0})
        self.assertEqual({k: found["not guided"][k] for k in ("tickets", "failed_steps_per_ticket", "review_runs_per_ticket")},
                         {"tickets": 1, "failed_steps_per_ticket": 2.0, "review_runs_per_ticket": 1.0})
        self.assertEqual(found["not guided"]["waited"], 1)
        self.assertEqual(found["situations"], {"start": 1})
        self.assertIn("GUIDES", stats["text"])
        self.assertIn("Guides named: start 1.", stats["text"])


class Init(RailTest):
    def test_init_copies_every_skill(self):
        p = Fixture(os.path.join(self.tmp, "fresh"), init=False)
        p.rail("init")
        names = sorted(os.listdir(os.path.join(SEED, "skills")))
        self.assertIn("rail-grill", names)
        for name in names:
            with open(os.path.join(SEED, "skills", name, "SKILL.md")) as f, open(p.path(SKILL.format(name))) as g:
                self.assertEqual(f.read(), g.read(), name)
