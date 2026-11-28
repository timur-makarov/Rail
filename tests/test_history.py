"""What one ticket learned reaches the next agent: the brief carries the ticket's why and its decided rows, what
earlier attempts tried, and what earlier tickets on the same paths decided, left untested, noticed and marked."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

CLEAN = {"summary": "Clean.", "findings": []}
DECIDED = ("\n## Assumptions\n- VERIFIED: decided, not checked: ints only, because every caller passes ints; a float"
           " caller would get a rounded sum.\n- VERIFIED: add is called from api/handlers.py (read the file).\n")
LOOK_AT = ("\n## Look at\n- The sign of the result.\n- not tested: floats, because nothing passes them\n"
           "- Noticed: api/handlers.py answers 200 where it creates something\n")
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "config.toml")) as f:
    TODO_RULE = "\n[[rules]]\n" + f.read().split("[[rules]]")[4]  # the seed's fourth rule, as it ships


def write_ticket(p, nn, more):
    path = os.path.join(p.worktree(nn), ".rail", "tickets", f"{nn}.md")
    with open(path) as f:
        text = f.read()
    with open(path, "w") as f:
        f.write(text.rstrip("\n") + "\n" + more)


class Brief(RailTest):
    def test_the_implement_brief_carries_the_why_and_the_decided_rows(self):
        p = self.fixture()
        p.add(ticket(body=DECIDED))
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("\nWhy:\nadd subtracts instead of adding.\n", brief)
        self.assertIn("Decided when the ticket was written, and not checked. Keep to each one, or write in the ticket"
                      " why it is wrong:\n- ints only, because every caller passes ints; a float caller would get a"
                      " rounded sum.\n", brief)
        self.assertNotIn("read the file", brief)  # a row somebody checked is no decision
        self.assertNotIn("Earlier tickets", brief)  # nothing merged on these paths yet
        self.assertIn('write a line there that starts "Noticed:"', brief)

    def test_what_was_tried_reaches_the_next_attempt_and_not_consult(self):
        p = self.fixture()
        p.add(ticket(title="Subtract", check="grep subtract src/calc.py"))
        p.rail("next")
        failed = p.rail("advance", "1", expect=3)
        self.assertIn('Before you try again, write one line under "## Tried" in .rail/tickets/1.md', failed["action"]["brief"])
        write_ticket(p, "1", "\n## Tried\n- a lambda named sub: the check wants the word subtract\n")
        # Written and not committed yet: the brief reads the worktree's copy.
        again = p.rail("next", "--ticket", "1")["action"]["brief"]
        self.assertIn("Tried before on this ticket, and it didn't work (## Tried in the ticket):\n"
                      "- a lambda named sub: the check wants the word subtract", again)
        # The same failure again brings consult in, which gets the ticket without the worker's own story.
        p.rail("advance", "1", expect=3)
        asked = [b["brief"] for b in p.briefs() if b["consult"]][-1]
        self.assertIn("## Done Contract", asked)
        self.assertNotIn("a lambda named sub", asked)
        # A worker that starts over on new code (a new session, the next rung of the ladder) gets it with the task.
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n\n\nsub = None\n", base=p.worktree("1"))
        p.rail("save", "1")
        fresh = p.rail("next", "--ticket", "1")
        self.assertEqual(fresh["reason"]["code"], "IMPLEMENT")
        self.assertIn("Tried before on this ticket, and it didn't work (## Tried in the ticket):\n"
                      "- a lambda named sub: the check wants the word subtract", fresh["action"]["brief"])


class Earlier(RailTest):
    def merged(self, p, nn, code, more=LOOK_AT, first=()):
        write_ticket(p, nn, more)
        p.write("src/calc.py", code, base=p.worktree(nn))
        p.queue_reviews(*first, CLEAN)
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

    def test_the_next_ticket_on_the_same_paths_is_told_what_the_last_one_left(self):
        p = self.fixture()
        p.add(ticket(body=DECIDED))
        p.rail("next")
        # The row its author decided is asked about first (rail docs triage), and stands as a choice.
        self.merged(p, "1", "def add(a, b):\n    return a + b  # SHORTCUT(1): ints only; use Decimal for money\n",
                    first=({"answer": "choice", "reason": "Nothing in the repository says what callers pass."},))
        p.add(ticket(title="Subtract", check="grep subtract src/calc.py"))
        p.add(ticket(title="Created", scope=("api/**",), check="grep 201 api/handlers.py"))
        brief = p.rail("next", "--ticket", "2")["action"]["brief"]
        self.assertIn("Earlier tickets that changed these paths, newest first. Their decisions stand unless this"
                      " ticket says otherwise:\n"
                      "- 1 Fix add: add subtracts instead of adding.\n"
                      "    decided: ints only, because every caller passes ints; a float caller would get a rounded sum.\n"
                      "    not tested: floats, because nothing passes them\n"
                      "    noticed: api/handlers.py answers 200 where it creates something\n"
                      "Markers standing in these paths (the number is the ticket that left it, or the one that will do"
                      " it):\n"
                      "- src/calc.py:2: return a + b  # SHORTCUT(1): ints only; use Decimal for money\n", brief)
        history = p.rail("context", "2")["history"]
        self.assertEqual([t["ticket"] for t in history["tickets"]], ["1"])
        self.assertEqual((history["tickets"][0]["title"], history["more_markers"]), ("Fix add", 0))
        # A ticket on other paths is told nothing of it.
        other = p.rail("next", "--ticket", "3")["action"]["brief"]
        self.assertNotIn("Earlier tickets", other)
        self.assertNotIn("Markers standing", other)
        self.assertEqual(p.rail("context", "3")["history"], {"tickets": [], "markers": [], "more_markers": 0})

    def test_the_history_is_the_last_five_tickets_newest_first_and_ten_markers(self):
        p = self.fixture()
        code = "def add(a, b):\n    return a + b\n"
        for n in range(1, 8):
            p.add(ticket(title=f"Step {n}", check=f"grep step{n} src/calc.py"))
            p.rail("next")
            code += f"\n\ndef step{n}():\n    return {n}  # SHORTCUT({n}): fixed; read it from the config\n" \
                    f"    # TODO({n + 20}): take the unit as well\n"
            self.merged(p, str(n), code, more="")
        p.add(ticket(title="Step 8", check="grep step8 src/calc.py"))
        history = p.rail("context", "8")["history"]
        self.assertEqual([t["ticket"] for t in history["tickets"]], ["7", "6", "5", "4", "3"])
        self.assertEqual((len(history["markers"]), history["more_markers"]), (10, 4))
        self.assertIn("- and 4 more", p.rail("next")["action"]["brief"])


class Todo(RailTest):
    def test_work_left_for_later_names_its_ticket(self):
        self.assertIn("todo-names-its-ticket", TODO_RULE)
        p = self.fixture(config=CONFIG + TODO_RULE)
        p.add(ticket())
        p.rail("next")
        work = p.worktree("1")
        bad = ("# TODO: floats", "# FIXME: floats", "# TODO floats", "// FIXME floats", "# TODO(): floats")
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n" + "".join(f"{line}\n" for line in bad), base=work)
        failed = p.rail("advance", "1", expect=3)
        step = [s for s in failed["steps"] if s.get("result") == "fail"][0]
        self.assertEqual((step["step"], step["detail"]), ("rules", "5 broken: todo-names-its-ticket"))
        brief = failed["action"]["brief"]
        for line in bad:
            self.assertIn(line, brief)
        self.assertIn("File the work with rail add, then write TODO(NN): with that ticket's number", brief)
        self.assertNotIn("## Tried", brief)  # a slip at a lint step is no attempt at the work
        self.assertNotIn("## Tried", p.rail("next", "--ticket", "1")["action"]["brief"])
        # With its ticket's number it passes, and so does a word that only looks like the marker.
        p.write("src/calc.py", "def add(a, b):\n    return a + b  # TODO(7): floats\n\n\nTITLE = 'TODO list'\n", base=work)
        p.queue_reviews(CLEAN)
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
