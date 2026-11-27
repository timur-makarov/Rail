"""An exemption the author writes is confirmed: a `SENSOR(NN): why` comment, a `VERIFIED: decided, not checked:` row
and a line in `.gitleaksignore` each raise a triage question (rail docs triage)."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CHECK_ADD, CONFIG, RailTest, ticket
from test_review import clean
from test_sensors import FIND, FIXED, LEGACY, SENSOR
from test_triage import said

COMMENT = "# SENSOR(1): FIXME is the word this function counts"
COUNTS = FIXED + f"\n\ndef notes(text):\n    {COMMENT}\n    return text.count(\"FIXME\")\n"
ROW = "ints only, because every caller passes ints; a float caller would get a rounded sum."
ASSUMED = "\n## Assumptions\n- ASSUMED: every caller passes ints.\n"
# A stand-in for gitleaks: it writes the report the test gives it, as gitleaks does with --report-path.
GITLEAKS = '''#!/usr/bin/env python3
import os
import shutil
import sys

path = sys.argv[sys.argv.index("--report-path") + 1]
if os.environ.get("FAKE_GITLEAKS_REPORT"):
    shutil.copy(os.environ["FAKE_GITLEAKS_REPORT"], path)
    sys.exit(1)
sys.exit(126)
'''
KEYS = 'import os\n\nREGION = "eu-west-1"\nTOKEN = "tok_live_9f8e7d6c5b4a39281706f5e4d3c2b1a0"\nRETRIES = 3\nWAIT = 2\n'


def events(p, kind, branch="1-fix-add"):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/1-events.jsonl").splitlines()]
    return [e for e in rows if e["event"] == kind]


def on_remote(github):
    """The ticket branches the remote has."""
    out = subprocess.run(["git", "--git-dir", github.read()["bare"], "for-each-ref", "--format=%(refname:short)",
                          "refs/heads/1-*"], capture_output=True, text=True).stdout
    return sorted(out.split())


def triage_briefs(p):
    return [b["brief"] for b in p.briefs() if b["brief"].startswith("# One question")]


class SensorComment(RailTest):
    def claimed(self, calc=LEGACY):
        p = self.fixture(config=CONFIG + SENSOR, files={
            ".rail/sensors/find.py": FIND, ".rail/sensors/words.txt": "FIXME\n", "src/calc.py": calc})
        p.add(ticket())
        p.rail("next")
        return p

    def test_a_comment_the_change_adds_raises_one_question_and_its_answer_stands_for_later_patches(self):
        p = self.claimed()
        p.write("src/calc.py", COUNTS, base=p.worktree("1"))
        p.queue_reviews(said("holds", "The line counts the word; it is no note to anyone."), clean())
        shipped = p.rail("advance", "1")
        self.assertEqual(shipped["state"], "merge-ready")
        (sensors,) = [e for e in events(p, "step") if e["step"] == "sensors"]
        self.assertEqual(sensors["excused"], [{"sensor": "words", "path": "src/calc.py", "line": 11,
                                               "message": "the word FIXME", "marker_line": 11, "marker": COMMENT},
                                              {"sensor": "words", "path": "src/calc.py", "line": 12,
                                               "message": "the word FIXME", "marker_line": 11, "marker": COMMENT}])
        (asked,) = events(p, "question")
        self.assertEqual((asked["id"], asked["type"], asked["key"]), ("Q1", "sensor-exempt", f"src/calc.py: {COMMENT}"))
        self.assertEqual(asked["fact"]["violations"], ["src/calc.py:11: the word FIXME (sensor words)",
                                                       "src/calc.py:12: the word FIXME (sensor words)"])
        (brief,) = triage_briefs(p)
        for text in ("# One question about ticket 1 (Q1, sensor-exempt)", "Does the comment's\nreason hold?".replace("\n", " "),
                     "- src/calc.py:12: the word FIXME (sensor words)", "What sensor words asks for: Say it another way.",
                     f"   11      {COMMENT}", '   12      return text.count("FIXME")',
                     "- `holds`: the sensor misreads the line, or the contract requires the line as it is.",
                     "It lets the change through.", "- `does-not-hold`:", "It stops the change.",
                     f"## The ticket's Done Contract\n- Check: `{CHECK_ADD}`"):
            self.assertIn(text, brief)
        (answer,) = events(p, "answered")
        self.assertEqual((answer["answer"], answer["evidence_ok"]), ("holds", True))

        # A later patch keeps the comment: the answer stands, and no run is spent on it.
        p.write("src/calc.py", COUNTS + "\n\ndef twice(a):\n    return a * 2\n", base=p.worktree("1"))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(events(p, "question")), 1)
        self.assertEqual(len(triage_briefs(p)), 1)

    def test_a_reason_that_does_not_hold_fails_triage_and_evidence_is_looked_up_when_given(self):
        p = self.claimed()
        p.write("src/calc.py", COUNTS, base=p.worktree("1"))
        p.queue_reviews(said("does-not-hold", "A count of a word can be written without the word in the source."))
        stopped = p.rail("advance", "1", expect=3)
        self.assertEqual((stopped["reason"]["code"], stopped["steps"][-1]["detail"]),
                         ("STEP_FAILED", "Q1 sensor-exempt: does-not-hold"))
        for text in (f"The change adds the comment `{COMMENT}` at src/calc.py:11",
                     "Its answer: `does-not-hold`, the sensor is right about the line",
                     "Take the comment out and mend the line so that the sensor passes."):
            self.assertIn(text, stopped["action"]["brief"])

        # The worker changes the reason: the comment is another line now, so it is asked about again. An answer that
        # quotes a line the ticket does not have is no answer, and the run is started once more.
        p.write("src/calc.py", COUNTS.replace("this function counts", "the caller asks for"), base=p.worktree("1"))
        p.queue_reviews(said("holds", evidence="- notes counts the word FIXME."),
                        said("holds", evidence="add subtracts instead of adding."), clean())
        again = p.rail("advance", "1", expect=3)
        self.assertEqual(again["state"], "merge-ready")
        self.assertEqual([(a["answer"], a.get("evidence_ok")) for a in events(p, "answered")],
                         [("does-not-hold", None), ("holds", False), ("holds", True)])
        self.assertEqual([q["id"] for q in events(p, "question")], ["Q1", "Q2"])

    def test_a_comment_the_base_already_had_raises_nothing(self):
        base = LEGACY + "\n\ndef notes(text):\n    # SENSOR(0): the word is counted here\n    return text\n"
        p = self.claimed(calc=base)
        fixed = base.replace("return a - b", "return a + b")
        p.write("src/calc.py", fixed.replace("    return text\n", "    found = text.count(\"FIXME\")\n    return found\n"),
                base=p.worktree("1"))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        (sensors,) = [e for e in events(p, "step") if e["step"] == "sensors"]
        self.assertEqual([x["marker_line"] for x in sensors["excused"]], [11])
        self.assertEqual(events(p, "question"), [])


class DecidedRow(RailTest):
    def decided(self, p):
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace("ASSUMED: every caller passes ints.",
                                                   f"VERIFIED: decided, not checked: {ROW}"), base=p.worktree("1"))

    def claimed(self):
        p = self.fixture()
        p.add(ticket(body=ASSUMED))
        p.rail("next")
        p.fix_calc("1")
        self.decided(p)
        return p

    def test_a_row_the_author_decided_raises_one_question_and_a_choice_goes_on(self):
        p = self.claimed()
        p.queue_reviews(said("choice", "No caller is in this repository, and no check passes anything but ints."), clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        (asked,) = events(p, "question")
        self.assertEqual((asked["type"], asked["key"]), ("decided", ROW))
        (brief,) = triage_briefs(p)
        for text in (f"## The row\nVERIFIED: decided, not checked: {ROW}", "Is it one?",
                     "- `choice`: nothing in the repository or its dependencies settles it, and no Done Contract item"
                     " depends on it. It lets the change through.",
                     "- `checkable`: it can be checked. Evidence: where: the file, the command or the document that"
                     " settles it. It stops the change.",
                     "- `contract`: a Done Contract item depends on it", "## Where the ticket may change\nsrc/**"):
            self.assertIn(text, brief)
        # The row stays through a later patch, and is not asked about again.
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n\n\ndef twice(a):\n    return a * 2\n", base=p.worktree("1"))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(events(p, "question")), 1)

    def test_a_row_that_can_be_checked_goes_back_to_the_worker_with_where(self):
        p = self.claimed()
        p.queue_reviews(said("checkable", "The callers are in this repository.", evidence="grep -rn 'add(' api/"))
        stopped = p.rail("advance", "1", expect=3)
        self.assertEqual((stopped["reason"]["code"], stopped["steps"][-1]["detail"]),
                         ("STEP_FAILED", "Q1 decided: checkable"))
        for text in (f"decided and did not check: {ROW}", "Its answer: `checkable`, it can be checked.",
                     "What the answer names: grep -rn 'add(' api/",
                     "Check it where the answer names, then write in the row how you checked"):
            self.assertIn(text, stopped["action"]["brief"])
        # Checked, the row is no decided row any more, and nothing is asked.
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        p.write(".rail/tickets/1.md", text.replace(f"decided, not checked: {ROW}", "every caller passes ints (grep, api/)."),
                base=p.worktree("1"))
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n\n\nONE = 1\n", base=p.worktree("1"))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(events(p, "question")), 1)

    def test_a_row_a_contract_item_depends_on_is_amended_into_the_contract(self):
        p = self.claimed()
        p.queue_reviews(said("contract", "The check passes ints, so the contract rests on the row.",
                             evidence=f"- Check: `{CHECK_ADD}`"))
        stopped = p.rail("advance", "1", expect=3)
        self.assertEqual(stopped["steps"][-1]["detail"], "Q1 decided: contract")
        for text in ("Amend the contract so that the choice stands where the reviewer reads it",
                     'take the row out of ## Assumptions, and run rail amend 1 "why"'):
            self.assertIn(text, stopped["action"]["brief"])
        # The contract states the choice now and the row is gone: nothing is left to ask about.
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        with open(path) as f:
            text = f.read()
        text = text.replace(f"- VERIFIED: decided, not checked: {ROW}\n", "- VERIFIED: add is called (read the file).\n")
        p.write(".rail/tickets/1.md", text.replace("## Done Contract\n", "## Done Contract\n- add takes ints only.\n"),
                base=p.worktree("1"))
        p.rail("amend", "1", "the contract says ints only")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(len(triage_briefs(p)), 1)


class IgnoredSecret(RailTest):
    def claimed(self, pair=False):
        if pair:
            p, b, github = self.github_pair()
        else:
            p, b, github = self.fixture(), None, None
        p.add(ticket())
        p.rail("next")
        wt = p.worktree("1")
        # The secret is in a commit of the branch, as after a save; the line that excuses it comes with the ship.
        p.write("src/keys.py", KEYS, base=wt)
        p.git("add", "src/keys.py", cwd=wt)
        p.git("commit", "--quiet", "-m", "wip", cwd=wt)
        self.commit = p.git("rev-parse", "HEAD", cwd=wt).strip()
        self.line = f"{self.commit}:src/keys.py:generic-api-key:4"
        p.write(".gitleaksignore", f"# findings that are no secrets\n{self.line}\n", base=wt)
        p.fix_calc("1")
        self.bin = os.path.join(self.tmp, "scanbin")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "gitleaks"), "w") as f:
            f.write(GITLEAKS)
        os.chmod(os.path.join(self.bin, "gitleaks"), 0o755)
        return (p, b, github) if pair else p

    def scan(self, report=None):
        """The environment of a run whose gitleaks is the stand-in: with a report of the finding, or with none."""
        path = (getattr(self, "github_bin", "") + os.pathsep if getattr(self, "github_bin", "") else "") + \
            self.bin + os.pathsep + os.environ["PATH"]
        env = {"PATH": path}
        if report is not None:
            held = os.path.join(self.tmp, "report.json")
            with open(held, "w") as f:
                json.dump(report, f)
            env["FAKE_GITLEAKS_REPORT"] = held
        return env

    def found(self):
        return [{"RuleID": "generic-api-key", "StartLine": 4, "EndLine": 4, "Match": 'TOKEN = "REDACTED"',
                 "Secret": "REDACTED", "File": "src/keys.py", "Commit": self.commit, "Fingerprint": self.line}]

    def test_a_line_in_gitleaksignore_raises_one_question_whose_brief_shows_the_string_only_redacted(self):
        p = self.claimed()
        p.queue_reviews(said("not-a-secret"), said("not-a-secret", evidence="A made-up token in the format the docs show."),
                        clean())
        shipped = p.rail("advance", "1", expect=3, env_extra=self.scan(self.found()))
        self.assertEqual(shipped["state"], "merge-ready")
        (asked,) = events(p, "question")
        self.assertEqual((asked["type"], asked["key"]), ("secret", self.line))
        self.assertEqual({k: asked["fact"][k] for k in ("commit", "file", "rule", "line")},
                         {"commit": self.commit, "file": "src/keys.py", "rule": "generic-api-key", "line": 4})
        # An answer that does not say what the string is is no answer: the run was started once more.
        self.assertEqual([a.get("evidence_ok") for a in events(p, "answered")], [False, True])
        brief = triage_briefs(p)[0]
        for text in ("# One question about ticket 1 (Q1, secret)", "Rule: generic-api-key", "File: src/keys.py, line 4",
                     f"Commit: {self.commit}", '    3  REGION = "eu-west-1"', '    4  TOKEN = "REDACTED"', "    5  RETRIES = 3",
                     "The scan's own redaction stands in for the string.",
                     "- `not-a-secret`: the string is no credential: an example, a fixture, a public id. Evidence: what"
                     " the string is, in a few words. It lets the change through.",
                     "- `secret`: the string is, or may be, a real credential.", "It holds the ticket for a person."):
            self.assertIn(text, brief)
        self.assertNotIn("tok_live", brief)

    def test_without_the_scans_report_the_brief_leaves_the_line_and_what_follows_it_out(self):
        p = self.claimed()
        p.queue_reviews(said("not-a-secret", evidence="An example."), clean())
        self.assertEqual(p.rail("advance", "1", env_extra=self.scan())["state"], "merge-ready")
        (brief,) = triage_briefs(p)
        for text in ('    3  REGION = "eu-west-1"', "    4  (the line the scan reported is not shown)",
                     "The scan's report could not be read here"):
            self.assertIn(text, brief)
        for text in ("tok_live", "RETRIES"):
            self.assertNotIn(text, brief)

    def test_a_real_secret_waits_for_a_person_and_then_the_branch_starts_again_from_the_base(self):
        p = self.claimed()
        p.queue_reviews(said("secret", "The token has the live prefix and the file reads no environment."))
        held = p.rail("advance", "1", expect=3, env_extra=self.scan(self.found()))
        self.assertEqual((held["owner"], held["reason"]["code"], held["action"]["kind"]),
                         ("person", "SECRET_FOUND", "person_wait"))
        facts = held["action"]["facts"]
        self.assertEqual((facts["question"], facts["finding"], facts["wait"]),
                         ("Q1", {"rule": "generic-api-key", "file": "src/keys.py", "line": 4, "commit": self.commit},
                          {"kind": "grant", "accept": "rail accept 1"}))
        for text in ("hold a real secret (rule generic-api-key, src/keys.py line 4, commit", "counts as leaked",
                     "A person rotates it where it was issued, then continues: rail accept 1.",
                     "starts the ticket's branch again from the base branch"):
            self.assertIn(text, held["action"]["brief"])
        self.assertEqual(p.rail("next", "1")["reason"]["code"], "SECRET_FOUND")  # it waits, whoever looks

        # The person has rotated it. The engine's next move is the restart, and the work is to do again.
        self.assertEqual(p.rail("accept", "1")["reason"]["code"], "RESTART")
        again = p.rail("next", "1")
        self.assertEqual((again["state"], again["reason"]["code"]), ("implementing", "IMPLEMENT"))
        self.assertIn({"step": "restart", "status": "ran", "result": "pass", "detail": "1-fix-add -> 1-fix-add--2"},
                      again["steps"])
        self.assertEqual(again["action"]["facts"]["restarted"],
                         {"branch": "1-fix-add", "rule": "generic-api-key", "file": "src/keys.py", "type": "secret"})
        for text in ("The engine started this ticket's branch again from the base branch",
                     "(1-fix-add) held a secret (generic-api-key in src/keys.py)", "write no credential into any file"):
            self.assertIn(text, again["action"]["brief"])
        branches = p.git("branch", "--format=%(refname:short)").split()
        self.assertIn("1-fix-add--2", branches)
        self.assertNotIn("1-fix-add", branches)
        wt = p.worktree("1")
        self.assertEqual(p.git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt).strip(), "1-fix-add--2")
        # One commit on the base's tip, with the ticket and its journal and none of the work.
        self.assertEqual(p.git("rev-list", "--count", "main..1-fix-add--2").strip(), "2")
        self.assertEqual(p.git("diff", "--name-only", "main", "1-fix-add--2").split(),
                         [".rail/journal/1-events.jsonl", ".rail/tickets/1.md"])
        self.assertFalse(os.path.exists(os.path.join(wt, "src", "keys.py")))
        self.assertFalse(os.path.exists(os.path.join(wt, ".gitleaksignore")))
        (restarted,) = events(p, "restarted", "1-fix-add--2")
        self.assertEqual((restarted["question"], restarted["branch"], restarted["to"]), ("Q1", "1-fix-add", "1-fix-add--2"))
        self.assertEqual(len(events(p, "question", "1-fix-add--2")), 1)   # the journal came along

        # The work is done again without the string, and the ticket goes its way.
        p.fix_calc("1")
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")

    def test_on_github_the_old_branch_and_its_pull_request_are_closed_and_the_ticket_gets_a_new_one(self):
        p, b, github = self.claimed(pair=True)
        self.github_bin = github.bin
        p.queue_reviews(said("secret", "A live token."))
        held = p.rail("advance", "1", expect=3, env_extra=self.scan())
        self.assertEqual(held["reason"]["code"], "SECRET_FOUND")
        self.assertEqual(held["action"]["facts"]["wait"], {"kind": "grant", "accept": "rail accept 1", "label": "rail:go"})
        github.label(1, "rail:go")   # the person answers on the pull request
        again = p.rail("next", "1")
        self.assertEqual((again["state"], again["reason"]["code"]), ("implementing", "IMPLEMENT"))
        self.assertEqual(github.pr(1)["state"], "closed")
        self.assertEqual(on_remote(github), ["1-fix-add--2"])
        self.assertEqual((github.pr(2)["state"], github.pr(2)["head"]), ("open", "1-fix-add--2"))
        # Another clone reads the new branch.
        (row,) = b.rail("status")["tickets"]
        self.assertEqual(row["state"], "implementing")

    def test_where_the_old_branch_cannot_be_deleted_the_engine_reads_the_new_one(self):
        p, b, github = self.claimed(pair=True)
        self.github_bin = github.bin
        p.queue_reviews(said("secret", "A live token."))
        p.rail("advance", "1", expect=3, env_extra=self.scan(), cloud=True)
        p.rail("accept", "1", cloud=True)
        again = p.rail("next", "1", cloud=True)
        self.assertEqual(again["reason"]["code"], "IMPLEMENT")
        self.assertEqual(on_remote(github), ["1-fix-add", "1-fix-add--2"])  # a cloud session's git deletes no branch
        there = b.rail("next", "1", session="session-b")
        self.assertEqual((there["reason"]["code"], there["action"]["facts"]["branch"]), ("IMPLEMENT", "1-fix-add--2"))
        self.assertEqual(there["action"]["facts"]["restarted"]["branch"], "1-fix-add")
