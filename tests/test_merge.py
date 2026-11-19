"""Shipping, CI and the merge: what the agent and a person see from ship to the base branch."""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

HERE = os.path.dirname(os.path.abspath(__file__))

# fake_gh.py with three more things GitHub does, each switched on by a key in its state file: an Actions run on a
# head (`workflow_runs`), a merge request that GitHub accepts and lands later (`merge_lands_later`), and a base that
# moves with a conflict between the engine's read and its merge (`conflict_at_merge`).
MORE_GITHUB = f"""\
import sys
sys.path.insert(0, {HERE!r})
import fake_gh

plain = fake_gh.handle


def handle(state, method, path, body):
    if "/actions/runs?" in path:
        return fake_gh.respond(200, {{"total_count": len(state.get("workflow_runs", [])),
                                     "workflow_runs": state.get("workflow_runs", [])}})
    if method == "PUT" and path.endswith("/merge-async"):
        number = int(path.split("/")[-2])
        pr = next(p for p in state["pulls"] if p["number"] == number)
        if state.get("merge_lands_later"):
            state.setdefault("calls", []).append(f"PUT pulls/{{number}}/merge-async")
            return fake_gh.respond(202, {{"status": "pending", "details": {{"message": "Merge request enqueued."}}}})
        if state.get("conflict_at_merge"):
            pr["mergeable_state"] = "dirty"
    return plain(state, method, path, body)


fake_gh.handle = handle
sys.exit(fake_gh.main(sys.argv[1:]))
"""


def more_github(github):
    """The fake gh, wrapped with MORE_GITHUB."""
    script = os.path.join(github.bin, "more_gh.py")
    with open(script, "w") as f:
        f.write(MORE_GITHUB)
    with open(os.path.join(github.bin, "gh"), "w") as f:
        f.write(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    return github


def failed_step(answer):
    """(step, detail) of the one step that failed."""
    failed = [s for s in answer["steps"] if s.get("result") == "fail"]
    assert len(failed) == 1, answer["steps"]
    return failed[0]["step"], failed[0].get("detail")


def journal(fx, nn="1", branch="1-fix-add"):
    return [json.loads(l) for l in fx.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]


def push_to_main(fx, path, text, message="base moves"):
    """Another person's change lands on the base branch."""
    fx.write(path, text)
    fx.git("add", path)
    fx.git("commit", "--quiet", "-m", message)
    fx.git("push", "--quiet", "origin", "main")


def shipped(fx):
    """Ticket 1 claimed, fixed and shipped."""
    fx.add(ticket())
    fx.rail("next")
    fx.fix_calc("1")
    return fx.rail("advance", "1")


def ci_clone(test, fx, ref, branch, config=None):
    """The CI runner's checkout of a pull request's head: `rail ci` there, as the workflow runs it."""
    ci = os.path.join(test.tmp, "ci")
    subprocess.run(["git", "clone", "--quiet", fx.root, ci], check=True)
    subprocess.run(["git", "checkout", "--quiet", "--detach", fx.git("rev-parse", ref).strip()], cwd=ci, check=True)
    if config is not None:
        with open(os.path.join(ci, ".rail", "config.toml"), "w") as f:
            f.write(config)
    result = subprocess.run([os.path.join(ci, ".rail", "bin", "rail"), "ci", "--json"], cwd=ci, capture_output=True,
                            text=True, env=dict(os.environ, RAIL_BRANCH=branch))
    return result.returncode, json.loads(result.stdout)


class Ship(RailTest):
    def test_a_verify_that_fails_on_the_change_and_passes_on_the_base_returns_the_ticket_with_its_output(self):
        p = self.fixture(config=CONFIG.replace("python3 -m py_compile src/calc.py", "python3 -m compileall -q src"))
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/report.py", "def report(:\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["state"], failed["owner"], failed["reason"]["code"]), ("implementing", "agent", "STEP_FAILED"))
        self.assertEqual(failed_step(failed), ("verify", "exit 1"))
        self.assertIn("Ship of ticket 1 failed at 'verify'.", failed["action"]["brief"])
        self.assertIn("src/report.py", failed["action"]["brief"])
        self.assertIn("SyntaxError", failed["action"]["brief"])
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "verify"][-1]
        self.assertEqual((recorded["result"], recorded["detail"]), ("fail", "exit 1"))
        self.assertNotIn("counted", recorded)  # the change's own failure: it spends an attempt
        again = p.rail("next")
        self.assertEqual((again["ticket"], again["reason"]["code"]), ("1", "STEP_FAILED"))  # not RED_BASE
        self.assertIn("failed at 'verify': exit 1", again["action"]["brief"])
        self.assertEqual([t["ticket"] for t in p.rail("status")["tickets"]], ["1"])  # and no fix ticket for the base
        p.write("src/report.py", "def report():\n    return 0\n", base=p.worktree("1"))
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")

    def test_a_verify_that_fails_on_the_base_too_and_prints_nothing_is_still_a_red_base(self):
        # grep -q exits 1 in silence, on the base and on the change: no output must not read as green on the base.
        p = self.fixture(config=CONFIG.replace("python3 -m py_compile src/calc.py", "grep -q total src/calc.py"))
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("verify", "red base"))
        self.assertIn("verify fails on the base branch too", failed["action"]["brief"])
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "verify"][-1]
        self.assertEqual((recorded["result"], recorded["counted"]), ("fail", False))
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "RED_BASE")

    def test_a_check_that_runs_past_timeout_secs_fails_with_timeout(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 2"))
        p.add(ticket(check="sleep 30"))
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("checks", "sleep 30: timeout"))
        self.assertEqual((failed["owner"], failed["reason"]["code"]), ("agent", "STEP_FAILED"))
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "checks"][-1]
        self.assertNotIn("counted", recorded)  # a command that times out at ship counts like any other failure

    def test_a_verify_that_runs_past_timeout_secs_fails_with_timeout_and_is_not_a_red_base(self):
        p = self.fixture(config=CONFIG.replace("timeout_secs = 60", "timeout_secs = 2")
                         .replace("python3 -m py_compile src/calc.py", "sleep 30"))
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed_step(failed), ("verify", "timeout"))
        recorded = [e for e in journal(p) if e["event"] == "step" and e["step"] == "verify"][-1]
        self.assertNotIn("counted", recorded)
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "STEP_FAILED")


