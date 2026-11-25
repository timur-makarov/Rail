"""The contract: add, accept, amend, ticket lint and the tier a contract takes."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RAIL, RailTest, check_shape, ticket  # noqa: E402

GRILLED = """
## Grilling
- Channel: Slack DM
- Agent: claude-opus-5-5
- Mood: cheerful
- Started: yesterday
- Drafts shown: two

| # | Topic | Recommended | Answer | Taken |
|---|---|---|---|---|
| Q1 | colour | Only src/calc.py | Yes | accepted |
| Q2 | scope | Only src/calc.py | Yes | maybe |
| Q3 | done | A check that add(2, 3) is 5 | Yes | answered |
| Q4 | behaviour | Raise on None |  | rejected |
| Q5 | scope | too few cells |
"""


def read(path):
    with open(path) as f:
        return f.read()


def events(p, branch="1-fix-add", nn="1"):
    return [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]


def rail_with_stdin(p, text, *args):
    """`rail ARGS --json` with `text` on stdin, in the environment Fixture.rail gives a command."""
    env = {k: v for k, v in os.environ.items() if k not in ("RAIL_TICKET", "GITHUB_ACTIONS", "CLAUDE_CODE_REMOTE_SESSION_ID")}
    env.update(RAIL_CLOUD="0", CLAUDE_CODE_SESSION_ID="session-a", RAIL_FAKE_REVIEWS=p.reviews, RAIL_FAKE_LOG=p.review_log)
    result = subprocess.run([sys.executable, RAIL, *args, "--json"], cwd=p.root, input=text, capture_output=True,
                            text=True, env=env)
    answer = json.loads(result.stdout)
    check_shape(answer)
    return result.returncode, answer


class Add(RailTest):
    def test_a_ticket_can_come_in_on_stdin(self):
        p = self.fixture()
        code, added = rail_with_stdin(p, ticket(), "add", "-")
        self.assertEqual((code, added["ticket"], added["state"], added["branch"]), (0, "1", "accepted", "1-fix-add"))
        self.assertIn('title = "Fix add"', p.git("show", "1-fix-add:.rail/tickets/1.md"))

    def test_a_branch_already_named_like_the_new_ticket_is_left_alone_and_the_add_is_refused(self):
        p = self.fixture()
        p.git("branch", "1-fix-add")
        mine = p.git("rev-parse", "1-fix-add")
        refused = p.add(ticket(), expect=2)
        self.assertEqual(refused["reason"]["message"], "branch 1-fix-add already exists")
        self.assertEqual(p.git("rev-parse", "1-fix-add"), mine)
        self.assertEqual(p.add(ticket(title="Fix add properly"))["ticket"], "2")  # the ID is never reused

    def test_with_the_remote_out_of_reach_add_takes_no_id_and_makes_no_branch(self):
        a, b = self.remote_pair()
        remote = os.path.join(self.tmp, "remote.git")
        os.rename(remote, remote + ".away")
        refused = a.add(ticket(), expect=2)
        self.assertEqual(refused["reason"]["code"], "UNAVAILABLE")
        self.assertIn("can't reach the remote to take a ticket ID", refused["reason"]["message"])
        self.assertEqual(a.git("branch", "--list", "1-*"), "")
        os.rename(remote + ".away", remote)
        self.assertEqual(a.add(ticket())["ticket"], "1")


class Lint(RailTest):
    """Each ticket lint rule, as a writer meets it at rail add."""

    def refused(self, text):
        p = self.fixture()
        failed = p.add(text, expect=3)
        self.assertEqual(failed["reason"]["code"], "TICKET_LINT")
        self.assertEqual(p.git("branch", "--list", "[0-9]*"), "")
        return failed["action"]["brief"]

    def test_an_empty_title_is_refused(self):
        self.assertIn("- title is empty", self.refused(ticket(title="  ")))

    def test_an_absolute_scope_path_is_refused(self):
        self.assertIn("- scope_paths must be relative to the repository root", self.refused(ticket(scope=("/src/**",))))

    def test_an_empty_scope_is_refused(self):
        self.assertIn("- scope_paths must list at least one path glob", self.refused(ticket(scope=())))

    def test_a_ticket_without_why_is_refused(self):
        self.assertIn("- '## Why' is missing or empty", self.refused(ticket().replace("add subtracts instead of adding.", "")))

    def test_a_ticket_without_a_done_contract_is_refused(self):
        text = ticket().split("## Done Contract")[0]
        self.assertIn("- '## Done Contract' is missing", self.refused(text))

    def test_a_done_contract_with_no_check_line_is_refused(self):
        text = ticket().split("- Check:")[0] + "- add returns the sum\n"
        self.assertIn("- the Done Contract needs at least one '- Check: `command`' line", self.refused(text))

    def test_a_field_of_the_wrong_type_is_refused(self):
        brief = self.refused(ticket(front=('after = "1"', "caused_by = 3")))
        self.assertIn("- 'after' must be a list", brief)
        self.assertIn("- 'caused_by' must be a string", brief)

    def test_front_matter_that_does_not_parse_is_refused(self):
        brief = self.refused(ticket(front=("rollback = drop the column",)))
        self.assertIn("- the front matter is not valid TOML", brief)

    def test_a_ticket_with_no_front_matter_or_no_closing_line_is_refused(self):
        p = self.fixture()
        for text, needle in ((ticket().split("+++", 2)[2], "the ticket must start with TOML front matter"),
                             (ticket().replace("+++\n\n## Why", "\n## Why"), "the front matter has no closing '+++' line")):
            with self.subTest(needle):
                self.assertIn(needle, p.add(text, expect=3)["action"]["brief"])

    def test_a_ticket_that_comes_after_itself_is_refused_at_amend(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace('tier = "AUTO"', 'tier = "AUTO"\nafter = ["1"]'),
                base=p.worktree("1"))
        failed = p.rail("amend", "1", expect=3)
        self.assertEqual(failed["reason"]["code"], "TICKET_LINT")
        self.assertIn("- a ticket can't come after itself", failed["action"]["brief"])

    def test_an_id_changed_by_hand_fails_ticket_lint_at_ship(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace('id = "1"', 'id = "7"'), base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["detail"]),
                         ("ticket-lint", "id is '7', expected '1'"))

    def test_each_line_of_a_grilling_record_that_does_not_add_up_is_named(self):
        brief = self.refused(ticket(body=GRILLED))
        for needle in ("Grilling: unknown line 'Mood'; the lines are Channel, Agent, Person, Started, Confirmed,"
                       " Drafts shown",
                       "Grilling: Channel is one lowercase word, such as slack, not 'Slack DM'",
                       "Grilling: Started is a UTC time like 2026-11-16T09:12:00Z",
                       "Grilling: Drafts shown is a number",
                       "Grilling Q1: topic must be one of scope, done, behaviour, tier, out-of-scope, other, not 'colour'",
                       "Grilling Q2: Taken must be one of accepted, edited, rejected, answered, not 'maybe'",
                       "Grilling Q3: a question with a recommendation was accepted, edited or rejected",
                       "Grilling Q4: the Answer is empty",
                       "Grilling: a question row needs 5 cells (#, Topic, Recommended, Answer, Taken), got 3"):
            self.assertIn(needle, brief)


class Accept(RailTest):
    def test_a_request_with_no_contract_yet_cannot_be_accepted(self):
        p = self.fixture()
        request = os.path.join(self.tmp, "request.md")
        with open(request, "w") as f:
            f.write("add(2, 3) gives -1.\n")
        p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix add", "--brief", request)
        refused = p.rail("accept", "1", expect=2)
        self.assertEqual(refused["reason"]["code"], "TICKET_LINT")
        self.assertIn("ticket 1 fails ticket lint: tier must be one of AUTO, PERSON", refused["reason"]["message"])
        self.assertEqual(p.rail("status")["tickets"][0]["state"], "new")


class Amend(RailTest):
    def claimed(self, **kw):
        p = self.fixture(**kw)
        p.add(ticket())
        p.rail("next")
        return p, os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")

    def test_an_amend_with_nothing_changed_is_refused(self):
        p, _ = self.claimed()
        refused = p.rail("amend", "1", expect=2)
        self.assertEqual(refused["reason"]["code"], "NOTHING_TO_AMEND")
        self.assertEqual(refused["reason"]["message"],
                         "the contract of ticket 1 matches the accepted one; there is nothing to amend")

    def test_an_amend_that_fails_lint_changes_nothing(self):
        p, path = self.claimed()
        p.write(".rail/tickets/1.md", read(path).replace("add subtracts instead of adding.", ""), base=p.worktree("1"))
        failed = p.rail("amend", "1", expect=3)
        self.assertEqual((failed["state"], failed["owner"], failed["reason"]["code"]), ("implementing", "agent", "TICKET_LINT"))
        self.assertIn("Fix the ticket, then amend again:\n- '## Why' is missing or empty", failed["action"]["brief"])
        self.assertEqual([e for e in events(p) if e["event"] == "amended"], [])

    def test_a_dropped_or_merged_ticket_is_not_amended(self):
        p, _ = self.claimed()
        p.fix_calc("1")
        p.rail("advance", "1")
        p.rail("advance", "1")
        merged = p.rail("amend", "1", "--file", p.path(".rail", "tickets", "1.md"), expect=2)
        self.assertEqual(merged["reason"]["message"], "ticket 1 is merged; follow-up work is a new ticket with caused_by")
        p.add(ticket(title="Other", scope=("api/**",)))
        p.rail("drop", "2")
        dropped = p.rail("amend", "2", "--file", p.path(".rail", "tickets", "1.md"), expect=2)
        self.assertEqual(dropped["reason"]["message"], "ticket 2 is dropped; follow-up work is a new ticket with caused_by")

    def test_a_ticket_with_no_worktree_here_is_amended_with_a_file(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        refused = p.rail("amend", "1", expect=2)
        self.assertEqual(refused["reason"]["message"], "edit the ticket in its worktree, or pass the new ticket with --file")
        changed = os.path.join(self.tmp, "1.md")
        with open(changed, "w") as f:
            f.write(ticket(tier="PERSON", scope=("src/**", "api/**")))
        amended = p.rail("amend", "1", "--file", changed)
        self.assertEqual((amended["state"], amended["reason"]["code"]), ("new", "APPROVE_CONTRACT"))
        self.assertIn('scope_paths = ["src/**", "api/**"]', p.git("show", "1-fix-add:.rail/tickets/1.md"))

    def test_an_amend_whose_scope_reaches_a_person_path_makes_the_ticket_person(self):
        p, path = self.claimed()
        p.write(".rail/tickets/1.md", read(path).replace('["src/**"]', '["src/**", ".github/workflows/**"]'),
                base=p.worktree("1"))
        amended = p.rail("amend", "1")
        self.assertEqual((amended["tier"], amended["state"], amended["owner"]), ("PERSON", "implementing", "agent"))
        record = [e for e in events(p) if e["event"] == "amended"][-1]
        self.assertEqual((record["changed"], record["added_paths"], record["needs_approval"]),
                         (["scope"], [".github/workflows/**"], False))
        self.assertEqual((events(p)[-1]["event"], events(p)[-1]["tier"]), ("accepted", "PERSON"))
        self.assertIn('tier = "PERSON"', read(path))
        self.assertIn('tier = "PERSON"', p.git("show", "1-fix-add:.rail/tickets/1.md"))

    def test_an_amend_keeps_its_reason_and_shows_it_to_the_person_who_approves(self):
        p = self.fixture()
        p.add(ticket(tier="PERSON"))
        p.rail("accept", "1")
        p.rail("next")
        path = os.path.join(p.worktree("1"), ".rail", "tickets", "1.md")
        p.write(".rail/tickets/1.md", read(path).replace("== 5", "== 5 and calc.add(0, 0) == 0"), base=p.worktree("1"))
        amended = p.rail("amend", "1", "the check ran the wrong file")
        self.assertEqual(amended["reason"]["code"], "APPROVE_AMEND")
        self.assertIn("The agent's reason: the check ran the wrong file", amended["action"]["brief"])
        self.assertEqual([e for e in events(p) if e["event"] == "amended"][-1]["reason"], "the check ran the wrong file")


class Drop(RailTest):
    def test_a_drop_records_who_dropped_it_and_why(self):
        p = self.fixture()
        p.add(ticket())
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next", "--ticket", "1")
        p.rail("next", "--ticket", "2")
        # Uncommitted work keeps each worktree, and with it the branch that holds the journal.
        p.fix_calc("1")
        p.write("api/handlers.py", "def handle():\n    return 201\n", base=p.worktree("2"))
        dropped = p.rail("drop", "1", "--reason", "superseded by ticket 2", "--by", "person")
        self.assertEqual((dropped["state"], dropped["leftovers"][0]["kind"]), ("dropped", "worktree"))
        last = events(p)[-1]
        self.assertEqual((last["event"], last["by"], last["reason"]), ("dropped", "person", "superseded by ticket 2"))
        p.rail("drop", "2")
        last = events(p, "2-add-a-status-code", "2")[-1]
        self.assertEqual((last["event"], last["by"], last["reason"]), ("dropped", "agent", ""))

    def test_a_merged_ticket_cannot_be_dropped(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        p.rail("advance", "1")
        refused = p.rail("drop", "1", "--reason", "too late", expect=2)
        self.assertEqual((refused["reason"]["code"], refused["reason"]["message"]),
                         ("MERGED", "ticket 1 is merged; follow-up work is a new ticket with caused_by"))
        self.assertEqual(p.rail("status")["tickets"][0]["state"], "merged")


class ReviewOutput(RailTest):
    def claimed_and_fixed(self, config=CONFIG):
        p = self.fixture(config=config)
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        return p

    def test_output_that_breaks_the_schema_is_rejected_with_the_reason(self):
        # An invalid run is started once more at once, and two in a row wait for a person, who continues.
        p = self.claimed_and_fixed()

        def finding(**kw):
            return {"severity": "advisory", "file": "src/calc.py", "claim": "x", **kw}

        cases = [({"findings": []}, "the output is not a review/v1 object with summary and findings"),
                 ({"summary": "x", "findings": [finding(severity="urgent")]}, "finding 1: severity 'urgent'"),
                 ({"summary": "x", "findings": [finding(line=99)]}, "finding 1: line 99 isn't inside src/calc.py"),
                 ({"summary": "x", "findings": [finding(evidence={"command": "pytest"})]},
                  "finding 1: evidence needs command and output"),
                 ({"summary": "x", "findings": [finding(author="me")]}, "finding 1 doesn't match the schema")]
        for output, reason in cases:
            with self.subTest(reason):
                p.queue_reviews(output, output)
                failed = p.rail("advance", "1", expect=3)
                details = [s["detail"] for s in failed["steps"] if s["step"] == "review"]
                self.assertEqual((failed["state"], failed["owner"], failed["reason"]["code"], details),
                                 ("reviewing", "human", "STUCK_REVIEW", [f"invalid output: {reason}"] * 2))
                p.rail("accept", "1")
        self.assertNotIn("1-review.json", p.git("ls-tree", "-r", "--name-only", "1-fix-add", ".rail/journal"))  # no run kept

    def test_a_review_given_as_text_in_the_result_field_is_read(self):
        p = self.claimed_and_fixed()
        said = 'Done reading.\n```json\n{"summary": "Clean.", "findings": []}\n```'
        p.queue_reviews({"raw": json.dumps({"type": "result", "result": said})})
        shipped = p.rail("advance", "1")
        self.assertEqual(shipped["state"], "merge-ready")
        doc = json.loads(p.git("show", "1-fix-add:.rail/journal/1-review.json"))
        self.assertEqual(doc["runs"][-1]["summary"], "Clean.")
