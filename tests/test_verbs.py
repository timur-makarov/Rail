"""Verbs and output no other file drives: init's labels, status notes, packs, text output, doctor, intake, sweep,
stats."""

import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import ARCHITECTURE, CONFIG, Fixture, RailTest, ticket  # noqa: E402

LABELS = ["rail", "rail:go", "rail:needs-you", "rail:hold"]


def read(path):
    with open(path) as f:
        return f.read()


def steps(answer):
    return {s["step"]: s for s in answer["steps"]}


def notes(p, session="session-a"):
    return {row["ticket"]: row["note"] for row in p.rail("status", session=session)["tickets"]}


class Init(RailTest):
    def test_init_in_a_clone_of_a_github_repository_creates_the_labels_once(self):
        a, b, github = self.github_pair(init=False)
        done = a.rail("init")
        self.assertEqual(steps(done)["labels"], {"step": "labels", "status": "ran", "result": "pass",
                                                 "detail": "created rail, rail:go, rail:needs-you, rail:hold"})
        self.assertEqual(sorted(github.read()["labels"]), sorted(LABELS))
        again = a.rail("init")
        self.assertEqual(steps(again)["labels"]["detail"], "all three exist")
        self.assertEqual(sorted(github.read()["labels"]), sorted(LABELS))

    def test_settings_that_are_not_json_are_left_alone_and_doctor_says_the_hooks_are_missing(self):
        p = Fixture(os.path.join(self.tmp, "broken"), init=False, files={".claude/settings.json": '{"hooks": {\n'})
        done = p.rail("init")
        self.assertEqual(steps(done)[".claude/settings.json"],
                         {"step": ".claude/settings.json", "status": "not_run",
                          "detail": "not valid JSON, so left alone; merge seed/settings.json by hand"})
        self.assertEqual(read(p.path(".claude", "settings.json")), '{"hooks": {\n')
        self.assertTrue(os.path.exists(p.path(".rail", "config.toml")))  # the rest of init went on
        self.assertEqual(steps(p.rail("doctor", expect=3))["hooks"]["result"], "fail")


class Status(RailTest):
    def test_status_notes_what_each_waiting_ticket_waits_for(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON", title="Change the API", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.add(ticket())
        p.add(ticket(title="Fix add again", front=('after = ["2"]',)))
        p.add(ticket(title="Add subtract"))
        p.rail("next", "--ticket", "2")
        found = notes(p)
        self.assertEqual(found["1"], "waiting: approve contract")
        self.assertEqual(found["2"], "")
        self.assertEqual(found["3"], "Ticket 3 waits for ticket 2 to merge.")
        self.assertEqual(found["4"], "Ticket 4 can't be claimed while ticket 2 changes the same paths.")
        text = p.rail("status", raw=True).stdout
        self.assertIn("waiting: approve contract", text)

    def test_work_a_quiet_session_left_is_noted_for_the_next_one_to_resume(self):
        p = self.fixture(config=CONFIG + "\n[claim]\nstale_minutes = 0\n")
        p.add(ticket())
        p.rail("next", session="a")
        self.assertEqual(notes(p, session="b")["1"], "left by an ended session: rail next resumes it")

    def test_a_claim_with_no_worktree_in_this_clone_says_how_to_make_one(self):
        a, b = self.remote_pair()
        a.add(ticket())
        a.rail("next", session="a")
        self.assertEqual(notes(b, session="a")["1"], "no worktree here: rail next --ticket 1 makes one")

    def test_a_claimed_ticket_with_no_event_for_days_is_stale(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        # The ticket was claimed four days ago and nothing has happened since: its journal says so.
        then = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 4 * 86400))
        journal = os.path.join(p.worktree("1"), ".rail", "journal", "1-events.jsonl")
        rows = [dict(json.loads(l), at=then) for l in read(journal).splitlines()]
        p.write(".rail/journal/1-events.jsonl", "".join(json.dumps(r) + "\n" for r in rows), base=p.worktree("1"))
        p.git("commit", "--quiet", "-am", "1: four days ago", cwd=p.worktree("1"))
        row = p.rail("status")["tickets"][0]
        self.assertEqual((row["state"], row["last_event"], row["note"]),
                         ("implementing", "4d", "STALE: no event for 4 days"))