class Conflicts(RailTest):
    def test_a_pull_request_that_conflicts_with_its_base_returns_the_ticket_to_the_agent(self):
        a, b, github = self.github_pair()
        shipped(a)
        github.ci("1-fix-add", "success")
        push_to_main(b, "src/calc.py", "def add(a, b):\n    return sum((a, b))\n")
        back = a.rail("next")
        self.assertEqual((back["ticket"], back["state"], back["owner"], back["reason"]["code"]),
                         ("1", "implementing", "agent", "CONFLICT"))
        self.assertIn("conflicts with the base branch. Run: rail advance 1", back["action"]["brief"])
        self.assertEqual(a.rail("status")["tickets"][0]["state"], "implementing")
        failed = a.rail("advance", "1", expect=3)
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["result"]), ("rebase", "fail"))
        self.assertIn("src/calc.py", failed["steps"][0]["detail"])
        self.assertEqual((failed["state"], failed["owner"]), ("implementing", "agent"))

    def test_a_pull_request_behind_its_base_that_conflicts_on_the_rebase_goes_back_to_the_agent(self):
        # GitHub said behind, and the engine's own rebase meets a conflict: the agent rebases by hand.
        a, b, github = self.github_pair()
        github.update(lambda s: s.__setitem__("require_up_to_date", True))
        shipped(a)
        push_to_main(b, "src/calc.py", "def add(a, b):\n    return sum((a, b))\n")
        github.update(lambda s: s["pulls"][0].__setitem__("mergeable_state", "behind"))
        back = a.rail("next", "--ticket", "1", expect=3)
        self.assertEqual((back["state"], back["owner"], back["reason"]["code"]), ("implementing", "agent", "STEP_FAILED"))
        self.assertIn({"step": "rebase", "status": "ran", "result": "fail",
                       "detail": "conflict while bringing the PR up to date"}, back["steps"])
        self.assertIn("rail advance 1", back["action"]["brief"])
        self.assertEqual(a.git("status", "--porcelain", cwd=a.worktree("1")), "")  # the rebase was undone
        github.update(lambda s: s["pulls"][0].pop("mergeable_state"))
        failed = a.rail("advance", "1", expect=3)
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["result"]), ("rebase", "fail"))
        self.assertIn("src/calc.py", failed["steps"][0]["detail"])


