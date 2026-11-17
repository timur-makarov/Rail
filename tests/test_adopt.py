"""rail adopt: work already on a branch with no ticket comes onto the rail, behind the same checks as any ticket."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, CONFIG, RailTest, ticket

FIXED = "def add(a, b):\n    return a + b\n"


def prototype(p, files=None, message="Make add add", back=True):
    """A branch `proto` with commits and no ticket, as a person prototypes outside Rail."""
    p.git("checkout", "--quiet", "-b", "proto")
    for path, text in (files or {"src/calc.py": FIXED}).items():
        p.write(path, text)
    p.git("add", "-A")
    p.git("commit", "--quiet", "-m", message)
    if back:
        p.git("checkout", "--quiet", "main")
    return p.git("rev-parse", "proto").strip()


def fill(path, checks=(CHECK_ADD,), title="Make add add", assumed=False):
    """What the agent writes into the draft: the title, Why, Out of scope and one Check: line per behaviour."""
    with open(path) as f:
        text = f.read()
    text = text.replace('title = ""', f'title = "{title}"')
    text = text.replace("## Why\n", "## Why\nadd subtracted instead of adding.\n")
    text = text.replace("## Out of scope\n", "## Out of scope\n- Other operations.\n")
    text = text.replace("## Done Contract\n", "## Done Contract\n" + "".join(f"- Check: `{c}`\n" for c in checks))
    if assumed:
        text = text.replace("## Assumptions\n", "## Assumptions\n- ASSUMED: the commit message says why.\n")
    with open(path, "w") as f:
        f.write(text)
    return path


def journal(p, ref):
    return [json.loads(line) for line in p.git("show", f"{ref}:.rail/journal/1-events.jsonl").splitlines()]


class Draft(RailTest):
    def test_the_first_step_drafts_scope_and_tier_from_the_branch_and_creates_nothing(self):
        p = self.fixture(files={"src/other.py": "z = 0\n"})
        prototype(p, {"src/calc.py": FIXED, "src/sum/one.py": "x = 1\n", "src/sum/two.py": "y = 2\n"}, back=False)
        branches = p.git("branch")
        drafted = p.rail("adopt")  # the current branch
        self.assertEqual((drafted["reason"]["code"], drafted["owner"], drafted["action"]["kind"]),
                         ("ADOPT", "agent", "agent_task"))
        self.assertEqual((drafted["branch"], drafted["tier"], drafted["size"]), ("proto", "AUTO", 4))
        self.assertIn({"path": "src/calc.py", "added": 1, "deleted": 1}, drafted["files"])
        brief = drafted["action"]["brief"]
        for text in ("src/calc.py (+1 -1)", "Size: 4 changed lines; [size] cap is 600", "Tier: AUTO", "Make add add",
                     "## Why and ## Out of scope", "ASSUMED:", "fails on main and passes on proto",
                     f"rail adopt proto {drafted['draft']}"):
            self.assertIn(text, brief)
        # The draft is outside the repository. A new folder whose every file the branch adds becomes one glob; a
        # folder with files the branch didn't touch stays a list of files.
        self.assertFalse(os.path.realpath(drafted["draft"]).startswith(os.path.realpath(p.root)))
        with open(drafted["draft"]) as f:
            text = f.read()
        self.assertIn('scope_paths = ["src/calc.py", "src/sum/**"]', text)
        self.assertIn('tier = "AUTO"', text)
        self.assertIn("## Why\n\n## Done Contract\n\n", text)
        self.assertEqual(p.git("branch"), branches)
        self.assertEqual(p.rail("status")["tickets"], [])

    def test_a_person_path_or_a_size_over_the_cap_makes_the_draft_person(self):
        p = self.fixture(config='person_paths = ["api/**"]\n' + CONFIG)
        prototype(p, {"api/handlers.py": "def handle():\n    return 201\n"})
        drafted = p.rail("adopt", "proto")
        self.assertEqual(drafted["tier"], "PERSON")
        self.assertIn("Tier: PERSON, because it changes api/handlers.py, on person_paths", drafted["action"]["brief"])

        q = self.fixture("big", config=CONFIG + "\n[size]\ncap = 5\n")
        prototype(q, {"src/big.py": "".join(f"x{i} = {i}\n" for i in range(10))})
        drafted = q.rail("adopt", "proto")
        self.assertEqual(drafted["tier"], "PERSON")
        self.assertIn("it changes 10 lines, over [size] cap of 5", drafted["action"]["brief"])


class Refusals(RailTest):
    def test_what_cannot_be_adopted_is_refused_with_a_reason(self):
        p = self.fixture()
        self.assertEqual(p.rail("adopt", "nope", expect=2)["reason"]["code"], "NO_BRANCH")
        refused = p.rail("adopt", expect=2)  # on main
        self.assertEqual(refused["reason"]["code"], "NOT_ADOPTABLE")
        self.assertIn("base branch", refused["reason"]["message"])
        p.git("branch", "empty")
        self.assertEqual(p.rail("adopt", "empty", expect=2)["reason"]["code"], "NO_COMMITS")
        p.add(ticket())
        refused = p.rail("adopt", "1-fix-add", expect=2)
        self.assertIn("ticket 1's own branch", refused["reason"]["message"])
        prototype(p, back=False)
        p.write("src/calc.py", FIXED + "# more\n")
        refused = p.rail("adopt", expect=2)
        self.assertEqual(refused["reason"]["code"], "UNCOMMITTED")
        self.assertIn("commit it", refused["reason"]["message"])


class Gate(RailTest):
    def test_a_check_green_on_the_base_or_not_green_on_the_branch_refuses_and_nothing_is_created(self):
        p = self.fixture()
        prototype(p)
        draft = p.rail("adopt", "proto")["draft"]
        green_on_base = "grep -q def src/calc.py"
        never = "grep -q multiply src/calc.py"
        fill(draft, checks=(CHECK_ADD, green_on_base, never, "no-such-tool-for-rail"))
        refused = p.rail("adopt", "proto", draft, expect=3)
        self.assertEqual(refused["reason"]["code"], "ADOPT_CHECKS")
        self.assertEqual(refused["checks"], [
            {"command": CHECK_ADD, "base": "red", "branch": "green"},
            {"command": green_on_base, "base": "green", "branch": "green"},
            {"command": never, "base": "red", "branch": "red"},
            {"command": "no-such-tool-for-rail", "base": "could_not_run", "branch": "could_not_run"}])
        brief = refused["action"]["brief"]
        self.assertIn(f"- NO: `{green_on_base}`: green on main, green on proto", brief)
        self.assertIn("could not run or timed out on the base counts as not red", brief)
        self.assertEqual(p.git("branch", "--list", "1-*"), "")
        self.assertEqual(p.rail("status")["tickets"], [])
        self.assertEqual(p.git("worktree", "list").count("\n"), 1)  # the throwaway worktrees are gone
        empty = p.rail("adopt", "proto")["draft"]
        self.assertEqual(p.rail("adopt", "proto", empty, expect=3)["reason"]["code"], "TICKET_LINT")
        # The ID wasn't taken: the adoption that passes gets ticket 1.
        ok = p.rail("adopt", "proto", fill(empty))
        self.assertEqual(ok["ticket"], "1")

    def test_setup_runs_before_the_checks_on_both_sides(self):
        p = self.fixture(config=CONFIG.replace("[commands]\n", "[commands]\nsetup = \"touch .ready\"\n"))
        prototype(p)
        draft = fill(p.rail("adopt", "proto")["draft"], checks=(CHECK_ADD + " && test -f .ready",))
        self.assertEqual(p.rail("adopt", "proto", draft)["reason"]["code"], "ADOPTED")


class Adopted(RailTest):
    def test_an_adopted_branch_walks_to_merged_through_the_normal_steps(self):
        p = self.fixture()
        head = prototype(p)
        draft = fill(p.rail("adopt", "proto")["draft"])
        adopted = p.rail("adopt", "proto", draft)
        self.assertEqual((adopted["ticket"], adopted["state"], adopted["owner"], adopted["reason"]["code"]),
                         ("1", "implementing", "agent", "ADOPTED"))
        self.assertEqual(adopted["action"]["command"], "rail advance 1")
        self.assertIn("Ticket 1 holds the work of branch proto", adopted["action"]["brief"])
        # The ticket's branch holds the adopted commits; the adopted branch is left as it was.
        branch = adopted["branch"]
        self.assertEqual(branch, "1-make-add-add")
        p.git("merge-base", "--is-ancestor", head, branch)
        self.assertEqual(p.git("rev-parse", "proto").strip(), head)
        events = journal(p, branch)
        self.assertEqual([e["event"] for e in events], ["requested", "accepted", "adopted", "base_checks", "claimed"])
        self.assertEqual(events[0]["via"], "adopt")
        self.assertEqual((events[2]["branch"], events[2]["head"]), ("proto", head[:12]))
        self.assertEqual(events[3]["checks"], [{"command": CHECK_ADD, "result": "red"}])
        self.assertEqual(events[3]["base"], p.git("rev-parse", "main").strip()[:12])

        self.assertEqual(p.rail("next")["reason"]["code"], "IMPLEMENT")  # nothing downstream is special
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["reason"]["code"]), ("merge-ready", "MERGE"))
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertEqual(p.git("show", "main:src/calc.py"), FIXED)
        merged = [json.loads(l) for l in p.git("show", "main:.rail/journal/1-events.jsonl").splitlines()]
        self.assertEqual(sum(e["event"] == "base_checks" for e in merged), 1)  # the claim didn't run them again

        stats = p.rail("stats")["stats"]
        self.assertEqual(stats["adopted"], 1)
        self.assertIn("Adopted from a branch with no ticket (rail adopt): 1 of 1 merged tickets.",
                      p.rail("stats", raw=True).stdout)
        refused = p.rail("adopt", "proto", draft, expect=3)  # its work is on main now: the checks are green there
        self.assertEqual(refused["reason"]["code"], "ADOPT_CHECKS")

    def test_a_branch_behind_the_base_is_rebased_at_ship(self):
        p = self.fixture()
        prototype(p)
        p.write("api/handlers.py", "def handle():\n    return 204\n")
        p.git("commit", "--quiet", "-am", "move main on")
        adopted = p.rail("adopt", "proto", fill(p.rail("adopt", "proto")["draft"]))
        self.assertEqual(adopted["reason"]["code"], "ADOPTED")
        refused = p.rail("adopt", "proto", expect=2)
        self.assertIn("ticket 1 adopted 'proto' already", refused["reason"]["message"])
        shipped = p.rail("advance", "1")
        self.assertIn(("rebase", "pass"), [(s["step"], s.get("result")) for s in shipped["steps"]])
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertIn("204", p.git("show", "main:api/handlers.py"))

    def test_a_person_adoption_waits_for_the_contract_approval_with_the_work_attached(self):
        p = self.fixture(config='person_paths = ["api/**"]\n' + CONFIG)
        prototype(p, {"src/calc.py": FIXED, "api/handlers.py": "def handle():\n    return 201\n"})
        draft = fill(p.rail("adopt", "proto")["draft"], checks=(CHECK_ADD, "grep -q 201 api/handlers.py"))
        adopted = p.rail("adopt", "proto", draft)
        self.assertEqual((adopted["state"], adopted["owner"], adopted["reason"]["code"], adopted["tier"]),
                         ("new", "human", "APPROVE_CONTRACT", "PERSON"))
        self.assertTrue(adopted["action"]["brief"].startswith("Ticket 1 holds the work of branch proto"))
        self.assertIn("rail accept 1", adopted["action"]["brief"])
        self.assertEqual(p.rail("next")["reason"]["code"], "WAITING_HUMAN")
        self.assertEqual(p.rail("accept", "1")["reason"]["code"], "IMPLEMENT")
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["reason"]["code"]), ("merge-ready", "MERGE_BY_PERSON"))
        self.assertEqual([s["step"] for s in shipped["steps"]][-2:], ["review", "security"])
        p.rail("accept", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")

    def test_with_a_remote_the_adopted_branch_needs_no_push(self):
        a, b = self.remote_pair()
        prototype(a)
        adopted = a.rail("adopt", "proto", fill(a.rail("adopt", "proto")["draft"]), session="a")
        self.assertEqual(adopted["reason"]["code"], "ADOPTED")
        self.assertNotIn("proto", a.git("ls-remote", "origin"))
        self.assertIn("refs/heads/1-make-add-add", a.git("ls-remote", "origin"))
        self.assertEqual(b.rail("status")["tickets"][0]["state"], "implementing")
