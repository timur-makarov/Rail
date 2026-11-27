"""The triage step: a question the engine raises about a shipped patch, answered by a fresh run before any review.

The run is the stand-in the reviewer has (fake_reviewer.py): with an empty [triage] command the review seat's command
answers, from the same queue. The step is tested with a question type of the test's own, written into the fixture's
copy of the engine, so that no test here depends on a type the engine may lose."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, RailTest, engine, ticket
from test_review import BLOCKING, clean, found

engine()
from rail import triage  # noqa: E402

# A type of the test's own: a line the change adds that says ASK raises it.
PLANTED = '''

def _find_marked(project, f, ref, patch_id):
    from .readthese import numbered
    return [{"key": f"{path}:{text.strip()}", "said": f"{path}:{n} says {text.strip()}", "file": path, "line": n}
            for path, lines in sorted(numbered(project, ref).items()) for n, text in lines if "ASK" in text]


question("marked", "The change adds a line that says ASK.", "Does the contract ask for the marked line?",
         {"asked": {"means": "the contract asks for the line.", "then": GO,
                    "evidence": "the Done Contract line that asks for it, word for word.", "check": quoted_in_ticket},
          "harmless": {"means": "the line changes nothing a contract could ask for.", "then": GO},
          "not-asked": {"means": "nothing in the contract asks for the line.", "then": STOP,
                        "told": "Remove the marked line, or amend the contract so that it asks for it."}},
         _find_marked, lambda project, f, fact: ["## The line", f"{fact['file']}:{fact['line']}"])
'''
MARKED = "def add(a, b):\n    return a + b  # ASK\n"


def said(answer, reason="Read the ticket.", **more):
    return {"answer": answer, "reason": reason, **more}


def events(p, kind=None, branch="1-fix-add"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if kind is None or e["event"] == kind]


def steps(p, step="triage"):
    return [e for e in events(p, "step") if e["step"] == step]


class Triage(RailTest):
    def planted(self, **kw):
        """A project whose engine has the test's question type, with ticket 1 claimed."""
        p = self.fixture(**kw)
        with open(p.path(".rail", "engine", "rail", "triage.py"), "a") as f:
            f.write(PLANTED)
        p.git("commit", "--quiet", "-am", "a question type of this project's own")
        p.add(ticket())
        p.rail("next")
        return p

    def marked(self, **kw):
        p = self.planted(**kw)
        p.write("src/calc.py", MARKED, base=p.worktree("1"))
        return p

    def test_a_fact_raises_one_question_for_a_patch_and_the_run_comes_before_any_review(self):
        p = self.marked()
        p.queue_reviews(said("harmless"), clean())
        shipped = p.rail("advance", "1")
        self.assertEqual((shipped["state"], shipped["reason"]["code"]), ("merge-ready", "MERGE"))
        self.assertEqual([s["step"] for s in shipped["steps"] if s["step"] in ("triage", "review")], ["triage", "review"])
        asked = events(p, "question")
        self.assertEqual([(q["id"], q["type"], q["key"]) for q in asked], [("Q1", "marked", "src/calc.py:return a + b  # ASK")])
        self.assertEqual(asked[0]["fact"], {"said": "src/calc.py:2 says return a + b  # ASK", "file": "src/calc.py", "line": 2})
        self.assertEqual(asked[0]["patch_id"], events(p, "shipped")[-1]["patch_id"])
        answered = events(p, "answered")
        self.assertEqual([(a["id"], a["type"], a["answer"], a["reason"], a["model"]) for a in answered],
                         [("Q1", "marked", "harmless", "Read the ticket.", "fake-model")])
        self.assertNotIn("evidence_ok", answered[0])  # the answer names no evidence, so nothing was checked
        run = steps(p)[0]
        self.assertEqual((run["result"], run["detail"], run["question"], run["type"], run["cost_usd"]),
                         ("pass", "Q1 marked: harmless", "Q1", "marked", 0.01))

        # The run read the question, its answers and the fact, with the triage prompt and a schema of this type's answers.
        first, second = p.briefs()
        self.assertIn("# One question about ticket 1 (Q1, marked)", first["brief"])
        self.assertIn("Does the contract ask for the marked line?", first["brief"])
        self.assertIn("- `asked`: the contract asks for the line. Evidence: the Done Contract line that asks for it,"
                      " word for word.", first["brief"])
        self.assertIn("- `not-asked`: nothing in the contract asks for the line.", first["brief"])
        self.assertIn("## What raised the question\nsrc/calc.py:2 says return a + b  # ASK", first["brief"])
        self.assertIn("## The line\nsrc/calc.py:2", first["brief"])
        self.assertNotIn("```diff", first["brief"])  # only what the type says to show
        self.assertEqual(first["prompt"], triage.PROMPT)
        self.assertEqual(json.loads(first["schema"])["properties"]["answer"]["enum"], ["asked", "harmless", "not-asked"])
        self.assertIn("This run's job: Review this change.", second["brief"])

        # The same patch shipped again raises no second question and starts no second run.
        with open(os.path.join(p.worktree("1"), ".rail", "tickets", "1.md"), "a") as f:
            f.write("\n## Tried\n- nothing else\n")
        again = p.rail("advance", "1")
        self.assertEqual((again["state"], [s for s in again["steps"] if s["step"] == "triage"]), ("merge-ready", []))
        self.assertEqual((len(events(p, "question")), len(events(p, "shipped")), len(p.briefs())), (1, 2, 2))

    def test_an_answer_with_evidence_the_engine_finds_lets_the_ticket_go_on_to_review(self):
        p = self.marked()
        p.queue_reviews(said("asked", evidence=f"Check: `{CHECK_ADD}`"), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        answered = events(p, "answered")[0]
        self.assertEqual((answered["answer"], answered["evidence"], answered["evidence_ok"]),
                         ("asked", f"Check: `{CHECK_ADD}`", True))
        self.assertEqual(len(p.briefs()), 2)

    def test_an_answer_that_stops_fails_triage_and_returns_the_ticket_to_the_worker(self):
        p = self.marked()
        p.queue_reviews(said("not-asked", "The contract has one check, and it does not read the comment."))
        stopped = p.rail("advance", "1", expect=3)
        self.assertEqual((stopped["state"], stopped["owner"], stopped["reason"]["code"]), ("implementing", "agent", "STEP_FAILED"))
        self.assertEqual(stopped["steps"][-1], {"step": "triage", "status": "ran", "result": "fail",
                                                "detail": "Q1 marked: not-asked"})
        self.assertEqual(len(p.briefs()), 1)  # no review of a patch that is about to change
        self.assertEqual(events(p, "shipped")[-1]["patch_id"], steps(p)[0]["patch_id"])
        self.assertNotIn("counted", steps(p)[0])  # it counts toward the retry budget like any failed step
        brief = stopped["action"]["brief"]
        for line in ("Ticket 1 shipped, and a triage answer stopped it (Q1 marked: not-asked).",
                     "The engine asked a run that did not write this change: Does the contract ask for the marked line?",
                     "What raised the question: src/calc.py:2 says return a + b  # ASK",
                     "Its answer: `not-asked`, nothing in the contract asks for the line.",
                     "Its reason: The contract has one check, and it does not read the comment.",
                     "Remove the marked line, or amend the contract so that it asks for it.",
                     "then run: rail advance 1"):
            self.assertIn(line, brief)
        self.assertEqual(stopped["action"]["facts"]["triage"], {
            "question": "Q1", "type": "marked", "ask": "Does the contract ask for the marked line?",
            "fact": "src/calc.py:2 says return a + b  # ASK", "answer": "not-asked",
            "means": "nothing in the contract asks for the line.",
            "reason": "The contract has one check, and it does not read the comment.",
            "told": "Remove the marked line, or amend the contract so that it asks for it."})
        self.assertEqual(p.rail("next")["action"]["brief"], brief)  # a fresh worker reads the same from the journal

        # Shipped again with nothing changed, the answer stands: the step fails with no second run.
        # It is the same failure twice, so the retry budget is reached and consult advises, as after any step.
        same = p.rail("advance", "1", expect=3)
        self.assertEqual([(s["step"], s.get("detail")) for s in same["steps"][-2:]],
                         [("triage", "Q1 marked: not-asked"), ("consult", "change")])
        self.assertIn("Its answer: `not-asked`, nothing in the contract asks for the line.", same["action"]["brief"])
        runs = lambda: [b for b in p.briefs() if not b["consult"]]  # noqa: E731
        self.assertEqual((len(runs()), len(events(p, "question")), len(steps(p))), (1, 1, 2))
        self.assertEqual(steps(p)[0]["signature"], steps(p)[1]["signature"])

        # The worker removes the line: the next patch has no such fact, so nothing is asked and the review runs.
        p.fix_calc("1")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual((len(events(p, "question")), len(runs())), (1, 2))

    def test_a_fact_that_still_holds_on_the_next_patch_is_asked_about_again(self):
        p = self.marked()
        p.queue_reviews(said("not-asked"))
        p.rail("advance", "1", expect=3)
        p.write("src/calc.py", "def add(a, b):\n    total = a + b\n    return total  # ASK\n", base=p.worktree("1"))
        p.queue_reviews(said("harmless"), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual([(q["id"], q["key"]) for q in events(p, "question")],
                         [("Q1", "src/calc.py:return a + b  # ASK"), ("Q2", "src/calc.py:return total  # ASK")])
        self.assertNotEqual(events(p, "question")[0]["patch_id"], events(p, "question")[1]["patch_id"])

    def test_an_amended_contract_has_the_same_patch_asked_about_again(self):
        p = self.marked()
        p.queue_reviews(said("not-asked"))
        p.rail("advance", "1", expect=3)
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        asks = "- Check: `grep -q ASK src/calc.py`"
        p.write(".rail/tickets/1.md", text.replace("## Done Contract\n", f"## Done Contract\n{asks}\n"), base=p.worktree("1"))
        p.rail("amend", "1", "the marker is part of the work")
        p.queue_reviews(said("asked", evidence=asks), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        first, second = events(p, "question")
        self.assertEqual((first["patch_id"], first["key"], second["id"]), (second["patch_id"], second["key"], "Q2"))
        self.assertEqual([(a["id"], a["answer"]) for a in events(p, "answered")], [("Q1", "not-asked"), ("Q2", "asked")])

    def test_evidence_that_is_not_in_the_ticket_repeats_the_run_once_and_then_waits_for_a_person(self):
        p = self.marked()
        p.queue_reviews(said("asked", evidence="Check: `make the marker stay`"), said("asked"), clean())
        waits = p.rail("advance", "1", expect=3)
        self.assertEqual((waits["state"], waits["owner"], waits["reason"]["code"]), ("reviewing", "person", "STUCK_REVIEW"))
        self.assertEqual([(s["detail"], s["counted"]) for s in steps(p)], [
            ("invalid output: the quoted line is in neither the Done Contract nor ## Why of the ticket", False),
            ("invalid output: the answer names no evidence", False)])
        self.assertEqual([a.get("evidence_ok") for a in events(p, "answered")], [False, False])
        self.assertEqual(len(p.briefs()), 2)  # two triage runs, and no review
        self.assertIn("The triage run of ticket 1 failed twice in a row with no answer", waits["action"]["brief"])
        self.assertEqual(waits["action"]["facts"]["run"], "triage")
        # No attempt of the author's was spent, and a person's accept starts the run again.
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "STUCK_REVIEW")
        p.rail("accept", "1", "the stand-in answers now")
        p.queue_reviews(said("harmless"), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(events(p, "question")), 1)

    def test_an_answer_the_type_does_not_have_or_no_json_is_invalid_output(self):
        p = self.marked()
        p.queue_reviews(said("maybe"), {"raw": "I think it is fine."})
        waits = p.rail("advance", "1", expect=3)
        self.assertEqual(waits["reason"]["code"], "STUCK_REVIEW")
        self.assertEqual([s["detail"] for s in steps(p)], [
            "invalid output: $.answer: 'maybe' is not one of asked, harmless, not-asked",
            "invalid output: the output is not JSON"])
        self.assertEqual(events(p, "answered"), [])

    def test_two_facts_are_two_questions_and_each_gets_its_own_run(self):
        p = self.planted()
        p.write("src/calc.py", MARKED + "\n\ndef twice(a):\n    return add(a, a)  # ASK again\n", base=p.worktree("1"))
        p.queue_reviews(said("harmless"), said("not-asked"))
        stopped = p.rail("advance", "1", expect=3)
        self.assertEqual([(s["detail"], s["result"]) for s in steps(p)],
                         [("Q1 marked: harmless", "pass"), ("Q2 marked: not-asked", "fail")])
        self.assertEqual(stopped["action"]["facts"]["triage"]["question"], "Q2")

    def test_triage_has_a_command_and_a_model_of_its_own_when_the_config_names_them(self):
        from railtest import CONFIG, FAKE
        log = os.path.join(self.tmp, "ran")
        p = self.marked(config=CONFIG + f'\n[triage]\ncommand = "echo $RAIL_TRIAGE $RAIL_TICKET >> {log}; python3 {FAKE}"\n'
                                         'model = "a-small-model"\n')
        p.queue_reviews(said("harmless"), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        with open(log) as f:
            self.assertEqual(f.read(), "marked 1\n")  # the review ran its own command
        self.assertEqual([b["model"] for b in p.briefs()], ["a-small-model", None])
        self.assertEqual(events(p, "answered")[0]["model"], "a-small-model")

    def test_the_run_changes_nothing_in_the_worktree(self):
        p = self.marked()
        p.queue_reviews({"touch": "scratch.txt", **said("harmless")}, clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertFalse(os.path.exists(os.path.join(p.worktree("1"), "scratch.txt")))
        self.assertEqual(p.git("status", "--porcelain", cwd=p.worktree("1")), "")

    def test_ci_fails_while_a_question_about_the_patch_is_open_or_its_answer_stops_the_change(self):
        p = self.marked()
        p.queue_reviews({"raw": "no"}, {"raw": "no"})
        p.rail("advance", "1", expect=3)

        def ci():
            folder = os.path.join(self.tmp, f"ci-{len(os.listdir(self.tmp))}")
            subprocess.run(["git", "clone", "--quiet", p.root, folder], check=True)
            subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", "1-fix-add").strip()],
                           cwd=folder, check=True)
            result = subprocess.run([os.path.join(folder, ".rail", "bin", "rail"), "ci", "--json"], cwd=folder,
                                    capture_output=True, text=True, env=dict(os.environ, RAIL_BRANCH="1-fix-add"))
            return result.returncode, json.loads(result.stdout)["steps"][-1]

        self.assertEqual(ci(), (3, {"step": "triage", "status": "ran", "result": "fail", "detail": "open: Q1"}))
        p.rail("accept", "1")
        p.queue_reviews(said("harmless"), clean())
        p.rail("advance", "1")
        self.assertEqual(ci()[0], 0)

    def test_stats_counts_each_types_questions_answers_runs_and_cost_on_merged_tickets(self):
        p = self.marked()
        p.queue_reviews(said("not-asked"))
        p.rail("advance", "1", expect=3)                                   # Q1: stopped
        p.write("src/calc.py", "def add(a, b):\n    total = a + b\n    return total  # ASK\n", base=p.worktree("1"))
        p.queue_reviews({"raw": "no"}, said("harmless"), clean())           # Q2: a run with no answer, then let through
        self.assertEqual(p.rail("advance", "1", expect=3)["state"], "merge-ready")  # 3: a run failed on the way
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")["stats"]
        self.assertEqual(stats["triage"], {"marked": {"questions": 2, "answers": {"not-asked": 1, "harmless": 1},
                                                      "runs": 3, "no_answer": 1, "cost_usd": 0.02}})
        self.assertEqual(stats["steps"]["triage"], {"runs": 3, "failed": 2, "could_not_run": 0})
        text = p.rail("stats", raw=True).stdout
        self.assertIn("TRIAGE  questions  runs  no answer   cost\nmarked          2     3          1  $0.02", text)
        self.assertIn("marked: not-asked 1 (50%), harmless 1 (50%).", text)

    def test_the_sweep_names_a_type_that_got_one_answer_in_19_of_its_last_20_questions(self):
        from railtest import CONFIG
        p = self.fixture(config=CONFIG + "\n[sweep]\nevery = 1\n")

        def journal(nn, answers):
            rows = []
            for n, answer in enumerate(answers):
                at = f"2026-11-{nn:02d}T10:{n:02d}:00Z"
                rows += [{"ticket": str(nn), "event": "question", "at": at, "id": f"Q{n + 1}", "type": "marked",
                          "patch_id": f"p{n}", "key": "k", "fact": {"said": "a line"}},
                         {"ticket": str(nn), "event": "answered", "at": at, "id": f"Q{n + 1}", "type": "marked",
                          "patch_id": f"p{n}", "answer": answer, "reason": "Read it."}]
            p.write(f".rail/journal/{nn}-events.jsonl", "".join(json.dumps(row) + "\n" for row in rows))

        # Journals of tickets merged before: 21 answered questions of one type, the oldest two answered another way.
        journal(11, ["not-asked", "not-asked", *["harmless"] * 9])
        journal(12, ["harmless"] * 10)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "journals of merged tickets")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        p.rail("advance", "1")
        swept = p.rail("sweep")
        self.assertEqual(swept["reason"]["code"], "SWEEP_TICKETS")  # something to file
        with open(os.path.join(p.worktree("2"), ".rail", "journal", "2-summary.md")) as f:
            summary = f.read()
        self.assertIn("## Question types with one answer\n- `marked` was answered `harmless` in 19 of its last 20"
                      " questions.", summary)

        # Two more answered the other way: 18 of the last 20, so it is still a question.
        journal(13, ["not-asked", "not-asked"])
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "one more journal")
        from rail.project import Project
        self.assertEqual(triage.settled(Project(p.root)), [])
