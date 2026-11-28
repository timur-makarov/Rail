"""A person's brake: an open issue labelled rail:stop stops Rail in the repository, or on the paths it names."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, FAKE_WORKER, RailTest, ticket

WORKER = CONFIG + f'\n[worker]\ncommand = "python3 {FAKE_WORKER}"\n'


def brake(github, number=40, title="Stop: the deploy is broken", body="", state="open"):
    github.update(lambda s: s["issues"].append({
        "number": number, "title": title, "body": body, "labels": ["rail:stop"], "state": state,
        "html_url": f"https://github.com/acme/app/issues/{number}", "user": {"login": "octocat"},
        "author_association": "OWNER"}))


def lift(github, number=40, how="close"):
    def change(state):
        issue = next(i for i in state["issues"] if i["number"] == number)
        if how == "close":
            issue["state"] = "closed"
        else:
            issue["labels"].remove("rail:stop")
    github.update(change)


class Stop(RailTest):
    def test_an_open_stop_issue_stops_next_advance_and_work_until_it_is_closed(self):
        a, b, github = self.github_pair(config=WORKER)
        a.add(ticket())
        a.add(ticket(title="Other", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        self.assertEqual(a.rail("next")["ticket"], "1")
        a.fix_calc("1")
        calls = len(github.read().get("calls", []))
        brake(github)

        stopped = a.rail("next")
        self.assertEqual((stopped["reason"]["code"], stopped["owner"], stopped["action"]["kind"], stopped["ticket"]),
                         ("STOPPED", "person", "person_wait", None))
        self.assertEqual(stopped["action"]["brief"], (
            "A person stopped Rail: issue #40 (Stop: the deploy is broken) is open with the label rail:stop. Nothing"
            " is done on any ticket until that issue is closed or loses the label; a run that then starts goes on by"
            " itself. Do no work on it meanwhile. https://github.com/acme/app/issues/40"))
        # Asked for by number, a ticket answers the same, and nothing is claimed: ticket 2 stays where it was.
        asked = a.rail("next", "--ticket", "2")
        self.assertEqual((asked["reason"]["code"], asked["ticket"], asked["state"]), ("STOPPED", "2", "accepted"))
        self.assertIn("Nothing is done on ticket 2 until", asked["action"]["brief"])
        self.assertFalse(os.path.exists(a.worktree("2")))
        # A runner that loops on one ticket stops at its next call: nothing ships and no worker starts.
        before = a.git("rev-parse", "1-fix-add")
        for verb in ("advance", "work"):
            answer = a.rail(verb, "1", expect=None)
            self.assertEqual((answer["reason"]["code"], answer["owner"]), ("STOPPED", "person"), answer)
        self.assertEqual(a.git("rev-parse", "1-fix-add"), before)
        self.assertEqual(a.work_log(), [])
        self.assertEqual(a.git("status", "--porcelain", cwd=a.worktree("1")).strip(), "M src/calc.py")  # the work waits
        # The person set the brake and knows: no pull request gets the inbox label for it.
        self.assertFalse([p for p in github.read()["pulls"] if "rail:needs-you" in p["labels"]])
        # Another clone reads the same brake, and status shows it first.
        self.assertEqual(b.rail("next")["reason"]["code"], "STOPPED")
        status = a.rail("status")
        self.assertEqual(status["stops"], [{"number": 40, "title": "Stop: the deploy is broken", "paths": [],
                                            "url": "https://github.com/acme/app/issues/40"}])
        self.assertEqual([t["owner"] for t in status["tickets"]], ["person", "person"])
        self.assertTrue(a.rail("status", raw=True).stdout.startswith("STOPPED by issue #40 (Stop: the deploy is broken)\n"))
        self.assertGreaterEqual(len(github.read().get("calls", [])), calls)

        lift(github)
        a.queue_reviews({"summary": "Clean.", "findings": []})
        shipped = a.rail("advance", "1")
        self.assertNotEqual(shipped["reason"]["code"], "STOPPED")
        self.assertNotIn("stops", a.rail("status"))

    def test_a_stop_with_paths_stops_only_the_tickets_whose_scope_reaches_them(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        a.add(ticket(title="Other", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        brake(github, body="The handlers are being moved by hand.\n\npaths: `api/**`, docs/**\n")
        claimed = a.rail("next")
        self.assertEqual((claimed["ticket"], claimed["reason"]["code"]), ("1", "IMPLEMENT"))  # src/** goes on
        other = a.rail("next", "--ticket", "2")
        self.assertEqual(other["reason"]["code"], "STOPPED")
        self.assertIn("A person stopped Rail for the paths api/**, docs/**: issue #40", other["action"]["brief"])
        self.assertEqual(a.rail("status")["stops"][0]["paths"], ["api/**", "docs/**"])
        # With ticket 1 at work and ticket 2 stopped, a plain next has nothing for the agent, and says who it waits for.
        a.fix_calc("1")
        a.queue_reviews({"summary": "Clean.", "findings": []})
        a.rail("advance", "1")
        # Taking the label off lifts the brake as closing does.
        lift(github, how="unlabel")
        self.assertEqual(a.rail("next", "--ticket", "2")["reason"]["code"], "IMPLEMENT")

    def test_a_closed_stop_issue_and_a_project_with_no_remote_stop_nothing(self):
        a, b, github = self.github_pair()
        a.add(ticket())
        brake(github, state="closed")
        self.assertEqual(a.rail("next")["reason"]["code"], "IMPLEMENT")
        p = self.fixture()
        p.add(ticket())
        self.assertEqual(p.rail("next")["reason"]["code"], "IMPLEMENT")
