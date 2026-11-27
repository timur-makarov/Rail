"""Tools: what the work reaches outside the repository is declared, listed in the briefs, and checked before a claim."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, FAKE_WORKER, RailTest, ticket

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


def journal(p, nn="1", branch="1-fix-add"):
    return [json.loads(row) for row in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]


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
        self.assertEqual((waiting["owner"], waiting["reason"]["code"]), ("person", "TOOL_MISSING"))
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


CI_TOOL = TOOLS.replace("probe = 'test", "ci = true\nprobe = 'test")
PASSED = "          RAIL_TEST_PAY_KEY: ${{ secrets.RAIL_TEST_PAY_KEY }}\n"


class Secrets(RailTest):
    """A ticket branch runs its own copy of every workflow: only the key of a tool declared ci = true may be in reach."""

    def doctor(self, p, **kw):
        return {s["step"]: s for s in p.rail("doctor", expect=None, env_extra=SET, **kw)["steps"]}

    def test_a_run_a_pull_request_starts_is_given_only_the_keys_declared_for_ci(self):
        p = self.fixture(config=CONFIG + CI_TOOL)
        workflow = open(p.path(".github/workflows/rail.yml")).read()
        self.assertNotIn("pull request secrets", self.doctor(self.fixture(name="plain")))  # nothing to say
        # The seed's workflow names an example in a comment, which is no reference; the declared key is not passed yet.
        found = self.doctor(p)["pull request secrets"]
        self.assertEqual((found["result"], found["detail"]), (
            "fail", ".github/workflows/rail.yml doesn't pass RAIL_TEST_PAY_KEY, declared ci = true, so a check that"
                    " needs it fails in CI: add `RAIL_TEST_PAY_KEY: ${{ secrets.RAIL_TEST_PAY_KEY }}` to the env of the"
                    " step that runs rail ci"))
        p.write(".github/workflows/rail.yml", workflow + PASSED)
        found = self.doctor(p)["pull request secrets"]
        self.assertEqual((found["result"], found["detail"]), (
            "pass", "a run a pull request starts is given only keys declared ci = true: RAIL_TEST_PAY_KEY"))
        # A key no tool declares for CI, however it is spelled.
        for line, said in (
                ("          DEPLOY: ${{ secrets.DEPLOY_KEY }}\n", "gives a run a pull request starts DEPLOY_KEY, which no"
                                                                  " tool declares with ci = true"),
                ("          DEPLOY: ${{ secrets['DEPLOY_KEY'] }}\n", "gives a run a pull request starts DEPLOY_KEY"),
                ("          ERRORS: ${{ secrets.RAIL_TEST_ERRORS_TOKEN }}\n",  # declared, but not for CI
                 "gives a run a pull request starts RAIL_TEST_ERRORS_TOKEN"),
                ("          ALL: ${{ toJSON(secrets) }}\n", "passes every secret to a run a pull request starts"),
                ("          ONE: ${{ secrets[matrix.key] }}\n", "passes every secret to a run a pull request starts")):
            p.write(".github/workflows/rail.yml", workflow + PASSED + line)
            found = self.doctor(p)["pull request secrets"]
            self.assertEqual(found["result"], "fail", line)
            self.assertIn(".github/workflows/rail.yml " + said, found["detail"])
            self.assertIn("A ticket branch runs its own copy of every workflow", found["detail"])
        p.write(".github/workflows/rail.yml", workflow + PASSED)
        # Another workflow a pull request starts counts; one only a push to the base branch starts does not.
        p.write(".github/workflows/deploy.yml", "on:\n  push:\n    branches: [main]\njobs:\n  d:\n    env:\n"
                                                "      K: ${{ secrets.PROD_KEY }}\n")
        self.assertEqual(self.doctor(p)["pull request secrets"]["result"], "pass")
        for trigger in ("on: [push, pull_request]\n", "on: pull_request_target\n", "'on':\n  pull_request:\n    paths: [src/**]\n",
                        "on:\n- pull_request\n"):
            p.write(".github/workflows/lint.yml", trigger + "jobs:\n  d:\n    secrets: inherit\n")
            found = self.doctor(p)["pull request secrets"]
            self.assertEqual(found["result"], "fail", trigger)
            self.assertIn(".github/workflows/lint.yml passes every secret", found["detail"])

    def test_every_repository_secret_is_in_a_ticket_branchs_reach(self):
        a, b, github = self.github_pair(config=CONFIG + CI_TOOL)
        self.assertNotIn("repository secrets", self.doctor(a))  # the repository holds none
        github.update(lambda s: s.update(secrets=["RAIL_TEST_PAY_KEY"]))
        found = self.doctor(a)["repository secrets"]
        self.assertEqual((found["result"], found["detail"]), (
            "pass", "every repository secret is the key of a tool declared ci = true: RAIL_TEST_PAY_KEY"))
        github.update(lambda s: s.update(secrets=["RAIL_TEST_PAY_KEY", "PROD_KEY"], org_secrets=["ORG_TOKEN"]))
        found = self.doctor(a)["repository secrets"]
        self.assertEqual(found["result"], "fail")
        self.assertIn("ORG_TOKEN, PROD_KEY: in a ticket branch's reach, and no tool declares it with ci = true. A branch"
                      " can add a workflow of its own that reads any repository or organization secret.", found["detail"])
        self.assertIn("Move any other secret to a GitHub environment that only main may deploy to", found["detail"])
        # A token that may not list secrets: the check says it did not run, and what holds anyway.
        github.update(lambda s: s.update(secrets_status=403))
        found = self.doctor(a)["repository secrets"]
        self.assertEqual(found["status"], "unavailable")
        self.assertIn("gh can't list this repository's Actions secrets here (403), so they weren't checked.", found["detail"])

    def test_an_environment_that_holds_a_secret_lets_only_the_base_branch_deploy(self):
        a, b, github = self.github_pair(config=CONFIG + CI_TOOL)
        github.update(lambda s: s.update(environments=[
            {"name": "open", "secrets": ["PROD_KEY"]},
            {"name": "wide", "secrets": ["PROD_KEY", "RAIL_TEST_PAY_KEY"], "branches": ["main", "release/*",
                                                                                      {"name": "v*", "type": "tag"}]},
            {"name": "base only", "secrets": ["PROD_KEY"], "branches": ["main"]},
            {"name": "protected", "secrets": ["PROD_KEY"], "branches": "protected"},
            {"name": "preview", "secrets": ["RAIL_TEST_PAY_KEY"]},  # a test key: any branch may read it
            {"name": "empty"}]))
        found = self.doctor(a)
        self.assertEqual({k: v["result"] for k, v in found.items() if k.startswith("environment ")}, {
            "environment open": "fail", "environment wide": "fail", "environment base only": "pass",
            "environment protected": "pass"})
        self.assertIn("it holds PROD_KEY and any branch may deploy to it, so a ticket branch can read them",
                      found["environment open"]["detail"])
        self.assertIn("it holds PROD_KEY and branch release/*, tag v* may deploy to it", found["environment wide"]["detail"])
        self.assertIn("allow main alone", found["environment wide"]["detail"])
        self.assertEqual(found["environment base only"]["detail"], "only main may deploy to it")
        self.assertEqual(found["environment protected"]["detail"], "only protected branches may deploy to it")

    def test_a_key_marked_for_ci_needs_its_name(self):
        p = self.fixture(config=CONFIG + '[tools.search]\nuse = "Search the docs"\nci = true\n')
        self.assertIn("config: tools.search.ci marks the tool's key as one a pull request's run may be given, so the"
                      " tool needs env", p.rail("status", expect=None)["reason"]["message"])

    def test_a_failed_rail_ci_names_a_declared_key_the_job_was_not_given(self):
        p = self.fixture(config=CONFIG + CI_TOOL)
        from railtest import CHECK_ADD
        p.add(ticket(check=f'test -n "$RAIL_TEST_PAY_KEY" && {CHECK_ADD}'))  # a check that needs the key
        p.rail("next", env_extra=SET)
        p.fix_calc("1")
        p.queue_reviews(CLEAN)
        p.rail("advance", "1", env_extra=SET)
        ci = os.path.join(self.tmp, "ci")  # what the workflow does: a clone, the pull request's head checked out
        subprocess.run(["git", "clone", "--quiet", p.root, ci], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", "1-fix-add").strip()], cwd=ci, check=True)
        failed = p.rail("ci", cwd=ci, expect=3, env_extra={"RAIL_BRANCH": "1-fix-add", "RAIL_TEST_PAY_KEY": ""})
        self.assertIn("Failed at 'checks'", failed["action"]["brief"])
        self.assertIn("\nNot set in this job: RAIL_TEST_PAY_KEY (tool payments). A check that needs it fails here.",
                      failed["action"]["brief"])
        passed = p.rail("ci", cwd=ci, env_extra=dict(SET, RAIL_BRANCH="1-fix-add"))
        self.assertEqual(passed["action"]["brief"], "Every check passed.")


class Down(RailTest):
    """A check that fails while a declared tool is out of reach may have failed for that alone."""
    PROBED = ("""
