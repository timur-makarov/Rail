"""Tools: what the work reaches outside the repository is declared, listed in the briefs, and checked before a claim."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

TOOLS = '''
[tools.payments]
use = "The payment service in test mode: create customers and charges in checks"
env = ["RAIL_TEST_PAY_KEY"]
probe = 'test "$RAIL_TEST_PAY_KEY" = sk_test_1'

[tools.errors]
use = "The error tracker: read an issue's stack trace"
env = ["RAIL_TEST_ERRORS_TOKEN"]
review = true
'''
SET = {"RAIL_TEST_PAY_KEY": "sk_test_1", "RAIL_TEST_ERRORS_TOKEN": "t"}
CLEAN = {"summary": "Clean.", "findings": []}


class Briefs(RailTest):
    def test_the_worker_is_told_every_tool_and_the_reviewer_only_those_declared_for_review(self):
        p = self.fixture(config=CONFIG + TOOLS)
        p.add(ticket())
        brief = p.rail("next", env_extra=SET)["action"]["brief"]
        self.assertIn("Tools this project declares, for what the work reaches outside the repository:\n"
                      "- payments: The payment service in test mode: create customers and charges in checks"
                      " (reads RAIL_TEST_PAY_KEY)\n"
                      "- errors: The error tracker: read an issue's stack trace (reads RAIL_TEST_ERRORS_TOKEN)\n", brief)
        self.assertNotIn("sk_test_1", brief)  # a name, never a value
        p.fix_calc("1")
        p.queue_reviews(CLEAN)
        p.rail("advance", "1", env_extra=SET)
        review = p.briefs()[-1]["brief"]
        self.assertIn("## Tools\nTools this project declares for a reviewer, to read with and never to change anything:\n"
                      "- errors: The error tracker: read an issue's stack trace (reads RAIL_TEST_ERRORS_TOKEN)\n", review)
        self.assertNotIn("payments", review)

    def test_a_project_with_no_tool_says_nothing_of_tools(self):
        p = self.fixture()
        p.add(ticket())
        self.assertNotIn("Tools", p.rail("next")["action"]["brief"])


class Missing(RailTest):
    def test_a_missing_name_stops_before_the_claim_and_counts_no_attempt(self):
        p = self.fixture(config=CONFIG + TOOLS)
        p.add(ticket())
        waiting = p.rail("next", env_extra={"RAIL_TEST_ERRORS_TOKEN": "t"})
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("human", "TOOL_MISSING"))
        self.assertEqual([(w["ticket"], w["needs"]) for w in waiting["waits"]], [("1", "TOOL_MISSING")])
        self.assertEqual(p.rail("status")["tickets"][0]["state"], "accepted")
        brief = waiting["action"]["brief"]
        self.assertIn("Ticket 1 can't be claimed on this machine: a tool the project declares has no credential here"
                      " (payments needs RAIL_TEST_PAY_KEY).", brief)
        self.assertIn("Set it in the shell that starts the agent, or in the project's .env", brief)
        self.assertIn("no attempt is counted", brief)
        self.assertFalse(os.path.exists(p.worktree("1")))
        # A name the project's .env gives a value counts as set: the value is never read out.
        p.write(".env", "export RAIL_TEST_PAY_KEY=sk_test_1\nOTHER=\n")
        claimed = p.rail("next", env_extra={"RAIL_TEST_ERRORS_TOKEN": "t"})
        self.assertEqual((claimed["reason"]["code"], claimed["state"]), ("IMPLEMENT", "implementing"))
        self.assertNotIn("sk_test_1", claimed["action"]["brief"])
        # A ticket already under way goes on without the name: only a claim is stopped.
        os.remove(p.path(".env"))
        self.assertEqual(p.rail("next", "--ticket", "1")["reason"]["code"], "IMPLEMENT")

    def test_in_a_cloud_session_one_issue_a_tool_tells_the_person_and_closes_when_the_name_is_there(self):
        a, b, github = self.github_pair(config=CONFIG + TOOLS)
        a.add(ticket())
        a.add(ticket(title="Other", scope=("api/**",), check="grep 201 api/handlers.py"))
        waiting = a.rail("next", cloud=True)
        self.assertEqual(waiting["reason"]["code"], "TOOL_MISSING")
        self.assertIn("Tickets 1, 2 can't be claimed on this machine: a tool the project declares has no credential"
                      " here (payments needs RAIL_TEST_PAY_KEY; errors needs RAIL_TEST_ERRORS_TOKEN). Set it in this"
                      " cloud environment's settings, as an environment variable", waiting["action"]["brief"])
        a.rail("next", cloud=True)
        issues = [i for i in github.read().get("issues", []) if i["state"] == "open"]
        self.assertEqual(sorted(i["title"] for i in issues),  # one a tool, however many tickets wait and runs pass
                         ["Rail needs RAIL_TEST_ERRORS_TOKEN for the tool errors",
                          "Rail needs RAIL_TEST_PAY_KEY for the tool payments"])
        self.assertEqual({tuple(i["labels"]) for i in issues}, {("rail:needs-you",)})
        self.assertIn("No ticket is claimed there until it is.", issues[0]["body"])
        # No pull request of a waiting ticket is labelled for it: the tool's issue is the person's one item.
        self.assertEqual([x for p in github.read().get("pulls", []) for x in p["labels"]], [])
        claimed = a.rail("next", cloud=True, env_extra=SET)
        self.assertEqual(claimed["state"], "implementing")
        self.assertEqual([i["state"] for i in github.read().get("issues", [])], ["closed", "closed"])

    def test_on_a_persons_own_machine_no_issue_is_opened(self):
        a, b, github = self.github_pair(config=CONFIG + TOOLS)
        a.add(ticket())
        self.assertEqual(a.rail("next")["reason"]["code"], "TOOL_MISSING")
        self.assertEqual(github.read().get("issues", []), [])


class Doctor(RailTest):
    def test_doctor_shows_each_tool_its_names_and_its_probe(self):
        p = self.fixture(config=CONFIG + TOOLS)
        found = {s["step"]: s for s in p.rail("doctor", expect=None, env_extra={"RAIL_TEST_PAY_KEY": "wrong"})["steps"]}
        self.assertEqual(found["tool payments"]["result"], "fail")
        self.assertIn("RAIL_TEST_PAY_KEY set; its probe failed (exit 1)", found["tool payments"]["detail"])
        self.assertNotIn("wrong", found["tool payments"]["detail"])
        self.assertEqual(found["tool errors"]["result"], "fail")
        self.assertIn("RAIL_TEST_ERRORS_TOKEN not set here, so its probe was not run. Set it in the shell",
                      found["tool errors"]["detail"])
        found = {s["step"]: s for s in p.rail("doctor", expect=None, env_extra=SET)["steps"]}
        self.assertEqual((found["tool payments"]["result"], found["tool payments"]["detail"]),
                         ("pass", "RAIL_TEST_PAY_KEY set; its probe passed"))
        self.assertEqual((found["tool errors"]["result"], found["tool errors"]["detail"]),
                         ("pass", "RAIL_TEST_ERRORS_TOKEN set; no probe"))


class Config(RailTest):
    def test_a_declaration_needs_a_use_line_and_takes_names_never_values(self):
        for n, (old, new, said) in enumerate((
                ('use = "The error tracker: read an issue\'s stack trace"\n', "", "config: tools.errors needs use"),
                ('env = ["RAIL_TEST_PAY_KEY"]', 'env = ["sk_test_51Habc/def"]',
                 "config: tools.payments.env lists the names of environment variables, never their values"),
                ("review = true", 'review = "yes"', "config: tools.errors.review must be bool"),
                ("review = true", "reviews = true", "config: unknown key 'tools.errors.reviews'"))):
            self.assertIn(old, TOOLS)
            p = self.fixture(name=f"p{n}", config=CONFIG + TOOLS.replace(old, new))
            message = p.rail("status", expect=None)["reason"]["message"]
            self.assertIn(said, message)
            self.assertNotIn("sk_test_51Habc", message)  # a value pasted where a name belongs is not echoed


class Init(RailTest):
    def test_the_init_task_names_what_looks_like_a_tool(self):
        p = self.fixture(init=False, files={
            ".mcp.json": '{"mcpServers": {"tracker": {"command": "npx"}, "db": {"command": "uvx"}}}',
            ".env.example": "# keys\nPAY_KEY=\nexport MAIL_TOKEN=changeme\n# OPTIONAL_KEY=\nlower=1\n",
            ".github/workflows/ci.yml": "env:\n  A: ${{ secrets.DEPLOY_TOKEN }}\n  B: ${{ secrets.GITHUB_TOKEN }}\n"})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "first")
        p.rail("init")
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("[tools.NAME] in .rail/config.toml: one table for each thing the work reaches outside the"
                      " repository", " ".join(brief.split()))
        self.assertIn("rail init found what may be tools (MCP servers in .mcp.json: db, tracker; names in .env.example:"
                      " MAIL_TOKEN, OPTIONAL_KEY, PAY_KEY; secrets the workflows in .github/workflows read:"
                      " DEPLOY_TOKEN): declare the ones the work uses.", " ".join(brief.split()))
        self.assertNotIn("changeme", brief)