class RemoteMerge(RailTest):
    def test_a_merge_github_has_not_landed_yet_is_requested_and_after_the_wait_goes_to_a_person(self):
        a, b, github = self.github_pair()
        more_github(github)
        github.update(lambda s: s.__setitem__("merge_lands_later", True))
        shipped(a)
        github.ci("1-fix-add", "success")
        requested = a.rail("advance", "1")
        self.assertEqual((requested["state"], requested["owner"], requested["reason"]["code"]),
                         ("merge-ready", "none", "MERGE_REQUESTED"))
        self.assertIn({"step": "merge", "status": "ran", "result": "pass", "detail": "requested for #1"},
                      requested["steps"])
        self.assertIn("rail next sees it on the base branch once GitHub lands it", requested["action"]["brief"])
        self.assertEqual(a.rail("status")["tickets"][0]["state"], "merge-ready")
        self.assertEqual(a.rail("next", "--ticket", "1")["reason"]["code"], "MERGE_REQUESTED")  # nobody's to act on yet

        # Ten minutes pass and the merge hasn't landed.
        note = os.path.join(a.root, ".git", "rail", "cache", "merge", "1")
        with open(note) as f:
            sha = f.read().split()[0]
        with open(note, "w") as f:
            f.write(f"{sha} {int(time.time()) - 700}")
        self.assertEqual(a.rail("status")["tickets"][0]["note"], "waiting: merge failed")
        waiting = a.rail("next", "--ticket", "1")
        self.assertEqual((waiting["owner"], waiting["reason"]["code"], waiting["action"]["kind"]),
                         ("human", "MERGE_FAILED", "human_wait"))
        self.assertIn("was requested and hasn't landed", waiting["action"]["brief"])
        self.assertIn("rail accept 1", waiting["action"]["brief"])
        self.assertIn("rail:needs-you", github.pr(1)["labels"])

        github.update(lambda s: s.pop("merge_lands_later"))
        github.person_merges(1)  # the person lands it
        self.assertEqual(a.rail("status")["tickets"][0]["state"], "merged")

    def test_a_merge_that_never_lands_keeps_its_own_reason_once_the_wait_is_labelled(self):
        # The engine labels every wait rail:needs-you; the label must not turn the failed merge into a person's hold.
        a, b, github = self.github_pair()
        more_github(github)
        github.update(lambda s: s.__setitem__("merge_lands_later", True))
        shipped(a)
        github.ci("1-fix-add", "success")
        self.assertEqual(a.rail("advance", "1")["reason"]["code"], "MERGE_REQUESTED")
        note = os.path.join(a.root, ".git", "rail", "cache", "merge", "1")
        with open(note) as f:
            sha = f.read().split()[0]
        with open(note, "w") as f:
            f.write(f"{sha} {int(time.time()) - 700}")  # ten minutes pass and the merge hasn't landed
        a.rail("next")
        self.assertIn("rail:needs-you", github.pr(1)["labels"])
        waiting = a.rail("next")
        self.assertEqual((waiting["owner"], [w["needs"] for w in waiting["waits"]]), ("human", ["MERGE_FAILED"]))
        self.assertIn("was requested and hasn't landed", waiting["waits"][0]["brief"])
        self.assertNotIn("holds ticket 1", waiting["waits"][0]["brief"])
        self.assertEqual(a.rail("status")["tickets"][0]["note"], "waiting: merge failed")

    def test_a_merge_refused_for_a_conflict_that_came_meanwhile_sends_the_ticket_back_to_the_agent(self):
        a, b, github = self.github_pair()
        more_github(github)
        shipped(a)
        github.ci("1-fix-add", "success")
        github.update(lambda s: s.__setitem__("conflict_at_merge", True))  # the base moves as the merge is asked
        back = a.rail("advance", "1", expect=3)
        self.assertEqual((back["state"], back["owner"], back["reason"]["code"]), ("implementing", "agent", "CONFLICT"))
        self.assertEqual((back["steps"][-1]["step"], back["steps"][-1]["result"]), ("merge", "fail"))
        self.assertIn("not mergeable", back["steps"][-1]["detail"])
        self.assertFalse(github.pr(1)["merged"])

    def test_while_ci_runs_next_hands_back_the_run_to_watch(self):
        a, b, github = self.github_pair()
        more_github(github)
        shipped(a)
        github.update(lambda s: s.__setitem__("workflow_runs", [{"id": 4242, "status": "in_progress"}]))
        watch = a.rail("next")
        self.assertEqual((watch["ticket"], watch["state"], watch["owner"], watch["reason"]["code"]),
                         ("1", "in-ci", "agent", "CI_WAIT"))
        self.assertEqual(watch["action"], {"kind": "script", "brief": "gh run watch 4242 --interval 30 --exit-status; rail next",
                                           "command": "gh run watch 4242 --interval 30 --exit-status; rail next"})
        github.update(lambda s: s.__setitem__("workflow_runs", []))  # no Actions run yet: nothing to watch
        resting = a.rail("next")
        self.assertEqual((resting["owner"], resting["reason"]["code"], resting["action"]["kind"]),
                         ("none", "CI_WAIT", "rest"))


