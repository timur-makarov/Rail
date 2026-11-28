"""A revert is a ticket: the label rail:revert on a merged pull request files one whose change is the reverse of
the reverted ticket's, and ship checks exactly that."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

CLEAN = {"summary": "Clean.", "findings": []}


def step(answer, name):
    return [s for s in answer["steps"] if s["step"] == name][-1]


def merge(p, nn, github=None):
    """Ship a ticket whose work is in its worktree, and merge it."""
    p.queue_reviews(CLEAN)
    answer = p.rail("advance", nn)
    for _ in range(4):
        if answer["state"] == "merged":
            return answer
        if github and answer["reason"]["code"] == "CI_WAIT":
            green(github, p, nn)
        answer = p.rail("advance", nn, expect=None) if not github else p.rail("next", "--ticket", nn, expect=None)
    raise AssertionError(answer)


def green(github, p, nn):
    branch = next(pr["head"] for pr in github.read()["pulls"] if pr["head"].startswith(f"{nn}-"))
    sha = github.head(branch)
    github.update(lambda s: s["checks"].__setitem__(sha, [{"name": "rail", "status": "completed", "conclusion": "success"}]))


class ByHand(RailTest):
    """With no remote, a revert ticket is filed like any ticket: kind and reverts in the front matter."""

    def merged(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        self.assertEqual(merge(p, "1")["state"], "merged")
        return p

    def revert(self, reverts="1", scope=("src/**",), body=""):
        scope_list = ", ".join(f'"{s}"' for s in scope)
        return (f'+++\ntitle = "Revert ticket {reverts}"\ntier = "AUTO"\nkind = "revert"\nreverts = "{reverts}"\n'
                f'caused_by = "{reverts}"\nscope_paths = [{scope_list}]\n+++\n\n## Why\nIt broke the totals.\n\n'
                f"## Done Contract\nThe change is the reverse of ticket {reverts}'s.\n{body}")

    def test_the_engine_reverses_the_change_and_the_squash_names_what_it_reverts(self):
        p = self.merged()
        sha = p.git("rev-parse", "main").strip()
        added = p.add(self.revert())
        self.assertEqual((added["ticket"], added["state"]), ("2", "accepted"))  # no Check: line, and lint passes
        claimed = p.rail("next")
        # The reverse is in the worktree already: all that is left is the ship.
        self.assertEqual((claimed["reason"]["code"], claimed["action"]["kind"], claimed["action"].get("command")),
                         ("REVERT_SHIP", "script", "rail advance 2"))
        with open(os.path.join(p.worktree("2"), "src", "calc.py")) as f:
            self.assertEqual(f.read(), "def add(a, b):\n    return a - b\n")
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "2")
        self.assertEqual(step(shipped, "checks"), {"step": "checks", "status": "ran", "result": "pass",
                                                   "detail": f"the reverse of ticket 1's change ({sha[:12]})"})
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        message = p.git("log", "-1", "--format=%B", "main")
        self.assertIn(f"\nReverts: {sha}\n", message)
        self.assertIn("| check: the reverse of ticket 1's change", message)
        self.assertEqual(p.git("show", "main:src/calc.py"), "def add(a, b):\n    return a - b\n")
        self.assertIn('title = "Fix add"', p.git("show", "main:.rail/tickets/1.md"))  # ticket 1's file and journal stay
        self.assertTrue(p.git("show", "main:.rail/journal/1-events.jsonl"))
        stats = p.rail("stats")["stats"]
        self.assertEqual(stats["outcomes"]["tiers"]["AUTO"]["reverted"], 1)

    def test_a_change_that_is_not_the_reverse_fails_while_the_reverse_still_applies(self):
        p = self.merged()
        p.add(self.revert())
        p.rail("next")
        p.write("src/calc.py", "def add(a, b):\n    return a * b\n", base=p.worktree("2"))
        asked = p.rail("next", "--ticket", "2")
        self.assertEqual(asked["reason"]["code"], "REVERT")
        self.assertIn("The reverse of that change still applies as it is, and the worktree holds something else.",
                      asked["action"]["brief"])
        failed = p.rail("advance", "2", expect=3)
        self.assertEqual(step(failed, "checks")["result"], "fail")
        self.assertIn("not the reverse of ticket 1's change", step(failed, "checks")["detail"])
        self.assertIn("Put the exact reverse in its place and ship that:", failed["action"]["brief"])

    def test_a_revert_made_by_hand_passes_once_the_reverse_no_longer_applies(self):
        p = self.merged()
        # A later ticket changes the same line, so the reverse of ticket 1 can't be applied as it is.
        p.add(ticket(title="Add floats", check="grep -q float src/calc.py"))
        p.rail("next")
        p.write("src/calc.py", "def add(a, b):\n    return float(a) + float(b)\n", base=p.worktree("2"))
        self.assertEqual(merge(p, "2")["state"], "merged")
        p.add(self.revert())
        asked = p.rail("next")
        self.assertEqual((asked["ticket"], asked["reason"]["code"], asked["action"]["kind"]), ("3", "REVERT", "agent_task"))
        brief = asked["action"]["brief"]
        self.assertIn("Ticket 3 reverts ticket 1: take its change (commit ", brief)
        self.assertIn("no longer applies, because later tickets changed the same lines. Undo by hand what ticket 1"
                      " changed, and keep the later work", brief)
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("3")).strip(), "")  # nothing half applied
        p.write("src/calc.py", "def add(a, b):\n    return float(a) - float(b)\n", base=p.worktree("3"))
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "3")
        self.assertIn("undone by hand: the reverse of ticket 1's change", step(shipped, "checks")["detail"])
        self.assertEqual(step(shipped, "checks")["result"], "pass")
        self.assertEqual(step(shipped, "review")["result"], "pass")  # the reviewer reads it like any change

    def test_a_revert_made_by_hand_passes_once_verify_failed_on_the_exact_reverse(self):
        verify = ("'''python3 -c \"import sys; sys.path.insert(0, 'src'); import use, more; use.total();"
                  " more.twice(1)\"'''")
        p = self.fixture(config=CONFIG.replace('verify = "python3 -m py_compile src/calc.py"', "verify = " + verify),
                         files={"src/use.py": "import calc\n\n\ndef total():\n    return calc.add(1, 2)\n",
                                "src/more.py": "def twice(a):\n    return a + a\n"})
        # Ticket 1 renames add to plus. Ticket 2 calls plus from a file ticket 1 never touched, so the reverse of
        # ticket 1 still applies, and the project no longer runs with it.
        p.add(ticket(title="Rename add", check="grep -q plus src/calc.py"))
        p.rail("next")
        p.write("src/calc.py", "def plus(a, b):\n    return a + b\n", base=p.worktree("1"))
        p.write("src/use.py", "import calc\n\n\ndef total():\n    return calc.plus(1, 2)\n", base=p.worktree("1"))
        self.assertEqual(merge(p, "1")["state"], "merged")
        p.add(ticket(title="Count twice", check="grep -q calc src/more.py"))
        p.rail("next")
        p.write("src/more.py", "import calc\n\n\ndef twice(a):\n    return calc.plus(a, a)\n", base=p.worktree("2"))
        self.assertEqual(merge(p, "2")["state"], "merged")

        p.add(self.revert())
        self.assertEqual(p.rail("next")["reason"]["code"], "REVERT_SHIP")
        failed = p.rail("advance", "3", expect=3)
        self.assertEqual(step(failed, "verify")["result"], "fail")  # twice still calls plus
        asked = p.rail("next", "--ticket", "3")
        self.assertEqual(asked["reason"]["code"], "STEP_FAILED")
        # The exact reverse failed verify, so a revert adapted by hand is accepted, and the brief says so.
        p.write("src/more.py", "import calc\n\n\ndef twice(a):\n    return calc.add(a, a)\n", base=p.worktree("3"))
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "3")
        self.assertIn("undone by hand: verify failed on the exact reverse of ticket 1's change", step(shipped, "checks")["detail"])
        self.assertEqual(p.rail("advance", "3")["state"], "merged")


FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_reviewer.py")


class Lint(RailTest):
    def test_kind_and_reverts_go_together(self):
        p = self.fixture()
        base = ticket()
        for front, said in (
            (('kind = "undo"',), "kind must be one of revert, or left out"),
            (('kind = "revert"',), 'a revert ticket needs reverts = "NN", the id of the merged ticket it takes out'),
            (('reverts = "1"',), "'reverts' belongs to a ticket with kind = \"revert\""),
        ):
            failed = p.add(ticket(front=front), expect=None)
            self.assertEqual(failed["reason"]["code"], "TICKET_LINT")
            self.assertIn(said, failed["action"]["brief"])
        self.assertNotIn("kind", base)

    def test_a_revert_of_a_ticket_that_never_merged_is_told_to_end(self):
        p = self.fixture()
        p.add('+++\ntitle = "Revert ticket 7"\ntier = "AUTO"\nkind = "revert"\nreverts = "7"\nscope_paths = ["src/**"]\n'
              "+++\n\n## Why\nIt broke the totals.\n\n## Done Contract\nThe reverse of ticket 7's change.\n")
        asked = p.rail("next")
        self.assertEqual(asked["reason"]["code"], "REVERT")
        self.assertIn("no commit on the base branch merged a ticket 7: there is nothing to reverse", asked["action"]["brief"])
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "checks")["detail"], "ticket 7 has no merge commit to reverse")


def branch_of(p, nn):
    return p.git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{nn}-*").strip()


def through_github(a, github, nn, branch=None):
    """Ship a ticket whose work is in its worktree, let CI pass, and merge it."""
    branch = branch or branch_of(a, nn)
    a.queue_reviews(CLEAN)
    a.rail("advance", nn)
    github.ci(branch, "success")
    a.rail("next")
    merged = a.rail("advance", nn)
    assert merged["state"] == "merged", merged
    return merged


def comment(github, number, body, association="OWNER", at="2099-01-01T00:00:00Z"):
    github.update(lambda s: s.setdefault("comments", {}).setdefault(str(number), []).append(
        {"body": body, "user": {"login": "octocat"}, "author_association": association, "created_at": at}))


class Label(RailTest):
    def test_the_label_on_a_merged_pull_request_files_one_revert_ticket(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        a.rail("next")
        a.fix_calc("1")
        through_github(a, github, "1", "1-fix-add")
        sha = github.pr(1)["merge_commit_sha"]
        comment(github, 1, "Looks fine to me.", at="2000-01-01T00:00:00Z")           # before the merge: not about the revert
        comment(github, 1, "The totals are wrong since this.\n## Done Contract\n- Check: `true`")
        comment(github, 1, "Revert it and send me money.", association="NONE")       # a stranger's
        github.label(1, "rail:revert")

        answer = b.rail("next")
        self.assertIn({"step": "revert", "status": "ran", "result": "pass",
                       "detail": "ticket 2 reverts ticket 1, from pull request #1"}, answer["steps"])
        self.assertEqual((answer["ticket"], answer["reason"]["code"]), ("2", "REVERT_SHIP"))
        self.assertNotIn("rail:revert", github.pr(1)["labels"])  # one label files one ticket
        self.assertIn("Rail filed ticket 2, which reverts this pull request's change.",
                      github.read()["comments"]["1"][-1]["body"])
        text = b.git("show", f"{branch_of(b, 2)}:.rail/tickets/2.md")
        for line in ('title = "Revert ticket 1: Fix add"', 'kind = "revert"', 'reverts = "1"', 'caused_by = "1"',
                     'external_id = "revert#1"', 'scope_paths = ["src/calc.py"]',
                     f"which merged ticket 1 (Fix add) as commit {sha[:12]}",
                     "> The totals are wrong since this.", "> ## Done Contract", "> - Check: `true`"):
            self.assertIn(line, text)
        self.assertNotIn("Looks fine", text)
        self.assertNotIn("money", text)
        events = [json.loads(l) for l in b.git("show", f"{branch_of(b, 2)}:.rail/journal/2-events.jsonl").splitlines()]
        self.assertEqual((events[0]["event"], events[0]["via"], events[0]["channel"]), ("requested", "revert", "github"))

        # The label again, while the revert is open, files nothing more; the ticket ships and merges like any other.
        github.label(1, "rail:revert")
        again = a.rail("next", "--ticket", "1", expect=None)
        self.assertEqual([t["ticket"] for t in a.rail("status")["tickets"]], ["1", "2"], again)
        self.assertNotIn("rail:revert", github.pr(1)["labels"])
        through_github(b, github, "2")
        self.assertIn(f"Reverts: {sha}", github.pr(2)["body"])
        self.assertEqual(a.rail("stats")["stats"]["outcomes"]["tiers"]["AUTO"]["reverted"], 1)

    def test_a_revert_on_a_kinds_paths_is_a_person_ticket_the_label_already_approved(self):
        a, b, github = self.github_pair(config=CONFIG + '\n[kinds]\naccess = ["api/**"]\n')
        a.add(ticket(title="Open the API", tier="PERSON", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        a.rail("accept", "1")
        a.rail("next")
        a.write("api/handlers.py", "def handle():\n    return 201\n", base=a.worktree("1"))
        a.queue_reviews(CLEAN, CLEAN)
        a.rail("advance", "1")
        github.ci("1-open-the-api", "success")
        a.rail("next")
        github.person_merges(1)
        self.assertEqual(a.rail("next", "--ticket", "1", expect=None)["state"], "merged")
        github.label(1, "rail:revert")
        answer = a.rail("next")
        self.assertEqual((answer["ticket"], answer["tier"], answer["reason"]["code"]), ("2", "PERSON", "REVERT_SHIP"))
        events = [json.loads(l) for l in a.git("show", f"{branch_of(a, 2)}:.rail/journal/2-events.jsonl").splitlines()]
        accepted = next(e for e in events if e["event"] == "accepted")
        self.assertEqual((accepted["by"], accepted["via"], accepted["tier"]), ("person", "label", "PERSON"))

    def test_a_revert_goes_on_under_a_brake_and_nothing_else_does(self):
        from test_stop import brake
        a, b, github = self.github_pair()
        a.add(ticket())
        a.add(ticket(title="Other", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        a.rail("next")
        a.fix_calc("1")
        through_github(a, github, "1", "1-fix-add")
        brake(github)
        github.label(1, "rail:revert")
        answer = a.rail("next")
        self.assertEqual((answer["ticket"], answer["reason"]["code"]), ("3", "REVERT_SHIP"))
        self.assertEqual(a.rail("next", "--ticket", "2")["reason"]["code"], "STOPPED")
        through_github(a, github, "3")
        self.assertEqual(a.rail("next")["reason"]["code"], "STOPPED")  # the revert is in: the brake still holds the rest

    def test_the_label_on_a_pull_request_that_merged_no_ticket_files_nothing_and_says_so(self):
        a, b, github = self.github_pair()
        github.update(lambda s: s["pulls"].append({
            "number": 9, "title": "Bump a dependency", "body": "", "head": "dependabot/x", "base": "main",
            "state": "closed", "merged": True, "merged_at": "2026-11-20T10:00:00Z", "merge_commit_sha": "0" * 40,
            "labels": ["rail:revert"]}))
        answer = a.rail("next")
        self.assertIn({"step": "revert", "status": "not_run",
                       "detail": "pull request #9 merged no ticket's change: nothing to reverse"}, answer["steps"])
        self.assertEqual(github.pr(9)["labels"], [])
        self.assertIn("Rail filed no revert", github.read()["comments"]["9"][-1]["body"])
        self.assertEqual(a.rail("status")["tickets"], [])


def smoke_issue(github, number, sha, at="2026-11-11T10:00:00Z"):
    """What the project's CD opens when the smoke check fails after a deploy to dev."""
    github.update(lambda s: s["issues"].append({
        "number": number, "title": "Smoke check failed on dev", "body": f"Commit: {sha}\n\nGET /health returned 500.",
        "labels": ["rail"], "state": "open", "created_at": at, "author_association": "NONE"}))


