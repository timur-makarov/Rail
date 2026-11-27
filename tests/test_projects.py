"""Projects within a repository: Rail works them out from the tracked manifests of the tree in front of it, and a
ticket sets up and checks only the projects its change reaches (rail docs languages).

The fixture is a shop: a Python service (`api`), a TypeScript app (`web`) and a library both use (`lib`, a member
of the uv workspace and of the pnpm workspace). `uv` and `pnpm` are stand-ins that write down where they ran and
with what, so no toolchain is needed."""

import json
import os
import stat
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import FAKE, RailTest, engine
from test_review import clean
from test_triage import said

CONFIG = f"""\
[commands]
verify = "echo whole >> \\"$SHOP_LOG\\""
timeout_secs = 60

[review]
command = "python3 {FAKE}"

[consult]
command = "python3 {FAKE} --consult"
"""

SHOP = {
    ".gitignore": ".claude/worktrees/\n__pycache__/\nnode_modules/\n",
    "README.md": "# Shop\n",
    "pyproject.toml": '[tool.uv.workspace]\nmembers = ["api", "lib"]\n',
    "uv.lock": "version = 1\n",
    "api/pyproject.toml": '[project]\nname = "shop-api"\nversion = "0.1.0"\ndependencies = ["shop-lib"]\n\n'
                          "[tool.uv.sources]\nshop-lib = { workspace = true }\n",
    "api/api.py": "def handle():\n    return 200\n",
    "lib/pyproject.toml": '[project]\nname = "shop-lib"\nversion = "0.1.0"\n',
    "lib/shop.py": "def price(n):\n    return n * 2\n",
    "package.json": '{"name": "shop", "private": true}\n',
    "pnpm-workspace.yaml": "packages:\n  - web\n  - lib\n",
    "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
    "web/package.json": '{"name": "shop-web", "dependencies": {"shop-lib-js": "workspace:*"}}\n',
    "web/tsconfig.json": "{}\n",
    "web/index.ts": "export const total = 1\n",
    "lib/package.json": '{"name": "shop-lib-js"}\n',
    "lib/shop.ts": "export const price = (n: number) => n * 2\n",
}

# A stand-in for a package manager or an audit tool: one line for each call, `TOOL FOLDER: ARGUMENTS`, the folder
# from the checkout's root. A test run fails where a file of the folder says BROKEN.
TOOL = """\
#!/bin/sh
top=$(git rev-parse --show-toplevel)
here=$(pwd -P)
case "$here" in "$top") at=. ;; *) at=${here#"$top"/} ;; esac
echo "$(basename "$0") $at: $*" >> "$SHOP_LOG"
case "$(basename "$0")" in uv) kind='*.py' ;; *) kind='*.ts' ;; esac
case " $* " in *" pytest "*|*" test "*) ! grep -rqs --include="$kind" BROKEN . || exit 1 ;; esac
exit 0
"""

ALL = ["lib-python", "api", "lib-typescript", "web"]


def card(title, scope, tier="AUTO", front=()):
    scopes = ", ".join(f'"{s}"' for s in scope)
    return "\n".join(["+++", f'title = "{title}"', f'tier = "{tier}"', f"scope_paths = [{scopes}]", *front, "+++", "",
                      "## Why", "The shop needs it.", "", "## Done Contract", "- Check: `test -f README.md`", ""])


def ran(answer, family):
    """The projects a step of this family ran for, in order."""
    return [s["step"].split(":", 1)[1] for s in answer["steps"]
            if s["step"].startswith(family + ":") and s["status"] == "ran"]


def triage_briefs(p):
    return [b["brief"] for b in p.briefs() if b["brief"].startswith("# One question")]


def events(p, nn, branch, kind=None):
    rows = [json.loads(l) for l in p.git("show", f"{branch}:.rail/journal/{nn}-events.jsonl").splitlines()]
    return [e for e in rows if kind is None or e["event"] == kind]