class Packs(RailTest):
    def test_rail_name_runs_the_packs_command_from_the_project_root(self):
        p = self.fixture()
        p.write(".rail/packs/hello/bin/hello", '#!/bin/sh\necho "hello $* from $RAIL_ROOT"\nexit 4\n')
        os.chmod(p.path(".rail", "packs", "hello", "bin", "hello"), 0o755)
        ran = p.rail("hello", "world", cwd=p.path("src"), raw=True, expect=4)
        self.assertEqual(ran.stdout, f"hello world from {p.root}\n")
        self.assertEqual(p.rail("goodbye", expect=2)["reason"]["code"], "USAGE")  # no such verb, and no such pack


class Text(RailTest):
    """What a person reads without --json."""

    def test_an_error_is_one_line(self):
        p = self.fixture()
        result = p.rail("advance", "99", raw=True, expect=2)
        self.assertEqual(result.stdout, "rail: no ticket '99'\n")

    def test_context_prints_the_areas_and_the_directories(self):
        p = self.fixture()
        text = p.rail("context", raw=True).stdout
        self.assertTrue(text.startswith("## Areas\n- calc (src/**): the calculator\n- api (api/**): public HTTP handlers\n"
                                        "\n## Directories\n"), text)
        self.assertIn("src/ (1 files)", text)
        os.remove(p.path("ARCHITECTURE.md"))
        p.git("commit", "--quiet", "-am", "no map")
        self.assertIn("## Areas\n(no ARCHITECTURE.md yet)\n", p.rail("context", raw=True).stdout)

    def test_steps_the_brief_and_leftovers_are_printed_in_order(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        text = p.rail("advance", "1", raw=True, expect=3).stdout
        lines = text.splitlines()
        self.assertEqual(lines[0], "ticket 1 · implementing · owner agent · STEP_FAILED")
        self.assertEqual(lines[1], "cwd: .claude/worktrees/1")
        self.assertIn("  ticket-lint: ran, pass", lines)
        self.assertIn("  rules: not_run", lines)
        self.assertIn("  verify: ran, pass (exit 0)", lines)
        self.assertIn("AssertionError", text)
        p.fix_calc("1")
        dropped = p.rail("drop", "1", "--reason", "not needed", raw=True).stdout
        self.assertIn("\n\nleftover: worktree .claude/worktrees/1 (uncommitted changes (1 files); left for you)", dropped)

    STOP = "If a person asked you for this work, stop here and tell them the ticket number: another session builds it."

    def test_add_ends_with_the_line_that_tells_an_intake_session_to_stop(self):
        p = self.fixture()
        path = p.path("..", "draft.md")
        with open(path, "w") as f:
            f.write(ticket())
        text = p.rail("add", path, raw=True).stdout
        self.assertTrue(text.startswith("ticket 1 · accepted · owner agent · CLAIM\n"), text)
        self.assertTrue(text.endswith("\n\nrail next --ticket 1\n\n" + self.STOP + "\n"), text)
        self.assertEqual(p.add(ticket(title="Fix sub"))["note"], self.STOP)  # --json carries it too
        lint = p.add("no front matter", expect=None)
        self.assertEqual(lint["reason"]["code"], "TICKET_LINT")
        self.assertNotIn("note", lint)  # only a filed ticket gets it


class Doctor(RailTest):
    def doctor(self, p):
        return steps(p.rail("doctor", expect=None))

    def test_a_guard_hook_on_the_wrong_matcher_is_reported(self):
        p = self.fixture()
        settings = json.loads(read(p.path(".claude", "settings.json")))
        settings["hooks"]["PreToolUse"][0]["matcher"] = "Edit"
        p.write(".claude/settings.json", json.dumps(settings))
        found = self.doctor(p)["guard rules"]
        self.assertEqual(found["result"], "fail")
        self.assertIn("the guard hook's Bash matcher", found["detail"])

    def test_claude_md_must_import_agents_md(self):
        p = self.fixture()
        self.assertNotIn("CLAUDE.md", self.doctor(p))
        p.write("CLAUDE.md", "# Claude\n\nBe brief.\n")
        self.assertEqual(self.doctor(p)["CLAUDE.md"]["detail"],
                         "CLAUDE.md stops Claude Code reading AGENTS.md: add a line @AGENTS.md")
        p.write("CLAUDE.md", "# Claude\n\n@AGENTS.md\n")
        self.assertEqual((self.doctor(p)["CLAUDE.md"]["result"], self.doctor(p)["CLAUDE.md"]["detail"]),
                         ("pass", "imports AGENTS.md"))

    def test_a_claude_md_in_a_folder_above_the_project_is_reported(self):
        p = self.fixture()
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w") as f:
            f.write("# Everything in this folder\n")
        found = self.doctor(p)["parent CLAUDE.md"]
        self.assertEqual((found["result"], found["detail"]),
                         ("fail", f"{self.tmp}/CLAUDE.md stops Claude Code reading AGENTS.md here"))

    def test_a_remote_that_is_not_on_github_is_noted(self):
        a, b = self.remote_pair()
        self.assertEqual(self.doctor(a)["forge"], {"step": "forge", "status": "unavailable",
                                                   "detail": "the remote isn't on GitHub, and only GitHub is supported"})

    def test_gh_that_cannot_read_the_repository_is_reported(self):
        a, b, github = self.github_pair()
        github.update(lambda s: s.update(repo="acme/elsewhere"))
        found = steps(a.rail("doctor", expect=3))
        self.assertEqual(found["gh"]["result"], "fail")
        self.assertIn("gh can't read acme/app", found["gh"]["detail"])
        self.assertIn("Log in with gh auth login", found["gh"]["detail"])
        self.assertNotIn("labels", found)  # nothing else on GitHub is checked


class Intake(RailTest):
    def test_intake_without_a_source_or_its_arguments_is_a_usage_error(self):
        p = self.fixture()
        self.assertEqual(p.rail("intake", "jira", expect=2)["reason"]["message"],
                         "unknown intake source 'jira'; use github, or --external-id with --title and --brief")
        self.assertEqual(p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix add", expect=2)["reason"]["message"],
                         "rail intake needs github, or --external-id, --title and --brief")
        unreachable = p.rail("intake", "github", expect=2)
        self.assertEqual(unreachable["reason"]["code"], "UNAVAILABLE")
        self.assertEqual(p.rail("status")["tickets"], [])

    def test_a_whole_ticket_that_fails_lint_comes_in_as_a_request_that_says_why(self):
        p = self.fixture()
        brief = os.path.join(self.tmp, "brief.md")
        with open(brief, "w") as f:
            f.write(ticket(front=("rollback = drop the column",)))
        taken = p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix add", "--brief", brief)
        self.assertEqual(taken["created"], ["1"])
        stub = p.rail("next")
        self.assertEqual((stub["ticket"], stub["reason"]["code"]), ("1", "TICKET_LINT"))
        self.assertIn("The issue held a whole ticket, and Rail took it only as a request: the front matter is not valid"
                      " TOML", stub["action"]["brief"])
        self.assertIn("> ## Done Contract", p.git("show", "1-proj-7-fix-add:.rail/tickets/1.md"))  # quoted, not taken


class Sweep(RailTest):
    # Counted over the whole tree, Rail's own files included: this config names the word too.
    RULE = '\n[[rules]]\nid = "no-new-suppressions"\nforbid = ["# noqa"]\nallow = ["vendor/**", ".rail/**"]\n'

    def test_rail_sweep_takes_up_its_open_ticket_and_counts_each_rules_lines_in_the_tree(self):
        p = self.fixture(config=CONFIG + self.RULE, files={
            "src/old.py": "import os  # noqa\nimport sys  # noqa\n", "vendor/lib.py": "import re  # noqa\n",
            "ARCHITECTURE.md": ARCHITECTURE + "| vendor | vendor/** | code we copy in |\n"})
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        swept = p.rail("sweep")
        # Rule counts are a fact for the summary, not a finding: the sweep has nothing to file.
        self.assertEqual((swept["ticket"], swept["reason"]["code"]), ("2", "SWEEP_EMPTY"))
        summary = read(os.path.join(p.worktree("2"), ".rail", "journal", "2-summary.md"))
        self.assertIn("- rule no-new-suppressions: 2 lines in the tree", summary)  # vendor/ is allowed
        again = p.rail("sweep")
        self.assertEqual((again["ticket"], again["reason"]["code"], again["action"]["command"]),
                         ("2", "SWEEP_EMPTY", "rail advance 2"))
        self.assertNotIn("harvest", [s["step"] for s in again["steps"]])  # it ran once
        self.assertEqual([r["ticket"] for r in p.rail("status")["tickets"]], ["1", "2"])


class Stats(RailTest):
    @staticmethod
    def later(seconds):
        """The merge's commit date, as if it landed `seconds` from now."""
        return {"GIT_COMMITTER_DATE": f"@{int(time.time()) + seconds} +0000"}

    def test_findings_the_reviewer_parked_and_long_spans_are_shown(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        parked = {"severity": "parked", "file": "src/calc.py", "claim": "calc has no subtract."}
        p.queue_reviews({"summary": "One for later.", "findings": [parked]})
        self.assertEqual(p.rail("advance", "1")["state"], "merge-ready")
        p.rail("advance", "1", env_extra=self.later(3 * 3600))
        p.add(ticket(title="Add a status code", tier="PERSON", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("accept", "2")
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("2"))
        self.assertEqual(p.rail("advance", "2")["reason"]["code"], "MERGE_BY_PERSON")
        p.rail("accept", "2")
        self.assertEqual(p.rail("advance", "2", env_extra=self.later(2 * 86400))["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["review"]["parked"], 1)
        self.assertIn("Parked by the reviewer: 1.", stats["text"])
        self.assertRegex(stats["text"], r"\nmedian claim to merge +3h00m +2d0h\n")

    def test_with_every_change_inside_skip_paths_no_review_ran(self):
        p = self.fixture(config=CONFIG.replace("[review]", '[review]\nskip_paths = ["docs/**"]'),
                         files={"docs/guide.md": "# Guide\n",
                                "ARCHITECTURE.md": ARCHITECTURE + "| docs | docs/** | the guide |\n"})
        p.add(ticket(title="Explain sum", scope=("docs/**",), check="grep -q sum docs/guide.md"))
        p.rail("next")
        p.write("docs/guide.md", "# Guide\nsum\n", base=p.worktree("1"))
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        stats = p.rail("stats")
        self.assertEqual(stats["stats"]["review"]["roles"], {})
        self.assertIn("\n\nNo review ran.", stats["text"])
        self.assertNotIn("REVIEW", stats["text"])


class GoneFolder(RailTest):
    def test_a_shell_whose_folder_was_removed_gets_a_plain_error(self):
        # A merge removes the ticket's worktree; `rail advance 1; rail next` from inside it runs next with no folder.
        p = self.fixture()
        gone = os.path.join(p.root, "gone")
        os.mkdir(gone)
        local = os.path.join(p.root, ".rail", "bin", "rail")  # the project's own launcher, as a hook or a path call
        script = f'cd "{gone}" && rmdir "{gone}" && "{sys.executable}" "{local}" next --json'
        result = subprocess.run(["sh", "-c", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(json.loads(result.stdout)["reason"]["code"], "NO_FOLDER")
