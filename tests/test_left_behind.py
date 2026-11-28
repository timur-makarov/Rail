"""The sweep gathers what merged tickets wrote down and nothing else reads: the lines workers left in their tickets,
the findings authors declined, a person's notes, the failures that recur across tickets, and the comments that name a
ticket that ended. Each gets a section of the summary, for the agent that files the sweep's tickets."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

CLEAN = {"summary": "Clean.", "findings": []}
OFF = CONFIG + "\n[sweep]\nevery = 0\n"  # no sweep comes due, and no pass reads the areas: each test runs it by hand


def write_ticket(p, nn, more):
    path = os.path.join(p.worktree(nn), ".rail", "tickets", f"{nn}.md")
    with open(path) as f:
        text = f.read()
    with open(path, "w") as f:
        f.write(text.rstrip("\n") + "\n" + more)


def summary_of(p, nn):
    with open(os.path.join(p.worktree(nn), ".rail", "journal", f"{nn}-summary.md")) as f:
        return f.read()


def failed(answer):
    return [s["step"] for s in answer["steps"] if s.get("result") == "fail"]


def section(text, title):
    """The lines under one `## title` of a summary."""
    return text.split(f"## {title}\n", 1)[1].split("\n## ", 1)[0].strip()


class Markers(RailTest):
    def test_a_todo_whose_ticket_ended_gets_a_removal_ticket(self):
        p = self.fixture(config=OFF)
        p.add(ticket())
        p.add(ticket(title="Take floats", check="grep -q float src/calc.py"))
        p.add(ticket(title="Take strings", check="grep -q str src/calc.py"))
        p.rail("next", "--ticket", "1")
        p.write("src/calc.py", "def add(a, b):\n    # TODO(2): take floats as well\n    # FIXME(3): and strings\n"
                               "    # TODO(1): cents\n    return a + b\n", base=p.worktree("1"))
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        # Ticket 2 merges and leaves the comment that names it. Ticket 3 is dropped.
        p.rail("next", "--ticket", "2")
        with open(os.path.join(p.worktree("2"), "src", "calc.py"), "a") as f:
            f.write("\n\nZERO = float(0)\n")
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")
        p.rail("drop", "3", "--reason", "nobody adds strings", "--by", "person")

        swept = p.rail("sweep")
        self.assertEqual((swept["ticket"], swept["reason"]["code"]), ("4", "SWEEP_TICKETS"))
        left = section(summary_of(p, "4"), "Work left for later whose ticket ended")
        self.assertEqual(left.splitlines(), [
            "- ticket 1 merged, and 1 comment still names it. Open one ticket with `external_id = \"todo#1\"` that does"
            " what is left or removes it. Check: `! git grep -n -E '(TODO|FIXME)\\(1\\)' -- . ':(exclude).rail'`",
            "    - src/calc.py:4: # TODO(1): cents",
            "- ticket 2 merged, and 1 comment still names it. Open one ticket with `external_id = \"todo#2\"` that does"
            " what is left or removes it. Check: `! git grep -n -E '(TODO|FIXME)\\(2\\)' -- . ':(exclude).rail'`",
            "    - src/calc.py:2: # TODO(2): take floats as well",
            "- ticket 3 was dropped, and 1 comment still names it. Open one ticket with `external_id = \"todo#3\"` that"
            " does what is left or removes it. Check: `! git grep -n -E '(TODO|FIXME)\\(3\\)' -- . ':(exclude).rail'`",
            "    - src/calc.py:3: # FIXME(3): and strings"])
        self.assertIn("3 tickets with comments left behind", swept["steps"][-1]["detail"])

        # The agent files the removal ticket for ticket 2 as the summary says, with its check, and the sweep merges.
        removal = ticket(title="Remove the TODO(2) comment ticket 2 left", front=('external_id = "todo#2"',),
                         check="! git grep -n -E '(TODO|FIXME)\\(2\\)' -- . ':(exclude).rail'")
        self.assertEqual(p.add(removal)["ticket"], "5")
        p.rail("advance", "4")
        self.assertEqual(p.rail("advance", "4")["state"], "merged")

        # The removal ticket's check is red while the comment stands, and green once it is gone.
        p.rail("next", "--ticket", "5")
        self.assertEqual(failed(p.rail("advance", "5", expect=3)), ["checks"])
        # While the removal ticket is open the next sweep does not name ticket 2 again.
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next", "--ticket", "6")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("6"))
        p.rail("advance", "6")
        self.assertEqual(p.rail("advance", "6")["state"], "merged")
        again = section(summary_of(p, p.rail("sweep")["ticket"]), "Work left for later whose ticket ended")
        self.assertIn("- ticket 1 merged", again)
        self.assertIn("- ticket 3 was dropped", again)
        self.assertNotIn("ticket 2", again)

        text = "def add(a, b):\n    # FIXME(3): and strings\n    # TODO(1): cents\n    return a + b\n\n\nZERO = float(0)\n"
        p.write("src/calc.py", text, base=p.worktree("5"))
        p.rail("advance", "5")
        self.assertEqual(p.rail("advance", "5")["state"], "merged")

    def test_a_marker_whose_ticket_is_open_is_left_alone(self):
        p = self.fixture(config=OFF)
        p.add(ticket())
        p.add(ticket(title="Take floats", check="grep -q float src/calc.py"))
        p.rail("next", "--ticket", "1")
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # TODO(2): take floats, SHORTCUT(1): ints only\n",
                base=p.worktree("1"))
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        swept = p.rail("sweep")
        # Ticket 2 will still do the work, and a SHORTCUT names the ticket that cut the corner: it stays.
        self.assertEqual(swept["reason"]["code"], "SWEEP_EMPTY")
        self.assertEqual(section(summary_of(p, "3"), "Work left for later whose ticket ended"), "(none)")


class Left(RailTest):
    def test_the_lines_a_worker_left_a_declined_finding_and_a_persons_note_reach_the_summary(self):
        p = self.fixture(config=OFF)
        naming = {"severity": "advisory", "file": "src/calc.py", "claim": "add  has no docstring."}
        for nn, tier in (("1", "AUTO"), ("2", "PERSON")):
            p.add(ticket(title=f"Fix add {nn}", tier=tier, check=f"grep -q '# {nn}' src/calc.py"))
            p.rail("next", "--ticket", nn)
            p.write("src/calc.py", f"def add(a, b):\n    return a + b\n# {nn}\n", base=p.worktree(nn))
            if nn == "1":
                write_ticket(p, nn, "\n## Look at\n- The sign of the result.\n- not tested: floats, because nothing"
                                    " passes them\n- Noticed: api/handlers.py answers 200 where it creates something\n")
            p.queue_reviews({"summary": "Read it.", "findings": [dict(naming, claim=naming["claim"].upper() if nn == "2" else naming["claim"])]},
                            CLEAN, CLEAN)
            p.rail("advance", nn)
            p.rail("answer", nn, "F1", "declined", "The project writes no docstrings." if nn == "1" else "As before.")
            if tier == "PERSON":
                self.assertEqual(p.rail("advance", nn)["reason"]["code"], "MERGE_BY_PERSON")
                p.rail("accept", nn, "Money is  always in cents, never floats.")
            self.assertEqual(p.rail("advance", nn)["state"], "merged")

        swept = p.rail("sweep")
        self.assertEqual((swept["ticket"], swept["reason"]["code"]), ("3", "SWEEP_TICKETS"))
        self.assertEqual(swept["steps"][-1]["detail"],
                         "no review run: 0 parked findings, 0 proposed checks, 0 patterns in the worker runs, 0 flaky"
                         " checks, 1 kinds of declined findings, 2 lines workers left, 1 notes a person gave")
        text = summary_of(p, "3")
        # One kind: the same claim in two tickets, spacing and case aside, with the first author's reason.
        self.assertEqual(section(text, "Findings an author declined, by kind").splitlines()[1:],
                         ["- add  has no docstring. (1/F1, 2/F1). The author's reason: The project writes no docstrings."])
        self.assertEqual(section(text, "Problems workers saw outside their tickets, and what they did not test").splitlines()[1:],
                         ["- ticket 1, Noticed: api/handlers.py answers 200 where it creates something",
                          "- ticket 1, not tested: floats, because nothing passes them"])
        self.assertEqual(section(text, "What a person said with rail accept").splitlines()[1:],
                         ["- ticket 2: Money is always in cents, never floats."])
        self.assertEqual(section(text, "Failures that recur across tickets"), "(none)")

    def test_a_failure_two_tickets_share_is_named_once(self):
        p = self.fixture(config=OFF)
        for nn in ("1", "2", "3"):
            p.add(ticket(title=f"Fix add {nn}", check=f"grep -q '# {nn}' src/calc.py"))
            p.rail("next", "--ticket", nn)
            if nn != "3":
                # The same slip in two tickets: verify fails the same way, whatever the folder it ran in.
                p.write("src/calc.py", f"def add(a, b):\n    return a +\n# {nn}\n", base=p.worktree(nn))
                self.assertEqual(failed(p.rail("advance", nn, expect=3)), ["verify"])
            else:
                self.assertEqual(failed(p.rail("advance", nn, expect=3)), ["checks"])  # its own failure
            p.write("src/calc.py", f"def add(a, b):\n    return a + b\n# {nn}\n", base=p.worktree(nn))
            p.rail("advance", nn)
            self.assertEqual(p.rail("advance", nn)["state"], "merged")
        swept = p.rail("sweep")
        self.assertEqual(swept["reason"]["code"], "SWEEP_TICKETS")
        lines = section(summary_of(p, "4"), "Failures that recur across tickets").splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertEqual(lines[1], "- step `verify` failed the same way in 2 tickets (1, 2): exit 1")


if __name__ == "__main__":
    import unittest
    unittest.main()