class LocalMerge(RailTest):
    def test_a_merge_git_refuses_waits_for_a_person_and_leaves_main_alone(self):
        p = self.fixture()
        shipped(p)
        before = p.git("rev-parse", "main")
        p.write("src/calc.py", "def add(a, b):\n    return a - b  # my own edit\n")  # uncommitted, in the main checkout
        refused = p.rail("advance", "1", expect=3)
        self.assertEqual((refused["state"], refused["owner"], refused["reason"]["code"]),
                         ("merge-ready", "human", "MERGE_FAILED"))
        self.assertEqual(refused["action"]["kind"], "human_wait")
        self.assertEqual(failed_step(refused)[0], "merge")
        self.assertIn("src/calc.py", refused["action"]["brief"])
        self.assertEqual(p.git("rev-parse", "main"), before)
        with open(p.path("src", "calc.py")) as f:
            self.assertIn("my own edit", f.read())
        p.git("checkout", "--", "src/calc.py")  # the person puts their edit away
        self.assertEqual(p.rail("advance", "1")["state"], "merged")


class RailCI(RailTest):
    def test_ci_fails_a_pull_request_with_no_ticket_whose_verify_fails(self):
        p = self.fixture()
        p.git("checkout", "--quiet", "-b", "bump-deps")
        p.write("src/calc.py", "def add(a, b:\n")
        p.git("commit", "--quiet", "-am", "Bump everything")
        code, result = ci_clone(self, p, "bump-deps", "bump-deps")
        self.assertEqual(code, 3, result)
        self.assertEqual(result["reason"]["code"], "CI_NO_TICKET")
        self.assertEqual(failed_step(result), ("verify", "exit 1"))
        self.assertIn("No ticket on branch bump-deps", result["action"]["brief"])

    def test_ci_fails_a_change_that_needs_a_higher_tier_than_it_shipped_as(self):
        # The ticket shipped AUTO; on the pull request's head the project's config makes its change a person's.
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/report.sql", "select 1;\n", base=p.worktree("1"))
        self.assertEqual(p.rail("advance", "1")["tier"], "AUTO")
        code, result = ci_clone(self, p, "1-fix-add", "1-fix-add", config='person_paths = ["**/*.sql"]\n' + CONFIG)
        self.assertEqual(code, 3, result)
        self.assertEqual(result["reason"]["code"], "CI_FAIL")
        self.assertEqual(failed_step(result), ("tier", "the change needs PERSON, and it shipped as AUTO"))