def events_of(p, nn):
    return [json.loads(row) for row in p.git("show", f"{branch_of(p, nn)}:.rail/journal/{nn}-events.jsonl").splitlines()]


def stops(github):
    return [i for i in github.read()["issues"] if "rail:stop" in i["labels"]]


class Smoke(RailTest):
    """A failed dev deploy reverts first: the change comes out, a brake holds its paths, and the fix comes after."""

    def failed_deploy(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        a.add(ticket(title="Other", check="grep -q def src/calc.py"))  # the same scope: the brake will hold it
        a.rail("next")
        a.fix_calc("1")
        through_github(a, github, "1", "1-fix-add")
        sha = github.pr(1)["merge_commit_sha"]
        smoke_issue(github, 30, sha)
        return a, github, sha

    def test_the_change_comes_out_first_and_the_fix_comes_after_it(self):
        a, github, sha = self.failed_deploy()
        answer = a.rail("next", "--ticket", "3")
        self.assertEqual([s["detail"] for s in answer["steps"] if s["step"] == "intake"],
                         ["ticket 3 from github#30", "ticket 4 from github#30"])
        self.assertEqual(answer["reason"]["code"], "REVERT_SHIP")
        revert = a.git("show", f"{branch_of(a, 3)}:.rail/tickets/3.md")
        for line in ('title = "Revert ticket 1: Fix add"', 'kind = "revert"', 'reverts = "1"', 'external_id = "smoke#30"',
                     'scope_paths = ["src/calc.py"]',
                     f"The dev smoke check failed on a deploy of commit {sha[:12]}, which merged ticket 1 (Fix add):"
                     " issue #30. This ticket takes that change out again, so that dev works while the fix is made."):
            self.assertIn(line, revert)
        fix = a.git("show", f"{branch_of(a, 4)}:.rail/tickets/4.md")
        for line in ('after = ["3"]', 'external_id = "github#30"', 'caused_by = "1"', "> GET /health returned 500.",
                     "Ticket 3 takes that change out first. This ticket does ticket 1's work again, so that the smoke"
                     " check passes."):
            self.assertIn(line, fix)
        asked = events_of(a, 3)[0]
        self.assertEqual((asked["via"], asked["opened"], asked.get("smoke")), ("intake", "2026-11-11T10:00:00Z", None))
        asked = events_of(a, 4)[0]
        self.assertEqual((asked["opened"], asked["smoke"]), ("2026-11-11T10:00:00Z", True))

        # The engine's own brake: what ticket 1's scope holds waits; the revert goes on under it; the fix waits its turn.
        brake = stops(github)
        self.assertEqual([(i["state"], i["title"]) for i in brake], [
            ("open", "Rail stopped work on what ticket 1 changed: its deploy to dev failed (#30)")])
        self.assertIn("\n\npaths: src/**\n\n<!-- rail-smoke: 30 -->", brake[0]["body"])
        self.assertEqual(a.rail("next", "--ticket", "2")["reason"]["code"], "STOPPED")
        a.rail("next")
        self.assertEqual(len(a.rail("status")["tickets"]), 4)   # taken in once
        self.assertEqual(len(stops(github)), 1)                 # and one brake

        through_github(a, github, "3")
        body = next(p for p in github.read()["pulls"] if p["head"].startswith("3-"))["body"]
        self.assertIn("Part of #30", body)   # the fix closes the issue, not the revert
        self.assertNotIn("Closes #30", body)
        self.assertIn(f"Reverts: {sha}", body)
        after = a.rail("next", "--ticket", "2")
        self.assertEqual(stops(github)[0]["state"], "closed")  # the revert is in: the brake lifts by itself
        self.assertNotEqual(after["reason"]["code"], "STOPPED")
        broken = a.rail("stats")["stats"]["dev_broken"]
        self.assertEqual(broken["reverts"], 1)
        self.assertGreater(broken["median_minutes"], 0)
        self.assertIn("Failed dev deploys reverted: 1, a median of", a.rail("stats", raw=True).stdout)

    def test_a_fix_that_fails_on_dev_too_is_reverted_and_no_further_fix_is_filed(self):
        a, github, sha = self.failed_deploy()
        a.rail("next", "--ticket", "3")
        through_github(a, github, "3")
        written = os.path.join(self.tmp, "4.md")
        with open(written, "w") as f:
            f.write(ticket(title="Fix add again", front=('external_id = "github#30"', 'caused_by = "1"', 'after = ["3"]'),
                           body="\n## Request\nGET /health returned 500.\n"))
        a.rail("amend", "4", "--file", written)
        self.assertEqual(a.rail("next", "--ticket", "4")["state"], "implementing")
        a.fix_calc("4")
        through_github(a, github, "4")
        again = next(p for p in github.read()["pulls"] if p["head"].startswith("4-"))["merge_commit_sha"]
        smoke_issue(github, 31, again)

        a.rail("next", "--ticket", "5")
        tickets = {t["ticket"]: t for t in a.rail("status")["tickets"]}
        self.assertEqual(sorted(tickets), ["1", "2", "3", "4", "5"])  # the revert of the fix, and no ticket 6
        self.assertIn('reverts = "4"', a.git("show", f"{branch_of(a, 5)}:.rail/tickets/5.md"))
        issue = next(i for i in github.read()["issues"] if i["number"] == 31)
        self.assertEqual(sorted(issue["labels"]), ["rail:needs-you"])
        said = github.read()["comments"]["31"][-1]["body"]
        self.assertIn("Ticket 5 reverts the change. Rail files no fix for this one: ticket 4 was itself the fix after a"
                      " failed deploy, so the same work failed on dev twice. A person decides what comes next. Label this"
                      " issue `rail` again to have an agent try once more.", said)
        # A person's label asks for one more try: the fix is filed, after the revert.
        github.update(lambda s: next(i for i in s["issues"] if i["number"] == 31)["labels"].append("rail"))
        a.rail("next", "--ticket", "5")
        self.assertIn('after = ["5"]', a.git("show", f"{branch_of(a, 6)}:.rail/tickets/6.md"))

    def test_a_failed_deploy_of_a_revert_is_left_to_a_person(self):
        a, github, sha = self.failed_deploy()
        a.rail("next", "--ticket", "3")
        through_github(a, github, "3")
        reverted = next(p for p in github.read()["pulls"] if p["head"].startswith("3-"))["merge_commit_sha"]
        smoke_issue(github, 31, reverted)
        a.rail("next", "--ticket", "4")
        self.assertEqual(len(a.rail("status")["tickets"]), 4)  # no revert of the revert, and no fix
        self.assertIn("Rail files no fix for this one: ticket 3 is a revert, and reversing it would put back the change"
                      " it took out.", github.read()["comments"]["31"][-1]["body"])
        self.assertEqual(len(stops(github)), 1)  # the first failure's brake, closed; none for this one