class ShopTest(RailTest):
    def shop(self, config=CONFIG, files=None):
        tree = os.path.join(self.tmp, "tree")
        for path, text in {**SHOP, **(files or {})}.items():
            os.makedirs(os.path.dirname(os.path.join(tree, path)), exist_ok=True)
            with open(os.path.join(tree, path), "w") as f:
                f.write(text)
        tools = os.path.join(self.tmp, "tools")
        os.makedirs(tools)
        for name in ("uv", "pnpm", "pip-audit"):
            with open(os.path.join(tools, name), "w") as f:
                f.write(TOOL)
            os.chmod(os.path.join(tools, name), stat.S_IRWXU)
        self.log = os.path.join(self.tmp, "shop.log")
        self.env = {"PATH": tools + os.pathsep + os.environ["PATH"], "SHOP_LOG": self.log}
        p = self.fixture(tree=tree, config=config)
        plain = p.rail
        p.rail = lambda *args, env_extra=None, **kw: plain(*args, env_extra={**self.env, **(env_extra or {})}, **kw)
        return p

    def calls(self, clear=True):
        """What the stand-ins and the whole repository's verify wrote since the last look."""
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            lines = f.read().splitlines()
        if clear:
            os.unlink(self.log)
        return lines

    def claim(self, p, title, scope, **kw):
        nn = p.add(card(title, scope, **kw))["ticket"]
        return nn, p.rail("next", "--ticket", nn)

    def ci(self, p, branch):
        """What the workflow does: a clone, the pull request's head checked out, `rail ci`."""
        ci = os.path.join(self.tmp, "ci-" + branch)
        subprocess.run(["git", "clone", "--quiet", p.root, ci], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", branch).strip()], cwd=ci, check=True)
        return p.rail("ci", cwd=ci, env_extra={"RAIL_BRANCH": branch})


class Reach(ShopTest):
    def test_a_change_in_the_app_sets_up_and_checks_the_app_only_and_ci_runs_the_same_set(self):
        p = self.shop()
        nn, claimed = self.claim(p, "Raise the total", ["web/**"])
        self.assertEqual(ran(claimed, "setup"), ["web"])
        self.assertEqual(self.calls(), ["pnpm web: install --frozen-lockfile --ignore-scripts --filter shop-web..."])
        (reached,) = p.rail("context", nn)["projects"]  # what the ticket's scope reaches, and the commands
        self.assertEqual((reached["name"], reached["paths"], reached["uses"], reached["setup"]),
                         ("web", ["web/**"], ["lib-typescript"],
                          "pnpm install --frozen-lockfile --ignore-scripts --filter shop-web..."))
        self.assertIn("pnpm --filter shop-web test", reached["verify"])
        p.write("web/index.ts", "export const total = 2\n", base=p.worktree(nn))
        p.queue_reviews(clean())
        shipped = p.rail("advance", nn)
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertEqual((ran(shipped, "setup"), ran(shipped, "verify")), ([], ["web"]))  # the claim set it up
        self.assertEqual(self.calls(), ["pnpm web: --filter shop-web exec oxlint --deny-warnings",
                                        "pnpm web: --filter shop-web exec tsc --noEmit",
                                        "pnpm web: --filter shop-web test", "whole"])
        self.assertEqual(p.git("diff", "--name-only", "main", "1-raise-the-total", "--", ".rail/config.toml"), "")

        checked = self.ci(p, "1-raise-the-total")
        self.assertEqual(checked["reason"]["code"], "CI_PASS")
        self.assertEqual((ran(checked, "setup"), ran(checked, "verify")), (["web"], ["web"]))
        self.assertEqual(self.calls()[-1], "whole")

    def test_a_change_in_the_library_runs_the_librarys_checks_and_both_users(self):
        p = self.shop()
        nn, claimed = self.claim(p, "Double the price", ["lib/**"])
        self.assertEqual(ran(claimed, "setup"), ALL)  # a project before the projects that use it
        self.assertEqual(self.calls(), [
            "uv lib: sync --locked --package shop-lib", "uv api: sync --locked --package shop-api",
            "pnpm lib: install --frozen-lockfile --ignore-scripts --filter shop-lib-js...",
            "pnpm web: install --frozen-lockfile --ignore-scripts --filter shop-web..."])
        p.write("lib/shop.py", "def price(n):\n    return n * 3\n", base=p.worktree(nn))
        p.queue_reviews(clean())
        shipped = p.rail("advance", nn)
        self.assertEqual(ran(shipped, "verify"), ALL)
        called = self.calls()
        self.assertIn("uv api: run pytest -q", called)
        self.assertIn("pnpm lib: --filter shop-lib-js test", called)
        self.assertNotIn("pnpm lib: --filter shop-lib-js exec tsc --noEmit", called)  # the library has no tsconfig.json
        self.assertEqual(ran(self.ci(p, "1-double-the-price"), "verify"), ALL)

    def test_a_root_file_reaches_every_project_and_a_workspaces_lockfile_its_members(self):
        p = self.shop()
        nn, claimed = self.claim(p, "Say what the shop is", ["README.md"])
        self.assertEqual(ran(claimed, "setup"), ALL)
        p.write("README.md", "# Shop\n\nA shop.\n", base=p.worktree(nn))
        p.queue_reviews(clean())
        self.assertEqual(ran(p.rail("advance", nn), "verify"), ALL)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

        nn, claimed = self.claim(p, "Lock the service again", ["uv.lock"])
        self.assertEqual(ran(claimed, "setup"), ["lib-python", "api"])
        p.write("uv.lock", "version = 1\nrevision = 2\n", base=p.worktree(nn))
        self.calls()
        p.queue_reviews(clean())
        self.assertEqual(ran(p.rail("advance", nn), "verify"), ["lib-python", "api"])
        called = self.calls()  # the lockfile changed, so each member's audit runs
        for line in ("uv lib: export --locked --no-emit-project --format requirements-txt",
                     "pip-audit lib: --disable-pip --no-deps -r /dev/stdin", "pip-audit api: --disable-pip --no-deps -r /dev/stdin"):
            self.assertIn(line, called)
        self.assertEqual([line for line in called if line.startswith("pnpm")], [])

    def test_a_failed_check_names_its_project_and_the_later_projects_do_not_run(self):
        p = self.shop()
        nn, _ = self.claim(p, "Double the price", ["lib/**"])
        p.write("lib/shop.ts", "export const price = (n: number) => n * 3  // BROKEN\n", base=p.worktree(nn))
        failed = p.rail("advance", nn, expect=3)
        self.assertEqual(ran(failed, "verify"), ["lib-python", "api", "lib-typescript"])
        (step,) = [s for s in failed["steps"] if s["step"] == "verify:lib-typescript"]
        self.assertEqual(step["result"], "fail")
        self.assertIn("Ship of ticket 1 failed at 'verify:lib-typescript'.", failed["action"]["brief"])
        self.assertEqual(p.rail("next", "--ticket", nn)["reason"]["code"], "STEP_FAILED")
        p.write("lib/shop.ts", "export const price = (n: number) => n * 3\n", base=p.worktree(nn))
        p.queue_reviews(clean())
        self.assertEqual(ran(p.rail("advance", nn), "verify"), ALL)

    def test_a_ticket_that_adds_a_folder_with_a_manifest_is_set_up_and_checked_as_a_project_in_its_own_ship(self):
        p = self.shop()
        nn, claimed = self.claim(p, "Add the jobs", ["jobs/**"])
        self.assertEqual(ran(claimed, "setup"), [])  # nothing is there yet
        work = p.worktree(nn)
        p.write("jobs/pyproject.toml", '[project]\nname = "shop-jobs"\nversion = "0.1.0"\n', base=work)
        p.write("jobs/uv.lock", "version = 1\n", base=work)
        p.write("jobs/sweep.py", "def sweep():\n    return 0\n", base=work)
        p.queue_reviews(clean())
        shipped = p.rail("advance", nn)
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertEqual((ran(shipped, "setup"), ran(shipped, "verify")), (["jobs"], ["jobs"]))
        called = self.calls()
        self.assertEqual(called[0], "uv jobs: sync --locked")
        self.assertIn("uv jobs: run pytest -q", called)
        self.assertEqual(p.git("diff", "--name-only", "main", "1-add-the-jobs", "--", ".rail/config.toml"), "")
        self.assertEqual(events(p, nn, "1-add-the-jobs", "question"), [])  # the folder is inside a project

    def test_rail_stats_splits_the_merged_tickets_by_project(self):
        p = self.shop()
        for n in range(1, 6):
            nn, _ = self.claim(p, f"Raise the total to {n + 1}", ["web/**"])
            p.write("web/index.ts", f"export const total = {n + 1}\n", base=p.worktree(nn))
            p.queue_reviews(clean())
            p.rail("advance", nn)
            self.assertEqual(p.rail("advance", nn)["state"], "merged")
        out = p.rail("stats")["stats"]["outcomes"]
        self.assertEqual(({name: row["merged"] for name, row in out["by_project"].items()},
                          {name: row["merged"] for name, row in out["by_profile"].items()}),
                         ({"web": 5}, {"typescript": 5}))
        self.assertIn("BY PROJECT", p.rail("stats", raw=True).stdout)


class Entries(ShopTest):
    def test_an_entry_replaces_a_projects_verify_and_uses_makes_the_users_checks_run(self):
        entry = ('\n[[projects]]\nname = "web"\nverify = "echo web-own >> \\"$SHOP_LOG\\""\nuses = ["api"]\n'
                 '\n[[projects]]\nname = "docs"\npaths = ["docs/**"]\nverify = "echo docs-own >> \\"$SHOP_LOG\\""\n')
        p = self.shop(config=CONFIG + entry, files={"docs/guide.md": "# Guide\n"})
        nn, claimed = self.claim(p, "Answer 201", ["api/**"])
        self.assertEqual(ran(claimed, "setup"), ["api", "web"])
        p.write("api/api.py", "def handle():\n    return 201\n", base=p.worktree(nn))
        self.calls()
        p.queue_reviews(clean())
        shipped = p.rail("advance", nn)
        self.assertEqual(ran(shipped, "verify"), ["api", "web"])
        self.assertEqual(self.calls()[-2:], ["web-own", "whole"])  # the entry's command, at the project's folder
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

        nn, claimed = self.claim(p, "Write the guide", ["docs/**"])
        self.assertEqual(ran(claimed, "setup"), [])  # a declared project with no setup
        p.write("docs/guide.md", "# Guide\n\nBuy things.\n", base=p.worktree(nn))
        p.queue_reviews(clean())
        self.assertEqual(ran(p.rail("advance", nn), "verify"), ["docs"])
        self.assertEqual(self.calls(), ["docs-own", "whole"])

    def test_an_entry_that_uses_no_project_a_cycle_and_a_declared_project_with_no_paths_are_refused(self):
        p = self.shop()
        cases = {
            '[[projects]]\nname = "web"\nuses = ["backend"]\n':
                "config: the [[projects]] entry 'web' uses 'backend', which is no project. The projects: api,"
                " lib-python, lib-typescript",
            '[[projects]]\nname = "web"\nuses = ["api"]\n\n[[projects]]\nname = "lib-python"\nuses = ["web"]\n':
                "config: the projects' `uses` go in a circle: api -> lib-python -> web -> api",
            '[[projects]]\nname = "infra"\nverify = "terraform validate"\n':
                "config: the [[projects]] entry 'infra' names no project a tracked manifest marks, so it declares one"
                " and needs `paths`",
        }
        for text, message in cases.items():
            with self.subTest(message):
                p.write(".rail/config.toml", CONFIG + "\n" + text)
                self.assertIn(message, p.rail("status", expect=2)["reason"]["message"])


TF = 'resource "aws_s3_bucket" "orders" {\n  bucket = "shop-orders"\n}\n'


class Uncovered(ShopTest):
    def infra(self, p, answer):
        """A ticket adds a Terraform folder, and its ship asks about it once."""
        nn, _ = self.claim(p, "Add the bucket", ["infra/**"])
        p.write("infra/main.tf", TF, base=p.worktree(nn))
        p.queue_reviews(answer, clean())
        return nn, p.rail("advance", nn)

    def test_a_terraform_folder_raises_one_question_and_needs_checks_files_a_person_ticket(self):
        p = self.shop()
        nn, shipped = self.infra(p, said("needs-checks", evidence="Terraform that declares the orders bucket."))
        self.assertEqual((shipped["state"], shipped["tier"]), ("merge-ready", "AUTO"))  # the change is not held for it
        self.assertEqual(ran(shipped, "verify"), ALL)  # a file inside no project reaches every project
        self.assertIn({"step": "intake", "status": "ran", "result": "pass", "detail": "ticket 2 covers infra"},
                      shipped["steps"])
        (asked,) = events(p, nn, "1-add-the-bucket", "question")
        self.assertEqual((asked["type"], asked["key"], asked["fact"]["folder"], asked["fact"]["types"]),
                         ("uncovered", "infra: .tf", "infra", [".tf"]))
        (brief,) = triage_briefs(p)
        for text in ("# One question about ticket 1 (Q1, uncovered)",
                     "1 tracked file under infra/ (.tf) is inside no project, so no check reads it.",
                     "## The files under infra/\n- infra/main.tf",
                     '## The first lines of infra/main.tf\n```\nresource "aws_s3_bucket" "orders" {',
                     "- `nothing-to-check`: docs, assets, data or examples", "- `needs-checks`: code or configuration",
                     "## The projects the repository has\n- api: api/**\n- lib-python: lib/**"):
            self.assertIn(text, brief)
        (review,) = [b["brief"] for b in p.briefs() if not b["brief"].startswith("# One question")]
        self.assertIn("## Files of this change that no check read\nThese files are inside no project of the repository,"
                      " so no command checked them at ship.", review)
        self.assertIn("list it in `kinds`.\n- infra/main.tf\n", review)
        filed = p.git("show", "2-coverage-infra-cover-infra-with-checks:.rail/tickets/2.md")
        for text in ('tier = "PERSON"', 'scope_paths = [".rail/config.toml"]', 'external_id = "coverage:infra"',
                     'person_reason = "controls: .rail/config.toml holds the checks every ticket runs"',
                     "> The files under infra/ (.tf) are inside no project, so no check reads them. A run that looked"
                     " at them judged that they need checks: Terraform that declares the orders bucket.",
                     '`paths` ("infra/**")', "infrastructure code is `infrastructure`"):
            self.assertIn(text, filed)
        self.assertEqual(json.loads(p.git("show", "1-add-the-bucket:.rail/journal/1-coverage.json")), {"infra": {
            "types": [".tf"], "answer": "needs-checks", "holds": "Terraform that declares the orders bucket.",
            "covered_by": "2"}})
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

        # The folder has its ticket, so the next ships ask nothing, whatever is added to it.
        nn, _ = self.claim(p, "Add the queue", ["infra/**"])
        p.write("infra/queue.hcl", 'queue = "orders"\n', base=p.worktree(nn))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", nn)["state"], "merge-ready")
        self.assertEqual(len(triage_briefs(p)), 1)

    def test_nothing_to_check_is_recorded_and_the_folder_is_asked_about_again_only_for_a_new_file_type(self):
        p = self.shop()
        nn, shipped = self.infra(p, said("nothing-to-check", evidence="An example a guide points at; nothing applies it."))
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertEqual([t["ticket"] for t in p.rail("status")["tickets"]], ["1"])  # no ticket is filed
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        self.assertEqual(json.loads(p.git("show", "main:.rail/journal/1-coverage.json")), {"infra": {
            "types": [".tf"], "answer": "nothing-to-check", "holds": "An example a guide points at; nothing applies it."}})

        nn, _ = self.claim(p, "Name the bucket", ["infra/**"])
        p.write("infra/names.tf", 'locals {\n  orders = "shop-orders"\n}\n', base=p.worktree(nn))
        p.queue_reviews(clean())
        self.assertEqual(p.rail("advance", nn)["state"], "merge-ready")  # a file of a type the answer saw
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        self.assertEqual(len(triage_briefs(p)), 1)

        nn, _ = self.claim(p, "Add the plan script", ["infra/**"])
        p.write("infra/plan.sh", "#!/bin/sh\nterraform plan\n", base=p.worktree(nn))
        p.queue_reviews(said("needs-checks", evidence="A shell script that runs terraform plan."), clean())
        self.assertEqual(p.rail("advance", nn)["state"], "merge-ready")
        (asked,) = events(p, nn, "3-add-the-plan-script", "question")
        self.assertEqual((asked["key"], asked["fact"]["types"], asked["fact"]["files"]), ("infra: .sh .tf", [".sh", ".tf"], 3))
        self.assertEqual([(t["ticket"], t["title"], t["tier"]) for t in p.rail("status")["tickets"]][-1],
                         ("4", "Cover infra with checks", "PERSON"))

    def test_a_base_commit_no_ticket_made_raises_the_question_at_the_next_rail_next(self):
        p = self.shop()
        self.assertEqual(p.rail("next")["reason"]["code"], "NO_WORK")  # every file is inside a project
        p.write("deploy/values.yaml", "replicas: 2\n")
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "Add the deploy values")
        asking = p.rail("next")
        self.assertEqual((asking["reason"]["code"], asking["action"]["command"]), ("ASK_COVERAGE", "rail advance 1"))
        (row,) = p.rail("status")["tickets"]
        self.assertEqual((row["tier"], row["state"]), ("AUTO", "implementing"))
        p.queue_reviews(said("needs-checks", evidence="Helm values a deploy reads."), clean())
        shipped = p.rail("advance", "1")
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertEqual(ran(shipped, "verify"), [])  # the ticket changes no file of a project
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertEqual([(t["ticket"], t["title"], t["tier"]) for t in p.rail("status")["tickets"]][-1],
                         ("2", "Cover deploy with checks", "PERSON"))
        self.assertEqual(json.loads(p.git("show", "main:.rail/journal/1-coverage.json"))["deploy"]["covered_by"], "2")

    def test_a_change_that_removes_a_manifest_and_keeps_the_code_raises_the_question_for_that_folder(self):
        p = self.shop()
        nn, _ = self.claim(p, "Drop the package file", ["web/**"])
        os.unlink(os.path.join(p.worktree(nn), "web", "package.json"))
        p.queue_reviews(said("needs-checks", evidence="TypeScript the app is built from."), clean())
        shipped = p.rail("advance", nn)
        (asked,) = events(p, nn, "1-drop-the-package-file", "question")
        self.assertEqual((asked["type"], asked["fact"]["folder"], asked["fact"]["types"]), ("uncovered", "web", [".json", ".ts"]))
        self.assertEqual(ran(shipped, "verify"), [])  # the project is gone from the branch, and nothing uses it

    def test_rail_doctor_prints_the_projects_and_the_folders_inside_none(self):
        entry = '\n[[projects]]\nname = "web"\nverify = "pnpm test"\nuses = ["api"]\n'
        p = self.shop(config=CONFIG + entry, files={"infra/main.tf": TF, "infra/modules/queue/main.tf": TF,
                                                   "design/logo.svg": "<svg/>\n", "design/README": "Logos.\n"})
        found = {s["step"]: s for s in p.rail("doctor", expect=None)["steps"]}
        self.assertEqual(found["project api"]["detail"], "python, uv, a member of the workspace at the root; paths api/**;"
                         " uses lib-python; setup: uv sync --locked --package shop-api; verify: uv run ruff format --check"
                         " --extend-exclude .rail --extend-exclude .claude . && uv run ruff check --extend-exclude .rail"
                         " --extend-exclude .claude . && uv run basedpyright --level error && uv run pytest -q && { git diff"
                         " --quiet \"$RAIL_BASE\"...HEAD -- ':(top)uv.lock' || uv export --locked --no-emit-project --format"
                         " requirements-txt | pip-audit --disable-pip --no-deps -r /dev/stdin; }")
        self.assertEqual(found["project web"]["detail"], "typescript, pnpm, a member of the workspace at the root, changed"
                         " by its [[projects]] entry; paths web/**; uses api, lib-typescript; setup: pnpm install"
                         " --frozen-lockfile --ignore-scripts --filter shop-web...; verify: pnpm test")
        self.assertEqual(found["coverage"]["detail"], "inside no project, and not answered about yet: design/ (.svg,"
                         " README); infra/ (.tf). No check reads these files. The next ship, or rail next, asks what each"
                         " folder holds")
        self.assertEqual({name: s["result"] for name, s in found.items() if name.startswith(("project", "coverage"))},
                         {"project api": "pass", "project lib-python": "pass", "project lib-typescript": "pass",
                          "project web": "pass", "coverage": "pass"})