class Choosing(RailTest):
    """Which ticket a verb acts on when the command names none."""

    def test_advance_with_no_ticket_takes_this_sessions_one_ticket(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next", session="a")
        p.fix_calc("1")
        self.assertEqual(p.rail("advance", session="a")["ticket"], "1")  # from the project's root, on main
        p.rail("next", "--ticket", "2", session="a")
        p.rail("next", "--ticket", "1", session="a")
        failed = p.rail("advance", session="a", expect=2)
        self.assertIn("which ticket?", failed["reason"]["message"])

    def test_rail_ticket_and_an_external_id_name_the_ticket(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        picked = p.rail("next", env_extra={"RAIL_TICKET": "2"})
        self.assertEqual((picked["ticket"], picked["reason"]["code"]), ("2", "IMPLEMENT"))
        brief = os.path.join(self.tmp, "brief.txt")
        with open(brief, "w") as f:
            f.write("Customers see negative totals.\n")
        self.assertEqual(p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix totals", "--brief", brief)["created"],
                         ["3"])
        self.assertEqual(p.rail("next", "--ticket", "PROJ-7")["ticket"], "3")
        self.assertEqual(p.rail("drop", "PROJ-7")["state"], "dropped")
        self.assertEqual([(t["ticket"], t["state"]) for t in p.rail("status")["tickets"]],
                         [("1", "accepted"), ("2", "implementing"), ("3", "dropped")])


class SecondMachine(RailTest):
    def test_a_ticket_branch_behind_its_remote_is_fast_forwarded_when_the_ticket_comes_back(self):
        # The laptop's session hands the ticket to a cloud run, which saves its work; the laptop takes it back.
        a, b = self.remote_pair()
        a.add(ticket())
        a.rail("next", session="laptop")
        b.rail("next", "--ticket", "1", session="cloud")
        b.write("src/calc.py", "def add(a, b):\n    return a + b  # from the cloud\n", base=b.worktree("1"))
        b.rail("save", "1", session="cloud")
        back = a.rail("next", "--ticket", "1", session="laptop")
        self.assertEqual((back["ticket"], back["reason"]["code"]), ("1", "IMPLEMENT"))
        with open(os.path.join(a.worktree("1"), "src", "calc.py")) as f:
            self.assertIn("from the cloud", f.read())
        self.assertEqual(a.git("rev-parse", "1-fix-add"), a.git("rev-parse", "origin/1-fix-add"))
        self.assertEqual(a.rail("advance", "1", session="laptop")["state"], "in-ci")

    def test_work_saved_after_its_pull_request_was_merged_early_starts_again_on_the_base(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        a.rail("next")
        github.person_merges(1)  # "Not shipped yet" was merged by hand
        a.fix_calc("1")
        a.rail("save", "1")  # the work goes on after the merge
        on = a.rail("next")
        self.assertEqual((on["ticket"], on["reason"]["code"]), ("1", "IMPLEMENT"))
        self.assertIn({"step": "rebase", "status": "ran", "result": "pass",
                       "detail": "onto main: its pull request was merged before the work shipped"}, on["steps"])
        a.git("fetch", "--quiet")
        self.assertEqual(a.git("merge-base", "--is-ancestor", "origin/main", "1-fix-add"), "")
        with open(os.path.join(a.worktree("1"), "src", "calc.py")) as f:
            self.assertEqual(f.read(), "def add(a, b):\n    return a + b\n")
        self.assertEqual(github.pr(2)["state"], "open")
        self.assertEqual(a.rail("advance", "1")["state"], "in-ci")