[tools.payments]
use = "The payment service in test mode"
env = ["RAIL_TEST_PAY_KEY"]
probe = 'test "$RAIL_TEST_PAY_KEY" = sk_test_1'
""")

    def test_a_failure_with_a_tool_out_of_reach_counts_no_attempt_and_twice_in_a_row_waits_for_a_person(self):
        from railtest import CHECK_ADD
        up, down = {"RAIL_TEST_PAY_KEY": "sk_test_1"}, {"RAIL_TEST_PAY_KEY": "revoked"}
        p = self.fixture(config=CONFIG + self.PROBED)
        p.add(ticket(check=f'test "$RAIL_TEST_PAY_KEY" = sk_test_1 && {CHECK_ADD}'))  # a check that uses the tool
        p.rail("next", env_extra=up)
        p.fix_calc("1")
        first = p.rail("advance", "1", expect=3, env_extra=down)
        self.assertEqual(first["reason"]["code"], "STEP_FAILED")
        self.assertIn("A tool the project declares is out of reach (payments: its probe failed (exit 1)). So the failure"
                      " may be the machine's and not the change's: no attempt was counted. Run it once more.",
                      first["action"]["brief"])
        recorded = [e for e in journal(p) if e["event"] == "step" and e["result"] == "fail"][-1]
        self.assertEqual((recorded["step"], recorded["counted"], recorded["tools_down"]),
                         ("checks", False, {"payments": "its probe failed (exit 1)"}))
        later = p.rail("next", "--ticket", "1", env_extra=down)["action"]["brief"]  # a fresh worker is told the same
        self.assertIn("A tool the project declares was out of reach (payments: its probe failed (exit 1)).", later)
        self.assertNotIn("## Tried", later)  # nothing was tried at the work
        second = p.rail("advance", "1", expect=3, env_extra=down)
        self.assertEqual((second["owner"], second["reason"]["code"]), ("person", "TOOL_DOWN"))
        self.assertEqual(second["action"]["brief"],
                         "Ticket 1 can't get past 'checks' on this machine: it failed 2 times in a row while a tool the"
                         " project declares was out of reach (payments: its probe failed (exit 1)). No failure of these"
                         " counted as an attempt, since it may not be the change's. A person checks that the tool answers"
                         " and that its credential is valid on this machine, then continues the ticket: rail accept 1.")
        self.assertEqual([e["event"] for e in journal(p) if e["event"] in ("consulted", "dropped")], [])
        p.rail("accept", "1")
        p.queue_reviews(CLEAN)
        self.assertEqual(p.rail("advance", "1", env_extra=up)["state"], "merge-ready")

    def test_a_failure_with_every_tool_in_reach_is_the_changes_own(self):
        up = {"RAIL_TEST_PAY_KEY": "sk_test_1"}
        p = self.fixture(config=CONFIG + self.PROBED)
        p.add(ticket())
        p.rail("next", env_extra=up)
        p.write("src/calc.py", "def add(a, b):\n    return a * b\n", base=p.worktree("1"))  # still wrong
        failed = p.rail("advance", "1", expect=3, env_extra=up)
        self.assertNotIn("out of reach", failed["action"]["brief"])
        recorded = [e for e in journal(p) if e["event"] == "step" and e["result"] == "fail"][-1]
        self.assertNotIn("counted", recorded)
        # A failure that counts between two that don't: they are not in a row.
        p.rail("advance", "1", expect=3, env_extra={"RAIL_TEST_PAY_KEY": "revoked"})
        p.write("src/calc.py", "def add(a, b):\n    return a - b - 0\n", base=p.worktree("1"))
        p.rail("advance", "1", expect=3, env_extra=up)
        again = p.rail("advance", "1", expect=3, env_extra={"RAIL_TEST_PAY_KEY": "revoked"})
        self.assertNotEqual(again["reason"]["code"], "TOOL_DOWN")


class Used(RailTest):
    """A worker run records the declared tools it reached, and rail stats counts them."""
    CONFIG = CONFIG + Down.PROBED + f'''
[tools.errors]
use = "The error tracker, an MCP server: read an issue's stack trace"

[tools.deployer]
use = "The deploy CLI, signed in on the machine"

[tools.unused]
use = "Declared, and no run reaches it"
env = ["RAIL_TEST_UNUSED_KEY"]

[worker]
command = "python3 {FAKE_WORKER}"
'''

    def test_a_tool_a_run_used_is_on_its_worked_event_and_stats_counts_it(self):
        from railtest import CHECK_ADD
        up = {"RAIL_TEST_PAY_KEY": "sk_test_1", "RAIL_TEST_UNUSED_KEY": "u"}
        down = dict(up, RAIL_TEST_PAY_KEY="revoked")
        p = self.fixture(config=self.CONFIG)
        p.add(ticket(check=f'test "$RAIL_TEST_PAY_KEY" = sk_test_1 && {CHECK_ADD}'))
        p.rail("next", env_extra=up)
        p.queue_work(
            {"write": {"src/calc.py": "def add(a, b):\n    return a + b\n"}, "calls": [
                ["Bash", {"command": 'curl -sf --oauth2-bearer "$RAIL_TEST_PAY_KEY" https://api.example.com/v1/balance'},
                 "ok", "{}"],                                                      # a variable the tool declares
                ["mcp__errors__get_issue", {"query": "PAY-12"}, "ok", "a stack trace"],  # the MCP server of that name
                ["Bash", {"command": "cd infra && uv run deployer status"}, "ok", "idle"],   # the program
                ["Bash", {"command": "echo $RAIL_TEST_UNUSED_KEY_OLD unused deployers"}, "ok", ""],  # none of them
                ["mcp__notdeclared__read", {"path": "x"}, "ok", ""]]},
            {"calls": [["mcp__errors__get_issue", {"query": "PAY-13"}, "ok", "another"]]},
            {"calls": [["Read", {"file_path": "src/calc.py"}, "ok", "def add"]]})
        p.rail("work", "1", env_extra=up)
        p.rail("work", "1", env_extra=up)
        p.rail("work", "1", env_extra=up)
        worked = [e for e in journal(p) if e["event"] == "worked"]
        self.assertEqual([e.get("tools") for e in worked], [["deployer", "errors", "payments"], ["errors"], None])
        self.assertNotIn("sk_test_1", json.dumps(worked))  # names only

        p.rail("advance", "1", expect=3, env_extra=down)  # the check fails with the payment service out of reach
        p.queue_reviews(CLEAN)
        p.rail("advance", "1", env_extra=up)
        self.assertEqual(p.rail("advance", "1", env_extra=up)["state"], "merged")
        stats = p.rail("stats", env_extra=up)["stats"]
        self.assertEqual(stats["tools"], {"deployer": {"tickets": 1, "runs": 1, "probe_failed": 0},
                                          "errors": {"tickets": 1, "runs": 2, "probe_failed": 0},
                                          "payments": {"tickets": 1, "runs": 1, "probe_failed": 1}})
        text = p.rail("stats", raw=True, env_extra=up).stdout
        self.assertIn("TOOLS     tickets  worker runs  probe failed\n"
                      "deployer        1            1             0\n"
                      "errors          1            2             0\n"
                      "payments        1            1             1\n", text)

    def test_a_project_with_no_declared_tool_records_none(self):
        p = self.fixture(config=CONFIG + f'\n[worker]\ncommand = "python3 {FAKE_WORKER}"\n')
        p.add(ticket())
        p.rail("next")
        p.queue_work({"write": {"src/calc.py": "def add(a, b):\n    return a + b\n"},
                      "calls": [["mcp__errors__get_issue", {"query": "PAY-12"}, "ok", ""]]})
        p.rail("work", "1")
        self.assertNotIn("tools", [e for e in journal(p) if e["event"] == "worked"][0])
        p.queue_reviews(CLEAN)
        p.rail("advance", "1")
        p.rail("advance", "1")
        self.assertEqual(p.rail("stats")["stats"]["tools"], {})
        self.assertNotIn("TOOLS", p.rail("stats", raw=True).stdout)


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