def derived(files, config=None):
    """The projects of a tree given as {path: text}, as the engine works them out, by name."""
    engine()
    from rail import layout
    found = layout.Layout(layout.Tree(sorted(files), lambda paths: {path: files[path] for path in paths}), config or {})
    layout.check(found)
    return found


def shown(found, *keys):
    return {p["name"]: tuple(p[key] for key in keys) for p in found.projects}


class Workspaces(RailTest):
    """Each workspace gives one project for each member, with commands that name the member and `uses` as the
    workspace's own files say. The commands are not checked against the tools here."""

    def test_a_pnpm_workspace(self):
        found = derived({
            "package.json": '{"name": "shop", "private": true}', "pnpm-workspace.yaml": "packages:\n  - 'apps/*'\n  - packages/ui\n",
            "pnpm-lock.yaml": "", "apps/web/package.json": '{"name": "@shop/web", "dependencies": {"@shop/ui": "workspace:^",'
                                                           ' "react": "^19.0.0"}}',
            "apps/web/tsconfig.json": "{}", "apps/web/src/main.ts": "",
            "apps/admin/package.json": '{"name": "@shop/admin", "devDependencies": {"@shop/ui": "workspace:*"}}',
            "packages/ui/package.json": '{"name": "@shop/ui"}', "packages/ui/tsconfig.json": "{}",
            "packages/old/package.json": '{"name": "@shop/old"}'})  # in no `packages` glob: a project of its own
        self.assertEqual(shown(found, "folder", "member", "uses"), {
            "apps/admin": ("apps/admin", "@shop/admin", ["packages/ui"]), "apps/web": ("apps/web", "@shop/web", ["packages/ui"]),
            "packages/old": ("packages/old", None, []), "packages/ui": ("packages/ui", "@shop/ui", [])})
        web = found.by_name["apps/web"]
        self.assertEqual(web["setup"], "pnpm install --frozen-lockfile --ignore-scripts --filter @shop/web...")
        self.assertEqual(web["verify"], "pnpm --filter @shop/web exec oxlint --deny-warnings && pnpm --filter @shop/web exec"
                         " tsc --noEmit && pnpm --filter @shop/web test && { git diff --quiet \"$RAIL_BASE\"...HEAD --"
                         " ':(top)pnpm-lock.yaml' || pnpm audit; }")
        self.assertNotIn("tsc", found.by_name["apps/admin"]["verify"])  # no tsconfig.json
        engine()
        from rail import layout
        self.assertEqual(layout.reach(found, found, ["packages/ui/src/button.ts"]), ["packages/ui", "apps/admin", "apps/web"])
        self.assertEqual(layout.reach(found, found, ["pnpm-lock.yaml"]), ["packages/ui", "apps/admin", "apps/web"])
        self.assertEqual(layout.reach(found, found, ["apps/web/src/main.ts"]), ["apps/web"])

    def test_the_root_of_a_pnpm_workspace_is_a_project_when_a_member_depends_on_its_package(self):
        files = {"package.json": '{"name": "notes-web"}', "pnpm-workspace.yaml": "packages:\n  - tools/*\n",
                 "pnpm-lock.yaml": "", "src/notes.ts": "",
                 "tools/report/package.json": '{"name": "notes-report", "dependencies": {"notes-web": "workspace:*"}}'}
        found = derived(files)
        self.assertEqual(shown(found, "folder", "member", "uses"), {
            "root": ("", "notes-web", []), "tools/report": ("tools/report", "notes-report", ["root"])})
        # pnpm's filter matches no package at the root and exits 0, so the root runs the lines with no filter.
        root = found.by_name["root"]
        self.assertEqual((root["setup"], root["member"]), ("pnpm install --frozen-lockfile --ignore-scripts", "notes-web"))
        self.assertIn("pnpm test", root["verify"])
        self.assertNotIn("--filter", root["verify"])
        self.assertIn("pnpm --filter notes-report test", found.by_name["tools/report"]["verify"])
        engine()
        from rail import layout
        self.assertEqual(layout.reach(found, found, ["src/notes.ts"]), ["root", "tools/report"])
        self.assertEqual(layout.reach(found, found, ["tools/report/src/report.ts"]), ["tools/report"])
        # With no member that depends on it, the root holds the tools and is no project.
        files["tools/report/package.json"] = '{"name": "notes-report"}'
        self.assertEqual(sorted(derived(files).by_name), ["tools/report"])

    def test_a_go_work_file(self):
        found = derived({
            "go.work": "go 1.24\n\nuse (\n\t./api\n\t./lib/money\n)\n", "go.work.sum": "",
            "api/go.mod": "module example.com/shop/api\n\ngo 1.24\n\nrequire (\n\texample.com/shop/lib/money v0.0.0\n"
                          "\tgithub.com/google/uuid v1.6.0\n)\n",
            "api/go.sum": "", "api/main.go": "",
            "lib/money/go.mod": "module example.com/shop/lib/money\n\ngo 1.24\n", "lib/money/money.go": "",
            "tools/gen/go.mod": "module example.com/shop/tools/gen\n"})  # not in the go.work: a project of its own
        self.assertEqual(shown(found, "folder", "member", "uses"), {
            "api": ("api", "example.com/shop/api", ["lib/money"]), "lib/money": ("lib/money", "example.com/shop/lib/money", []),
            "tools/gen": ("tools/gen", None, [])})
        api = found.by_name["api"]
        self.assertEqual((api["setup"], api["workspace"]), ("go mod download", ""))
        self.assertIn("go test -race ./...", api["verify"])  # in the module's folder, which names it
        engine()
        from rail import layout
        self.assertEqual(layout.reach(found, found, ["lib/money/money.go"]), ["lib/money", "api"])
        self.assertEqual(layout.reach(found, found, ["go.work"]), ["lib/money", "api"])

    def test_a_uv_workspace(self):
        found = derived({
            "pyproject.toml": '[project]\nname = "shop"\nversion = "1"\ndependencies = ["shop-core"]\n\n[tool.uv.workspace]\n'
                              'members = ["services/*", "core"]\nexclude = ["services/legacy"]\n\n[tool.uv.sources]\n'
                              "shop-core = { workspace = true }\n",
            "uv.lock": "", "shop/__init__.py": "",
            "core/pyproject.toml": '[project]\nname = "shop-core"\nversion = "1"\n',
            "services/billing/pyproject.toml": '[project]\nname = "shop-billing"\nversion = "1"\n'
                                               'dependencies = ["shop-core>=1", "httpx"]\n\n[tool.uv.sources]\n'
                                               "shop-core = { workspace = true }\n",
            "services/mail/pyproject.toml": '[project]\nname = "shop-mail"\nversion = "1"\ndependencies = ["shop-core"]\n',
            "services/legacy/pyproject.toml": '[project]\nname = "shop-legacy"\nversion = "1"\n'})
        self.assertEqual(shown(found, "folder", "member", "uses"), {
            "root": ("", "shop", ["core"]), "core": ("core", "shop-core", []),
            "services/billing": ("services/billing", "shop-billing", ["core"]),
            # The sources the workspace's root names hold for every member. services/legacy is excluded from the
            # workspace, so its manifest is one nested in the root project's folder, and counts for that project.
            "services/mail": ("services/mail", "shop-mail", ["core"])})
        self.assertEqual(found.by_name["services/billing"]["setup"], "uv sync --locked --package shop-billing")
        self.assertEqual(found.by_name["root"]["setup"], "uv sync --locked --package shop")
        self.assertEqual([p["name"] for p in found.owners("services/legacy/old.py")], ["root"])
        self.assertIn("':(top)uv.lock'", found.by_name["services/billing"]["verify"])  # the workspace's one lockfile
        engine()
        from rail import layout
        self.assertEqual(layout.reach(found, found, ["core/money.py"]),
                         ["core", "root", "services/billing", "services/mail"])
        self.assertEqual(layout.reach(found, found, ["shop/__init__.py"]), ["root"])

    def test_a_cargo_workspace(self):
        found = derived({
            "Cargo.toml": '[workspace]\nmembers = ["crates/*"]\nresolver = "2"\n', "Cargo.lock": "",
            "crates/api/Cargo.toml": '[package]\nname = "shop-api"\nversion = "0.1.0"\n\n[dependencies]\n'
                                     'shop-money = { path = "../money" }\nserde = "1"\n',
            "crates/money/Cargo.toml": '[package]\nname = "shop-money"\nversion = "0.1.0"\n',
            "crates/cli/Cargo.toml": '[package]\nname = "shop-cli"\nversion = "0.1.0"\n\n[dev-dependencies]\n'
                                     'shop-api = { path = "../api" }\n'})
        self.assertEqual(shown(found, "folder", "member", "uses"), {
            "crates/api": ("crates/api", "shop-api", ["crates/money"]), "crates/cli": ("crates/cli", "shop-cli", ["crates/api"]),
            "crates/money": ("crates/money", "shop-money", [])})
        money = found.by_name["crates/money"]
        for part in ("cargo fmt --check -p shop-money", "cargo clippy -p shop-money --all-targets --locked -- -D warnings",
                     "cargo test --locked -p shop-money"):
            self.assertIn(part, money["verify"])
        engine()
        from rail import layout
        self.assertEqual(layout.reach(found, found, ["crates/money/src/lib.rs"]), ["crates/money", "crates/api", "crates/cli"])

    def test_two_languages_in_one_folder_nested_manifests_and_manifests_that_mark_nothing(self):
        files = {"svc/pyproject.toml": "[project]\nname = 'svc'\n", "svc/package.json": "{}", "svc/tools/package.json": "{}",
                 "docs/package.json": "{}", "vendor/x/go.mod": "module x\n", "web/node_modules/y/package.json": "{}",
                 "go.mod": "module shop\n", "cmd/tool/go.mod": "module shop/tool\n"}
        found = derived(files, {"init": {"other_manifests": ["docs/package.json"]}})
        self.assertEqual(shown(found, "folder", "profile", "paths"), {
            "root": ("", "go", ["**"]), "svc-python": ("svc", "python", ["svc/**"]),
            "svc-typescript": ("svc", "typescript", ["svc/**"])})
        self.assertEqual(found.owners("cmd/tool/main.go"), [found.by_name["root"]])  # the top-most folder's project
        self.assertEqual([p["name"] for p in found.owners("svc/app.py")], ["svc-python", "svc-typescript"])


class Extras(ShopTest):
    """What a profile brings besides its commands applies to the paths of each project of that profile, and nothing of
    it is written into the config."""

    def test_a_profiles_migration_paths_rules_and_test_paths_hold_inside_its_projects_only(self):
        p = self.shop()
        self.assertEqual(p.add(card("Change the service", ["api/**"]))["tier"], "AUTO")
        self.assertEqual(p.add(card("Add a column", ["api/alembic/versions/**"]))["tier"], "PERSON")  # Alembic, in a Python project
        self.assertEqual(p.add(card("Add a table", ["web/alembic/versions/**"]))["tier"], "AUTO")     # no Python project there
        self.assertEqual(p.add(card("Add a web table", ["web/drizzle/**"]))["tier"], "PERSON")
        self.assertNotIn("alembic", p.git("show", "main:.rail/config.toml"))

        nn, _ = self.claim(p, "Quiet the linter", ["api/**", "web/**"])
        p.write("web/gen.py", "TOTAL = 1  # type: ignore\n", base=p.worktree(nn))  # no Python project holds web/
        p.write("api/api.py", "def handle():\n    return 200  # type: ignore\n", base=p.worktree(nn))
        failed = p.rail("advance", nn, expect=3)
        (rules,) = [s for s in failed["steps"] if s["step"] == "rules"]
        self.assertEqual(rules["result"], "fail")
        self.assertIn("api/api.py adds '# type: ignore'", failed["action"]["brief"])
        self.assertNotIn("web/gen.py", failed["action"]["brief"])


if __name__ == "__main__":
    import unittest
    unittest.main()
