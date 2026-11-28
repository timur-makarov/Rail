"""Language profiles: Rail finds the projects of Python, TypeScript, Rust and Go from the tracked manifests, each
time it needs them, and each project gets its profile's commands, rules and paths with nothing written for it
(tests/test_projects.py has what a change reaches). `Projects` takes one small real program per language from rail
init through eight tickets with the language's own toolchain, and stand-ins for the worker, the reviewer and the
triage run; it skips a language whose toolchain this machine lacks, and `python3 tests/run.py --languages` fails
there instead."""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, FAKE, FAKE_WORKER, RAIL, Fixture, RailTest, ticket  # noqa: E402

FRAMEWORK = os.path.dirname(os.path.dirname(RAIL))
sys.path.insert(0, os.path.join(FRAMEWORK, "engine"))
from rail import config as configmod, init as initmod, layout  # noqa: E402
from rail.util import globmatch  # noqa: E402

LANGUAGES = ("go", "python", "rust", "typescript")


def profile(name):
    with open(os.path.join(FRAMEWORK, "engine", "profiles", name, "profile.toml"), "rb") as f:
        return tomllib.load(f)


def read(path):
    with open(path) as f:
        return f.read()


def step(answer, name):
    return [s for s in answer["steps"] if s["step"] == name][-1]


def tree(*paths, config=None, **texts):
    """The projects of a tree that tracks these files, empty unless `texts` gives one its text, by name."""
    files = {path: "" for path in paths} | texts
    found = layout.Layout(layout.Tree(sorted(files), lambda asked: {path: files[path] for path in asked}), config or {})
    return {p["name"]: p for p in found.projects}


class Detection(RailTest):
    def repo(self, files):
        """A committed repository holding these files and nothing else."""
        root = os.path.join(self.tmp, f"repo{len(os.listdir(self.tmp))}")
        os.makedirs(root)
        subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=root, check=True)
        for path, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(root, path)), exist_ok=True)
            with open(os.path.join(root, path), "w") as f:
                f.write(text)
        subprocess.run(["git", "add", "-A", "-f"], cwd=root, check=True)
        subprocess.run(["git", "commit", "--quiet", "--allow-empty", "-m", "start"], cwd=root, check=True)
        return root

    def found(self, files):
        return [(p["name"], p["profile"], p["paths"]) for p in initmod.found(self.repo(files))]

    def test_each_manifest_gives_a_project_of_its_profile(self):
        cases = {"pyproject.toml": "python", "setup.cfg": "python", "requirements-dev.txt": "python",
                 "package.json": "typescript", "Cargo.toml": "rust", "go.mod": "go"}
        for manifest, name in cases.items():
            with self.subTest(manifest):
                self.assertEqual(self.found({manifest: "\n"}), [("root", name, ["**"])])
        self.assertEqual(self.found({"README.md": "x\n", "src/main.c": "x\n"}), [])

    def test_package_json_without_tsconfig_gives_typescript_with_type_checking_off(self):
        [without] = initmod.found(self.repo({"package.json": "{}\n"}))
        [with_it] = initmod.found(self.repo({"package.json": "{}\n", "tsconfig.json": "{}\n"}))
        self.assertEqual((without["profile"], without["type_check"], with_it["type_check"]), ("typescript", False, True))
        self.assertEqual(initmod.describe([without]), "root (typescript, pnpm, no tsconfig.json: type checking off)")
        self.assertNotIn("tsc", without["verify"])
        self.assertIn("pnpm exec tsc --noEmit", with_it["verify"])
        [go] = initmod.found(self.repo({"go.mod": "module x\n"}))
        self.assertIsNone(go["type_check"])

    def test_a_manifest_below_the_root_gives_a_project_named_after_its_folder(self):
        self.assertEqual(self.found({"web/package.json": "{}\n", "api/go.mod": "module x\n"}),
                         [("api", "go", ["api/**"]), ("web", "typescript", ["web/**"])])
        # The top-most folder only: a manifest nested in a project's folder counts for that project.
        self.assertEqual(self.found({"a/go.mod": "x\n", "a/tool/go.mod": "x\n", "b/c/go.mod": "x\n"}),
                         [("a", "go", ["a/**"]), ("b/c", "go", ["b/c/**"])])
        self.assertEqual(self.found({"pyproject.toml": "\n", "libs/one/pyproject.toml": "\n"}), [("root", "python", ["**"])])

    def test_vendored_installed_built_and_untracked_manifests_give_nothing(self):
        root = self.repo({"node_modules/x/package.json": "{}\n", "vendor/y/go.mod": "x\n", "web/vendor/z/go.mod": "x\n",
                          "target/debug/Cargo.toml": "x\n", ".venv/lib/pyproject.toml": "x\n", "dist/package.json": "x\n"})
        with open(os.path.join(root, "Cargo.toml"), "w") as f:
            f.write("[package]\n")  # not tracked
        self.assertEqual(initmod.found(root), [])

    def test_brace_globs_match_either_word(self):
        cases = [("**/*.{ts,tsx,js}", "web/a.tsx", True), ("**/*.{ts,tsx,js}", "a.ts", True),
                 ("**/*.{ts,tsx,js}", "a.json", False), ("**/*.{ts,tsx,js}", "a.md", False),
                 ("{web,api/v1}/**", "api/v1/x.go", True), ("{web,api/v1}/**", "api/x.go", False),
                 ("{a,b*}/x", "bc/x", True), ("{a,b*}/x", "b/c/x", False),
                 ("a{b", "a{b", True), ("{x}", "{x}", True), ("{a,b}", "{a,b}", False)]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(globmatch(pattern, path), expected)


class Init(RailTest):
    def test_init_names_the_projects_writes_none_of_them_and_merges_the_registries(self):
        settings = {"sandbox": {"network": {"allowedDomains": ["example.com"]}}}
        p = Fixture(os.path.join(self.tmp, "mono"), init=False, files={
            "pyproject.toml": "[project]\nname = 'api'\n", "web/package.json": "{}\n", "web/tsconfig.json": "{}\n",
            ".claude/settings.json": json.dumps(settings)})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual((step(done, "projects")["status"], step(done, "projects")["detail"]), (
            "ran", "found root (python, uv), web (typescript, pnpm). Each is set up and checked with its commands, for the"
                   " changes that reach it; rail doctor prints them. Nothing is written for a project: they are worked out"
                   " from the tracked manifests each time"))
        seed = tomllib.loads(read(os.path.join(FRAMEWORK, "seed", "config.toml")))
        with open(p.path(".rail/config.toml"), "rb") as f:
            config = tomllib.load(f)
        # The one command init writes is the whole repository's: the secret scan over the branch's commits.
        self.assertEqual(config["commands"], dict(seed["commands"], verify=profile("common")["secrets"]["run"]))
        self.assertEqual({k: v for k, v in config.items() if k != "commands"}, {k: v for k, v in seed.items() if k != "commands"})
        self.assertNotIn("projects", config)
        self.assertIn("\n[tests]", read(p.path(".rail/config.toml")))  # the seed's own comments stay
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("Rail finds these projects from the tracked manifests: root (python, uv), web (typescript, pnpm). ", brief)
        self.assertIn("a [[projects]] entry with a derived project's `name` puts the repository's own `setup` or `verify`"
                      " in the\n     default's place.", brief)
        self.assertIn("Rail finds these projects from the tracked manifests: root (python, uv), web (typescript, pnpm).",
                      p.rail("next", cloud=True)["action"]["brief"])

        domains = json.loads(read(p.path(".claude/settings.json")))["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(domains, ["example.com", "api.anthropic.com", "pypi.org", "files.pythonhosted.org",
                                   "registry.npmjs.org", "registry.yarnpkg.com"])
        self.assertIn("the sandbox allows pypi.org", step(done, ".claude/settings.json")["detail"])
        self.assertEqual(p.rail("status")["reason"]["code"], "STATUS")  # the engine loads what init wrote

        again = p.rail("init")
        self.assertEqual(step(again, ".claude/settings.json")["status"], "not_run")
        self.assertEqual(step(again, "projects")["status"], "not_run")

    def test_an_existing_config_is_left_alone_and_the_registries_still_merge(self):
        p = Fixture(os.path.join(self.tmp, "existing"), init=False, files={"go.mod": "module x\n",
                                                                         ".rail/config.toml": CONFIG})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual(read(p.path(".rail/config.toml")), CONFIG)
        self.assertEqual(step(done, "projects")["status"], "not_run")
        self.assertTrue(step(done, "projects")["detail"].startswith("found calc (declared in [[projects]]), root (go, go). "))
        domains = json.loads(read(p.path(".claude/settings.json")))["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(domains, ["api.anthropic.com", "proxy.golang.org", "sum.golang.org"])

    def test_a_project_added_after_init_is_found_with_no_change_to_the_config(self):
        p = Fixture(os.path.join(self.tmp, "later"), init=False, files={"api/pyproject.toml": "[project]\nname = 'api'\n"})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        p.rail("init")
        config = read(p.path(".rail/config.toml"))
        projects = lambda: sorted(s["step"] for s in p.rail("doctor", expect=None)["steps"]  # noqa: E731
                                  if s["step"].startswith("project "))
        self.assertEqual(projects(), ["project api"])

        # A Rust service is added next year, and a vendored manifest with it.
        for path in ("worker/Cargo.toml", "worker/vendor/dep/Cargo.toml", "worker/sub/Cargo.toml"):
            os.makedirs(os.path.dirname(p.path(path)), exist_ok=True)
            with open(p.path(path), "w") as f:
                f.write("[package]\nname = 'x'\n")
        p.git("add", "-A")
        self.assertEqual(projects(), ["project api", "project worker"])  # the top-most folder stands for those below it
        self.assertEqual(read(p.path(".rail/config.toml")), config)
        self.assertIn("found api (python, uv), worker (rust, cargo). ", step(p.rail("init"), "projects")["detail"])

        # A manifest that marks no project is named as one in [init] other_manifests.
        with open(p.path(".rail/config.toml"), "w") as f:
            f.write(config.replace("other_manifests = []", 'other_manifests = ["worker/**"]'))
        self.assertEqual(projects(), ["project api"])

    def test_a_repository_in_no_profiles_language_gets_the_seed_config_as_it_is(self):
        p = Fixture(os.path.join(self.tmp, "plain"), init=False)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual(step(done, "projects")["status"], "not_run")
        self.assertEqual(read(p.path(".rail/config.toml")), read(os.path.join(FRAMEWORK, "seed", "config.toml")))


# One project for each language, none of which runs a command: these tests are about the rules.
QUIET = "".join(f'\n[[projects]]\nname = "{name}"\nsetup = ""\nverify = ""\n' for name in LANGUAGES)
MANIFESTS = {"go/go.mod": "module x\n", "python/pyproject.toml": "[project]\nname = 'x'\n",
             "rust/Cargo.toml": "[package]\nname = 'x'\n", "typescript/package.json": "{}\n"}


class Markers(RailTest):
    def test_each_languages_markers_fail_in_its_own_projects_files_and_not_in_a_markdown_file(self):
        p = self.fixture(config=CONFIG + QUIET, files=MANIFESTS)
        p.add(ticket(scope=("src/**", *(f"{name}/**" for name in LANGUAGES))))
        p.rail("next")
        p.fix_calc("1")
        files = {"go": ["go/a.go"], "python": ["python/a.py"], "rust": ["rust/a.rs"],
                 "typescript": ["typescript/a.ts", "typescript/b.tsx", "typescript/c.mjs"]}
        expected, markdown = [], []
        for name in LANGUAGES:
            markers = profile(name)["rules"][0]["forbid"]
            for path in files[name]:
                p.write(path, "".join(f"x = 1  {marker}\n" for marker in markers), base=p.worktree("1"))
                expected += [f"{path} adds '{marker}'" for marker in markers]
            markdown += markers
            # The marker in another language's file breaks nothing, and neither does it in a file of the language
            # that is inside no project of the language.
            other = files[LANGUAGES[(LANGUAGES.index(name) + 1) % 4]][0].replace("/a.", "/other.")
            p.write(other, "".join(f"x = 1  {marker}\n" for marker in markers), base=p.worktree("1"))
            p.write(files[name][0].replace(f"{name}/a.", "src/outside."), "".join(f"x = 1  {m}\n" for m in markers),
                    base=p.worktree("1"))
        p.write("python/notes.md", "".join(f"Never write {m}\n" for m in markdown), base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        brief = failed["action"]["brief"]
        for line in expected:
            self.assertIn(line, brief)
        for word in ("notes.md", "/other.", "src/outside."):
            self.assertNotIn(word, brief)
        self.assertTrue(step(failed, "rules")["detail"].startswith(f"{len(expected)} broken: "), step(failed, "rules"))


class Data(RailTest):
    def test_every_profile_has_its_keys_and_the_languages_page_names_its_data(self):
        page = read(os.path.join(FRAMEWORK, "engine", "docs", "languages.md"))
        names = sorted(n for n in os.listdir(os.path.join(FRAMEWORK, "engine", "profiles")) if n != "common")
        self.assertEqual(names, sorted(LANGUAGES))
        for name in names:
            data = profile(name)
            self.assertLessEqual({"manifests", "domains", "generated", "migration_paths", "tests", "rules"}, set(data))
            for rule in data["rules"]:
                self.assertLessEqual(set(rule), set(configmod.RULE_KEYS))
                self.assertTrue(rule["id"] and rule["files"] and rule["forbid"] and rule["fix"])
            for word in data["manifests"] + data["domains"] + data["generated"] + data["migration_paths"] + \
                    [m for rule in data["rules"] for m in rule["forbid"] + [rule["files"]]]:
                self.assertIn(f"`{word}`", page, name)
            # The commands: every manager and its lockfile, each line of the one a new project starts with, and
            # what a workspace's member runs in their place.
            first = data["managers"][0]
            member = [first[key] for key in ("member_setup",) if key in first] + \
                     [part["member"] for part in first["verify"] if "member" in part]
            for word in [w for m in data["managers"] for w in (m["name"], m["lockfile"])] + [first["setup"]] + \
                    [part["run"] for part in first["verify"]] + member + [data.get("workspace") or first["lockfile"]]:
                self.assertIn(f"`{word.replace('|', chr(92) + '|')}`", page, name)
        for folder in profile("common")["ignore"]:
            self.assertIn(f"`{folder}`", page)
        self.assertIn(f"`{profile('common')['secrets']['run']}`", page)


class Defaults(RailTest):
    """The commands a project gets, from the profiles alone: no toolchain runs here."""

    def test_the_lockfile_names_the_manager_and_each_project_runs_its_commands_in_its_folder(self):
        found = tree("api/pyproject.toml", "api/poetry.lock", "web/package.json", "web/package-lock.json",
                     "web/tsconfig.json", "tools/gen/go.mod", "tools/lint/go.mod")
        self.assertEqual([(p["name"], p["folder"], p["profile"], p["manager"], p["setup"]) for p in found.values()], [
            ("api", "api", "python", "poetry", "poetry install"),
            ("tools/gen", "tools/gen", "go", "go", "go mod download"),
            ("tools/lint", "tools/lint", "go", "go", "go mod download"),
            ("web", "web", "typescript", "npm", "npm ci --ignore-scripts")])
        # The folder is where the command runs, so no command names it.
        self.assertTrue(found["tools/gen"]["verify"].startswith('test -z "$(gofmt -l .)" && go vet ./...'))
        self.assertIn("poetry run pytest -q", found["api"]["verify"])
        self.assertIn("npx --no-install tsc --noEmit", found["web"]["verify"])
        # An audit runs only on a change that touches the project's lockfile, wherever the command runs.
        self.assertTrue(found["web"]["verify"].endswith(
            """ && { git diff --quiet "$RAIL_BASE"...HEAD -- ':(top)web/package-lock.json' || npm audit; }"""))
        self.assertTrue(found["tools/gen"]["verify"].endswith(
            """ && { git diff --quiet "$RAIL_BASE"...HEAD -- ':(top)tools/gen/go.sum' || govulncheck ./...; }"""))
        # The secret scan is the whole repository's, and no project's.
        self.assertNotIn("gitleaks", "".join(p["verify"] for p in found.values()))

    def test_types_are_left_out_where_type_checking_is_off_and_each_part_names_its_tool(self):
        found = tree("package.json", "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock")
        self.assertEqual(sorted(found), ["root-rust", "root-typescript"])  # two languages' manifests in one folder
        self.assertEqual([(p["profile"], part["part"], part["tool"]) for p in found.values() for part in p["parts"]], [
            ("rust", "format", "rustfmt"), ("rust", "lint", "cargo-clippy"), ("rust", "tests", "cargo"),
            ("rust", "audit", "cargo-deny"), ("typescript", "lint", "oxlint"), ("typescript", "tests", "pnpm"),
            ("typescript", "audit", "pnpm")])
        self.assertEqual((found["root-rust"]["setup"], found["root-typescript"]["setup"]),
                         ("cargo fetch --locked", "pnpm install --frozen-lockfile --ignore-scripts"))
        self.assertEqual(found["root-typescript"]["verify"], "pnpm exec oxlint --deny-warnings && pnpm test && { git diff"
                         """ --quiet "$RAIL_BASE"...HEAD -- ':(top)pnpm-lock.yaml' || pnpm audit; }""")

    def test_a_requirements_file_with_no_lockfile_picks_pip_and_its_commands_name_the_file(self):
        [found] = tree("requirements-dev.txt", "src/app.py").values()
        self.assertEqual((found["manager"], found["setup"]),
                         ("pip", "python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"))
        self.assertIn("""{ git diff --quiet "$RAIL_BASE"...HEAD -- ':(top)requirements-dev.txt' || pip-audit -r"""
                      " requirements-dev.txt; }", found["verify"])
        self.assertNotIn("uv ", found["verify"])
        self.assertNotIn("requirements.txt", found["setup"] + found["verify"])
        # A lockfile beside it names the manager, whatever else is tracked; with neither, the first manager.
        for files, manager in ((("requirements-dev.txt", "pyproject.toml", "uv.lock"), "uv"),
                               (("requirements-dev.txt", "pyproject.toml", "poetry.lock"), "poetry"),
                               (("pyproject.toml",), "uv"), (("requirements.txt", "requirements-dev.txt"), "pip")):
            with self.subTest(files):
                [found] = tree(*files).values()
                self.assertEqual(found["manager"], manager)
        self.assertIn("pip install -r requirements.txt", found["setup"])  # the last one: the file pip pins with
        # Below the root, the file is looked for in the folder that holds the manifest.
        [found] = tree("api/requirements-test.txt", "requirements-dev.txt.bak").values()
        self.assertEqual((found["folder"], found["setup"]),
                         ("api", "python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt"))

    def test_every_default_is_a_command_the_config_can_hold(self):
        for name in LANGUAGES:
            for manager in profile(name)["managers"]:
                self.assertTrue(manager["name"] and manager["lockfile"] and manager["setup"], name)
                self.assertLessEqual({p["part"] for p in manager["verify"]}, {"format", "lint", "types", "tests", "audit"})
                for part in manager["verify"]:
                    self.assertLessEqual({"part", "run", "tool"}, set(part), name)
                    self.assertLessEqual(set(part), {"part", "run", "tool", "member"}, name)
                    for command in (part["run"], part.get("member", "")):
                        self.assertEqual(tomllib.loads("x = " + initmod.toml_string(command))["x"], command)


GENERATED = "// Code generated by protoc-gen-go. DO NOT EDIT.\n"


class Size(RailTest):
    def test_a_go_file_marked_generated_before_its_package_line_is_left_out_of_the_size_count(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        body = "".join(f"var v{i} = {i}\n" for i in range(10))
        for path, text in {
            "src/first.go": GENERATED + "\npackage x\n" + body,                          # on line 1: left out
            "src/licensed.go": "// Copyright the authors.\n\n" + GENERATED + "\npackage x\n" + body,  # left out
            "src/after.go": "package x\n\n" + GENERATED + body,                          # after package: 13 lines
            "src/inline.go": "package x // Code generated by hand. DO NOT EDIT.\n" + body,  # not its own line: 11
            "src/plain.go": "package x\n" + body,                                        # 11
        }.items():
            p.write(path, text, base=p.worktree("1"))
        p.fix_calc("1")  # 2 more lines: one out, one in
        shipped = p.rail("advance", "1", expect=None)
        self.assertEqual(step(shipped, "size")["detail"], "size 37/600")


HERE = os.path.dirname(os.path.abspath(__file__))
STRICT = os.environ.get("RAIL_LANGUAGES") == "1"  # tests/run.py --languages: a missing toolchain fails, not skips


def have(tool):
    return shutil.which(tool) is not None


def shell(command, cwd):
    """A command as the engine runs one: bash -o pipefail, with RAIL_BASE set. Returns (exit code, output)."""
    done = subprocess.run(["bash", "-o", "pipefail", "-c", command], cwd=cwd, capture_output=True, text=True,
                          env=dict(os.environ, RAIL_BASE="main", RAIL_TICKET="1"))
    return done.returncode, done.stdout + done.stderr


def fake_key():
    """Text shaped like a private key, made here so that no file of Rail's own holds one."""
    body = base64.b64encode(b"".join(hashlib.sha256(bytes([i])).digest() for i in range(24))).decode()
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return "-----BEGIN RSA PRIVATE " + "KEY-----\n" + lines + "\n-----END RSA PRIVATE " + "KEY-----\n"


# One project per language (tests/projects/NAME). `needs`: the toolchain; without it the language is skipped.
# `mistakes`: for a part of verify, by (part, tool), one edit that the part has to catch: (path, old, new), where an
# empty `old` adds `new` at the end of the file. `ticket`: the change the ticket makes, its new test first: with the
# test alone verify fails, and with the fix it passes.
PROJECTS = {
    "python": {
        "needs": ("uv",),
        "mistakes": {
            ("format", "ruff"): ("src/notes/store.py", "", '\n\nSIZES = {  "small":1 }\n'),
            ("lint", "ruff"): ("src/notes/store.py", "", "\n\ndef unused() -> None:\n    import os\n"),
            ("types", "basedpyright"): ("src/notes/store.py", "", '\n\nCOUNT: int = "three"\n'),
            ("tests", "pytest"): ("src/notes/store.py", '"done": False}', '"done": True}'),
        },
        "ticket": {
            "scope": ("src/**", "tests/**"),
            "check": "uv run pytest -q tests/test_trim.py",
            "test": ("tests/test_trim.py", '''import unittest

from notes.store import Store


class TrimTest(unittest.TestCase):
    def test_the_spaces_around_a_title_are_dropped(self) -> None:
        self.assertEqual(Store().add("  write the report ")["title"], "write the report")

    def test_a_title_of_only_spaces_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            Store().add("   ")
'''),
            "fix": ("src/notes/store.py", "        if not title:\n", "        title = title.strip()\n        if not title:\n"),
        },
    },
    "typescript": {
        "needs": ("node", "pnpm"),
        "mistakes": {
            ("lint", "oxlint"): ("src/notes.ts", "", "\ndebugger;\n"),
            ("types", "tsc"): ("src/notes.ts", "", '\nexport const count: number = "three";\n'),
            ("tests", "pnpm"): ("src/notes.ts", "title, done: false };", "title, done: true };"),
        },
        "ticket": {
            "scope": ("src/**", "test/**"),
            "check": "node --test test/trim.test.ts",
            "test": ("test/trim.test.ts", '''import assert from "node:assert/strict";
import { test } from "node:test";

import { Notes } from "../src/notes.ts";

test("the spaces around a title are dropped", () => {
  assert.equal(new Notes().add("  write the report ").title, "write the report");
});

test("a title of only spaces is refused", () => {
  assert.throws(() => new Notes().add("   "), /a note needs a title/);
});
'''),
            "fix": ("src/notes.ts", "  add(title: string): Note {\n", "  add(given: string): Note {\n    const title = given.trim();\n"),
        },
    },
    "rust": {
        "needs": ("cargo",),
        "mistakes": {
            ("format", "rustfmt"): ("crates/notes/src/lib.rs", "", "\npub fn two() -> u8 {2}\n"),
            ("lint", "cargo-clippy"): ("crates/notes/src/lib.rs", "",
                                       "\npub fn none(notes: &Notes) -> bool {\n    notes.all().len() == 0\n}\n"),
            ("tests", "cargo"): ("crates/notes/src/lib.rs", "            done: false,\n", "            done: true,\n"),
        },
        "ticket": {
            "scope": ("crates/**",),
            "check": "cargo test --locked -p notes --test trim",
            "test": ("crates/notes/tests/trim.rs", '''use notes::{Error, Notes};

#[test]
fn the_spaces_around_a_title_are_dropped() {
    let mut notes = Notes::default();
    notes.add("  write the report ").unwrap();
    assert_eq!(notes.all()[0].title, "write the report");
}

#[test]
fn a_title_of_only_spaces_is_refused() {
    assert_eq!(Notes::default().add("   "), Err(Error::NoTitle));
}
'''),
            "fix": ("crates/notes/src/lib.rs", "        if title.is_empty() {\n",
                    "        let title = title.trim();\n        if title.is_empty() {\n"),
        },
    },
    "go": {
        "needs": ("go",),
        "mistakes": {
            ("format", "gofmt"): ("internal/notes/store.go", "", "\nfunc Two() int {return 2}\n"),
            ("lint", "go"): ("cmd/notes/main.go", "", '\nfunc init() { fmt.Printf("%d\\n", "three") }\n'),
            ("lint", "golangci-lint"): ("internal/notes/store.go", "", "\nfunc two() int { return 2 }\n"),
            ("tests", "go"): ("internal/notes/store.go", "Title: title}", "Title: title, Done: true}"),
        },
        "ticket": {
            "scope": ("internal/**",),
            "check": "go test -run TestTitleSpacesAreDropped -v ./internal/notes | grep '^--- PASS'",
            "test": ("internal/notes/trim_test.go", '''package notes

import (
	"errors"
	"testing"
)

func TestTitleSpacesAreDropped(t *testing.T) {
	var store Store
	note, err := store.Add("  write the report ")
	if err != nil || note.Title != "write the report" {
		t.Fatalf("got %q, %v", note.Title, err)
	}
	if _, err := store.Add("   "); !errors.Is(err, ErrNoTitle) {
		t.Fatalf("a title of only spaces gave %v", err)
	}
}
'''),
            "fix": ("internal/notes/store.go",
                    '''import (
	"errors"
	"sync"
)''', '''import (
	"errors"
	"strings"
	"sync"
)'''),
            "fix_too": ("internal/notes/store.go", '	if title == "" {\n', '	title = strings.TrimSpace(title)\n	if title == "" {\n'),
        },
    },
}


# What the later steps of `Projects.project` need for each language (the steps are listed on the class).
# `first`: the name of the sample's own project, and `home`: a folder inside it. `second`: a project that a ticket
# adds in a new folder and that uses the first: its name, the ticket's scope and check, the new `files`, the `edits`
# to files the sample has, and `lock`, the command that makes the lockfile follow. `untrim`: a change that drops
# behaviour the first ticket added (titles are trimmed), with the edit to that ticket's test that hides it.
# `product`: what `tests/projects/checks/` is told about the product (product.json), with the surface a change to
# `drive` reaches.
MORE = {
    "python": {
        "first": "root", "home": "",
        "second": {
            "name": "tools/report", "scope": ("tools/**", "pyproject.toml", "uv.lock", ".gitignore"),
            "check": "cd tools/report && uv run pytest -q", "lock": "uv lock",
            "files": {
                "tools/report/pyproject.toml": """[project]
name = "notes-report"
version = "0.1.0"
description = "A count of the notes in a store, done and open."
requires-python = ">=3.11"
dependencies = ["notes"]

[tool.uv.sources]
notes = { workspace = true }

[tool.pytest.ini_options]
pythonpath = ["src", "../../src"]
testpaths = ["tests"]
""",
                "tools/report/src/notes_report/__init__.py": """\"\"\"A count of the notes in a store.\"\"\"

from notes.store import Store


def count(store: Store) -> dict[str, int]:
    \"\"\"How many notes are done and how many are open.\"\"\"
    notes = store.all()
    done = sum(1 for note in notes if note["done"])
    return {"done": done, "open": len(notes) - done}
""",
                "tools/report/tests/test_count.py": """import unittest

from notes_report import count

from notes.store import Store


class CountTest(unittest.TestCase):
    def test_a_new_note_is_open(self) -> None:
        store = Store()
        store.add("write the report")
        self.assertEqual(count(store), {"done": 0, "open": 1})
""",
            },
            # The root's type check leaves the member to the member's own: it cannot see the member's `src`. A
            # member that depends on the root has uv install the root as a package, which leaves build metadata.
            "edits": [("pyproject.toml", "", '\n[tool.uv.workspace]\nmembers = ["tools/report"]\n\n[tool.basedpyright]\n'
                                             'exclude = ["tools", "**/__pycache__", "**/.*"]\n'),
                      (".gitignore", "", "*.egg-info/\n")],
        },
        "untrim": {
            "code": [("src/notes/store.py", "        title = title.strip()\n        if not title:\n",
                      "        if not title.strip():\n")],
            "test": ("tests/test_trim.py", '["title"], "write the report")', '["title"], "  write the report ")'),
        },
        "product": {"start": "PYTHONPATH=src exec python3 -m notes {port} {run}/notes.db", "path": "/notes"},
        "surface": ("api", "api", "root"), "drive": "",
    },
    "typescript": {
        "first": "root", "home": "",
        "second": {
            "name": "tools/report", "scope": ("tools/**", "pnpm-workspace.yaml", "pnpm-lock.yaml"),
            "check": 'cd tools/report && node --test "test/**/*.test.ts"', "lock": "pnpm install --lockfile-only",
            "files": {
                "pnpm-workspace.yaml": "packages:\n  - tools/report\n",
                "tools/report/package.json": """{
  "name": "notes-report",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "node --test \\"test/**/*.test.ts\\""
  },
  "dependencies": {
    "notes-web": "workspace:*"
  },
  "engines": {
    "node": ">=22.18"
  }
}
""",
                "tools/report/tsconfig.json": """{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2023"],
    "types": [],
    "strict": true,
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "erasableSyntaxOnly": true,
    "verbatimModuleSyntax": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["src"]
}
""",
                "tools/report/src/report.ts": """import type { Notes } from "notes-web/src/notes.ts";

export function count(notes: Notes): { done: number; open: number } {
  const all = notes.all();
  const done = all.filter((note) => note.done).length;
  return { done, open: all.length - done };
}
""",
                "tools/report/test/report.test.ts": """import assert from "node:assert/strict";
import { test } from "node:test";

import { Notes } from "notes-web/src/notes.ts";

import { count } from "../src/report.ts";

test("a new note is open", () => {
  const notes = new Notes();
  notes.add("write the report");
  assert.deepEqual(count(notes), { done: 0, open: 1 });
});
""",
            },
            "edits": [],
        },
        "untrim": {
            "code": [("src/notes.ts", "  add(given: string): Note {\n    const title = given.trim();\n",
                      "  add(title: string): Note {\n"),
                     ("src/notes.ts", '    if (title === "") {\n', '    if (title.trim() === "") {\n')],
            "test": ("test/trim.test.ts", '.title, "write the report");', '.title, "  write the report ");'),
        },
        "product": {"start": "exec node bin/serve.mjs {port}", "path": "/api/notes"},
        "surface": ("api", "api", "root"), "drive": "",
    },
    "rust": {
        "first": "crates/notes", "home": "crates/notes/",
        "second": {
            "name": "crates/notes-report", "scope": ("crates/notes-report/**", "Cargo.toml", "Cargo.lock"),
            "check": "cargo test --locked -p notes-report", "lock": "cargo metadata --format-version 1 --offline > /dev/null",
            "files": {
                "crates/notes-report/Cargo.toml": """[package]
name = "notes-report"
version.workspace = true
edition.workspace = true

[dependencies]
notes = { path = "../notes" }
""",
                "crates/notes-report/src/lib.rs": """//! A count of the notes in a list.

use notes::Notes;

/// How many notes are done and how many are open.
pub fn count(notes: &Notes) -> (usize, usize) {
    let done = notes.all().iter().filter(|note| note.done).count();
    (done, notes.all().len() - done)
}
""",
                "crates/notes-report/tests/count.rs": """use notes::Notes;
use notes_report::count;

#[test]
fn a_new_note_is_open() {
    let mut notes = Notes::default();
    notes.add("write the report").unwrap();
    assert_eq!(count(&notes), (0, 1));
}
""",
            },
            "edits": [("Cargo.toml", 'members = ["crates/notes", "crates/notes-cli"]',
                       'members = ["crates/notes", "crates/notes-cli", "crates/notes-report"]')],
        },
        "untrim": {
            "code": [("crates/notes/src/lib.rs", "        let title = title.trim();\n        if title.is_empty() {\n",
                      "        if title.trim().is_empty() {\n")],
            "test": ("crates/notes/tests/trim.rs", 'title, "write the report");', 'title, "  write the report ");'),
        },
        "product": {"cli": "cargo run --quiet --locked -p notes-cli --"},
        "surface": ("cli", "cli", "crates/notes-cli"), "drive": "crates/notes-cli/",
    },
    "go": {
        "first": "root", "home": "",
        "second": {
            "name": "tools/report", "scope": ("tools/**", "go.work"),
            "check": "cd tools/report && go test ./...", "lock": "",
            "files": {
                "go.work": "go 1.22\n\nuse (\n\t.\n\t./tools/report\n)\n",
                "tools/report/go.mod": "module example.com/notes/tools/report\n\ngo 1.22\n\n"
                                       "require example.com/notes v0.0.0\n\nreplace example.com/notes => ../..\n",
                "tools/report/report.go": """// Package report counts the notes of a store.
package report

import "example.com/notes/internal/notes"

// Count says how many notes are done and how many are open.
func Count(store *notes.Store) (done, open int) {
	for _, note := range store.All() {
		if note.Done {
			done++
		} else {
			open++
		}
	}
	return done, open
}
""",
                "tools/report/report_test.go": """package report

import (
	"testing"

	"example.com/notes/internal/notes"
)

func TestANewNoteIsOpen(t *testing.T) {
	var store notes.Store
	if _, err := store.Add("write the report"); err != nil {
		t.Fatal(err)
	}
	if done, open := Count(&store); done != 0 || open != 1 {
		t.Fatalf("got %d done and %d open", done, open)
	}
}
""",
            },
            "edits": [],
        },
        "untrim": {
            "code": [("internal/notes/store.go", '	title = strings.TrimSpace(title)\n	if title == "" {\n',
                      '	if strings.TrimSpace(title) == "" {\n')],
            "test": ("internal/notes/trim_test.go", 'note.Title != "write the report"',
                     'note.Title != "  write the report "'),
        },
        "product": {"start": "go build -o {run}/notes ./cmd/notes && exec {run}/notes serve 127.0.0.1:{port}",
                    "path": "/notes"},
        "surface": ("api", "api", "root"), "drive": "",
    },
}
CLEAN = {"summary": "Clean.", "findings": []}
TF = 'resource "aws_s3_bucket" "notes" {\n  bucket = "notes-export"\n}\n'
PUSH = """name: push
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  say:
    runs-on: ubuntu-latest
    steps:
      - run: echo pushed
"""


def card(title, scope, check, why):
    scopes = ", ".join(f'"{s}"' for s in scope)
    return (f'+++\ntitle = "{title}"\ntier = "AUTO"\nscope_paths = [{scopes}]\n+++\n\n## Why\n{why}\n\n'
            f"## Done Contract\n- Check: `{check}`\n")


def said(answer, reason="Read the ticket and the change.", **more):
    """An answer to a triage question, as the stand-in for the triage run gives it."""
    return {"answer": answer, "reason": reason, **more}


def ran(answer, family):
    """The names behind a family's steps that passed: `verify:root` gives `root`."""
    return [s["step"].split(":", 1)[1] for s in answer["steps"]
            if s["step"].startswith(family + ":") and s.get("result") == "pass"]


def failed(answer):
    return [s["step"] for s in answer["steps"] if s.get("result") == "fail"]


def area(root, name, holds):
    """Add a row for a new top-level folder to `## Areas` of ARCHITECTURE.md, as doc-lint asks of the change."""
    full = os.path.join(root, "ARCHITECTURE.md")
    lines = read(full).splitlines()
    at = lines.index("## Areas") + 1
    while at < len(lines) and lines[at].startswith("|"):
        at += 1
    lines.insert(at, f"| {name} | {name}/** | {holds} |")
    with open(full, "w") as f:
        f.write("\n".join(lines) + "\n")


def stand_ins(text):
    """The seed config's text with Rail's stand-ins where it names a model's CLI: the worker, the reviewer, which the
    triage run uses too, and consult. No test here starts a model."""
    text, workers = re.subn(r"(?ms)^command = '''claude -p --output-format stream-json.*?'''",
                            f'command = "python3 {FAKE_WORKER}"', text)
    text, reviewers = re.subn(r"(?m)^command = '''claude -p --safe-mode .*--json-schema.*$",
                              f'command = "python3 {FAKE}"', text)
    text, consults = re.subn(r'(?m)^command = "claude -p --safe-mode --effort high .*--tools Read,Grep,Glob"$',
                             f'command = "python3 {FAKE} --consult"', text)
    assert (workers, reviewers, consults) == (1, 1, 1), (workers, reviewers, consults)
    assert "claude -p" not in "\n".join(line.split("#")[0] for line in text.splitlines()), "a model's CLI is left"
    return text


def edit(root, path, old, new):
    full = os.path.join(root, path)
    text = read(full) if os.path.exists(full) else ""
    if old and old not in text:
        raise AssertionError(f"{path} doesn't hold {old!r}")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text.replace(old, new, 1) if old else text + new)


class Projects(RailTest):
    """Each language's project from rail init on, with the commands its profile gives it and no remote. Each step
    checks that the ticket ends where it should; the cases of each feature are in that feature's own tests.

    1. `rail init` writes no project, and `rail doctor` prints the one it derived.
    2. A plain AUTO ticket: each part of `verify` catches a planted mistake, and the ticket merges.
    3. A ticket adds a second project that uses the first: set up and checked in the ship that adds it.
    4. A ticket drops behaviour and edits the test that held it: `old-test`, answered `lost`.
    5. A ticket on a path of a kind: built with no wait, merged by a person's `rail accept`.
    6. A ticket fails the same way to the cap: `stuck`, answered `approach`, started again and merged.
    7. A ticket adds a folder no check reads: `uncovered`, answered `needs-checks`, where a folder can be so.
    8. A ticket changes a project of a surface: the product is started, seeded, driven and stopped.
    9. `rail stats` has a number for each of these.

    Steps 3 to 9 need every tool of the profile, and are left out, and reported, on a machine that lacks one."""

    def project(self, name):
        spec = PROJECTS[name]
        missing = [tool for tool in spec["needs"] if not have(tool)]
        if missing:
            said = f"the {name} project needs {', '.join(missing)} on this machine"
            self.fail(said) if STRICT else self.skipTest(said)

        p = Fixture(os.path.join(self.tmp, name), tree=os.path.join(HERE, "projects", name), init=False)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        found = initmod.found(p.root)
        self.assertTrue(found and all(f["profile"] == name for f in found), found)
        self.assertIn(f"found {initmod.describe(found)}. ", step(done, "projects")["detail"])
        text = read(p.path(".rail/config.toml"))
        secrets = profile("common")["secrets"]
        self.assertEqual(tomllib.loads(text)["commands"]["verify"], secrets["run"])  # the one command init writes
        self.assertNotIn("\n[[projects]]", text)
        self.assertIn(f"Rail finds these projects from the tracked manifests: {initmod.describe(found)}. ",
                      p.rail("next")["action"]["brief"])

        # What the init task leaves on this machine: the parts whose tools are here, and Rail's stand-in reviewer.
        # A project keeps its derived commands unless a part's tool is missing: then an entry gives it the rest.
        parts, left = [], []
        for f in found:
            here = [part for part in f["parts"] if have(part["tool"])]
            left += [f"{name} {part['part']} ({part['tool']})" for part in f["parts"] if part not in here]
            parts += [dict(part, cwd=f["folder"]) for part in here]
            if len(here) < len(f["parts"]):
                verify = " && ".join(part["run"] for part in here)
                text += f'\n[[projects]]\nname = "{f["name"]}"\nverify = {initmod.toml_string(verify)}\n'
        if have(secrets["tool"]):
            parts.append(dict(secrets, part="secrets", cwd=""))
        else:
            left.append(f"secrets ({secrets['tool']})")
            text = text.replace(f"verify = {initmod.toml_string(secrets['run'])}", 'verify = ""')
        report = os.environ.get("RAIL_LANGUAGES_REPORT")
        if report and left:
            with open(report, "a") as f:
                f.write(f"{name}: not run, the tool is not on this machine: {', '.join(left)}\n")
        p.write(".rail/config.toml", stand_ins(text))
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "set up Rail")

        change = spec["ticket"]
        scope = ", ".join(f'"{s}"' for s in change["scope"])
        p.add(f'+++\ntitle = "Trim note titles"\ntier = "AUTO"\nscope_paths = [{scope}]\n+++\n\n## Why\n'
              "A title keeps the spaces typed around it, and a title of only spaces is taken as a note.\n\n"
              f"## Done Contract\n- Check: `{change['check']}`\n")
        claimed = p.rail("next")
        self.assertEqual((claimed["ticket"], claimed["reason"]["code"]), ("1", "IMPLEMENT"), claimed)
        set_up = [s for s in claimed["steps"] if s["step"].startswith("setup:")]  # each project's setup, run by Rail
        self.assertTrue(set_up and all(s["result"] == "pass" for s in set_up), claimed["steps"])
        work = p.worktree("1")

        def run_all():
            for part in parts:
                code, output = shell(part["run"], os.path.join(work, part["cwd"]))
                if code:
                    return code, f"{part['part']} in {part['cwd'] or 'the root'}: {output}"
            return 0, ""

        # Every part passes on the untouched project, and each catches the mistake made for it.
        code, output = run_all()
        self.assertEqual(code, 0, output)
        for part in parts:
            mistake = spec["mistakes"].get((part["part"], part["tool"]))
            if mistake and not mistake[0].startswith(part["cwd"]):
                continue  # another project's file
            if part["part"] == "secrets":
                edit(work, "deploy.pem", "", fake_key())
                subprocess.run("git add -A && git commit --quiet -m 'add a key'", shell=True, cwd=work, check=True)
                code, output = shell(part["run"], work)
                subprocess.run(["git", "reset", "--quiet", "--hard", "HEAD~1"], cwd=work, check=True)
            elif mistake:
                edit(work, *mistake)
                code, output = shell(part["run"], os.path.join(work, part["cwd"]))
                subprocess.run("git checkout --quiet -- . && git clean --quiet -fd", shell=True, cwd=work, check=True)
            else:
                continue  # an audit: these projects have no dependency to pin to a version with an advisory
            self.assertNotEqual(code, 0, f"{name} {part['part']} ({part['tool']}) passed a planted mistake:\n{output}")
            self.assertNotEqual(code, 127, f"{name} {part['part']}: the command could not run:\n{output}")
        code, output = run_all()
        self.assertEqual(code, 0, output)  # every mistake is gone again

        # The ticket: its test alone fails a project's verify, through Rail; with the fix it is reviewed and merged.
        edit(work, change["test"][0], "", change["test"][1])
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed["reason"]["code"], "STEP_FAILED", failed)
        self.assertEqual([(s["step"].split(":")[0], s["result"]) for s in failed["steps"] if s.get("result") == "fail"],
                         [("verify", "fail")], failed["steps"])
        for key in ("fix", "fix_too"):
            if key in change:
                edit(work, *change[key])
        p.queue_reviews({"summary": "Clean.", "findings": []})
        shipped = p.rail("advance", "1")
        checked = [s for s in shipped["steps"] if s["step"].split(":")[0] == "verify"]
        self.assertTrue(len(checked) > 1 and all(s["result"] == "pass" for s in checked), shipped["steps"])
        self.assertEqual(step(shipped, "checks")["result"], "pass", shipped["steps"])
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertIn(change["fix"][2].strip().splitlines()[-1].strip(), p.git("show", f"main:{change['fix'][0]}"))
        self.assertEqual(p.git("show", f"main:{change['test'][0]}"), change["test"][1])
        if left:
            # A project that a ticket adds gets every part of its profile's verify, so the rest needs every tool.
            if report:
                with open(report, "a") as f:
                    f.write(f"{name}: the steps after the first ticket were not run, for the same tools\n")
            return
        self.later(p, name)

    def take(self, p, text, tier="AUTO"):
        """File a ticket and claim it. Returns (its id, the claim's answer, its worktree)."""
        added = p.add(text)
        self.assertEqual(added["tier"], tier, added)
        nn = added["ticket"]
        claimed = p.rail("next", "--ticket", nn)
        self.assertEqual((claimed["ticket"], claimed["reason"]["code"]), (nn, "IMPLEMENT"), claimed)
        return nn, claimed, p.worktree(nn)

    def merge(self, p, nn):
        done = p.rail("advance", nn)
        self.assertEqual(done["state"], "merged", done)

    def journal(self, p, nn, kind):
        rows = [json.loads(line) for line in p.git("show", f"main:.rail/journal/{nn}-events.jsonl").splitlines()]
        return [e for e in rows if e["event"] == kind]

    def later(self, p, name):
        """The steps after the first ticket, each a ticket of its own (the class says which)."""
        more = MORE[name]
        first, home, second = more["first"], more["home"], more["second"]

        # 3. A second project in a new folder, which uses the first: found from its manifest, with nothing written
        # for it, and set up and checked in the ship that adds it.
        folder = second["name"].split("/")[0]
        known = f"| {folder}/** |" in read(p.path("ARCHITECTURE.md"))
        nn, _, work = self.take(p, card("Count the notes", (*second["scope"], "ARCHITECTURE.md"), second["check"],
                                        "Nothing says how many notes are open and how many are done."))
        if not known:
            area(work, folder, "`report`, which counts the notes that are done and open")
        for path, text in second["files"].items():
            edit(work, path, "", text)
        for change in second["edits"]:
            edit(work, *change)
        if second["lock"]:
            code, output = shell(second["lock"], work)
            self.assertEqual(code, 0, output)
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", nn)
        self.assertIn(second["name"], ran(shipped, "setup"), shipped["steps"])
        self.assertIn(second["name"], ran(shipped, "verify"), shipped["steps"])
        self.merge(p, nn)
        self.assertNotIn("\n[[projects]]", read(p.path(".rail/config.toml")))
        shown = {s["step"]: s["detail"] for s in p.rail("doctor", expect=None)["steps"]}
        self.assertIn(f"uses {first}", shown[f"project {second['name']}"])

        # 4. A change that drops behaviour and edits the test that held it: the base's version of the test fails on
        # the new code, one question is raised, and answered `lost` the ticket is the worker's again.
        untrim = more["untrim"]
        nn, _, work = self.take(p, card("Say what a title may hold", (*PROJECTS[name]["ticket"]["scope"], home + "TITLES.md"),
                                        f"test -f {home}TITLES.md",
                                        "Nobody can read anywhere what a note's title may hold."))
        edit(work, home + "TITLES.md", "", "# Titles\n\nA title is any text but spaces alone.\n")
        for change in (*untrim["code"], untrim["test"]):
            edit(work, *change)
        p.queue_reviews(said("lost", "A title keeps the spaces around it now, and the ticket asks for a page of words."))
        back = p.rail("advance", nn, expect=3)
        self.assertEqual((back["state"], back["reason"]["code"], back["steps"][-1]["detail"]),
                         ("implementing", "STEP_FAILED", "Q1 old-test: lost"), back)
        for path, old, new in (*untrim["code"], untrim["test"]):
            edit(work, path, new, old)  # the behaviour and its test, as they were
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", nn)
        # A change to the first project runs its checks and those of the project that uses it.
        self.assertLessEqual({first, second["name"]}, set(ran(shipped, "verify")), shipped["steps"])
        self.merge(p, nn)
        (asked,) = self.journal(p, nn, "question")
        self.assertEqual((asked["type"], asked["key"]), ("old-test", untrim["test"][0]))

        # 5. A ticket on a path of a kind: built with no wait, and merged by a person's one act.
        nn, _, work = self.take(p, card("Say when a push reaches main", (".github/workflows/**",),
                                        "test -f .github/workflows/push.yml", "Nothing runs on a push to main."),
                                tier="PERSON")
        edit(work, ".github/workflows/push.yml", "", PUSH)
        p.queue_reviews(CLEAN, CLEAN)  # the reviewer, and the security seat a PERSON ticket still gets
        ready = p.rail("advance", nn)
        self.assertEqual((ready["owner"], ready["reason"]["code"]), ("person", "MERGE_BY_PERSON"), ready)
        self.assertEqual(ready["action"]["facts"]["wait"], {"kind": "approval", "accept": f"rail accept {nn}"})
        p.rail("accept", nn)
        self.merge(p, nn)
        (accepted,) = self.journal(p, nn, "accepted")
        self.assertEqual((accepted["by"], accepted["tier"], accepted["kinds"]), ("engine", "PERSON", ["runs-with-secrets"]))

        # 6. A ticket that fails the same way until the cap: one diagnosis, and answered `approach` it starts again
        # from the base branch and merges.
        nn, _, work = self.take(p, card("Say how a note is finished", (home + "FINISHING.md", home + "FINISHED.md"),
                                        f"test -f {home}FINISHING.md",
                                        "Nobody can read anywhere how a note is finished."))
        edit(work, home + "FINISHED.md", "", "# Finishing\n\nA note is finished by its number.\n")  # the wrong name
        for _ in range(configmod.load(p.root)["retry"]["cap"] + 1):
            stuck = p.rail("advance", nn, expect=None)
            if stuck["reason"]["code"] == "DIAGNOSE":
                break
            self.assertEqual((stuck["reason"]["code"], failed(stuck)), ("STEP_FAILED", ["checks"]), stuck)
        self.assertEqual(stuck["reason"]["code"], "DIAGNOSE", stuck)
        p.queue_reviews(said("approach", evidence="Each attempt writes FINISHED.md. The check asks for FINISHING.md."))
        again = p.rail("next", "--ticket", nn)
        self.assertEqual((again["reason"]["code"], again["action"]["facts"]["restarted"]["type"]), ("IMPLEMENT", "stuck"), again)
        work = p.worktree(nn)
        self.assertFalse(os.path.exists(os.path.join(work, home + "FINISHED.md")))  # none of the attempts' work
        edit(work, home + "FINISHING.md", "", "# Finishing\n\nA note is finished by its number.\n")
        p.queue_reviews(CLEAN)
        p.rail("advance", nn)
        self.merge(p, nn)

        # 7. A folder that no check reads. Where the sample's project is the repository's root, every folder is that
        # project's and nothing is asked. Where it is not, one question is raised, and answered `needs-checks` a
        # PERSON ticket is filed that writes the folder's checks.
        nn, _, work = self.take(p, card("Add the export bucket", ("infra/**", "ARCHITECTURE.md"), "test -f infra/main.tf",
                                        "The export has no bucket to write to."))
        edit(work, "infra/main.tf", "", TF)
        area(work, "infra", "the bucket the export writes to")
        rooted = first == "root"
        p.queue_reviews(*([] if rooted else [said("needs-checks", evidence="Terraform that declares the export bucket.")]),
                        CLEAN)
        shipped = p.rail("advance", nn)
        covers = [s["detail"] for s in shipped["steps"] if s["step"] == "intake"]
        self.merge(p, nn)
        if rooted:
            self.assertEqual((covers, self.journal(p, nn, "question")), ([], []))
        else:
            (asked,) = self.journal(p, nn, "question")
            self.assertEqual((asked["type"], asked["fact"]["folder"]), ("uncovered", "infra"))
            filed = str(int(nn) + 1)
            self.assertEqual(covers, [f"ticket {filed} covers infra"])
            row = next(t for t in p.rail("status")["tickets"] if t["ticket"] == filed)
            self.assertEqual(row["tier"], "PERSON", row)
            self.assertIn('external_id = "coverage:infra"', p.git("show", f"{row['branch']}:.rail/tickets/{filed}.md"))

        # 8. The product. A person says how it is started and which surface users reach; a change to a project of
        # that surface starts, seeds, drives and stops it, and with the sample's fault switched on the step fails.
        surface, kind, reached = more["surface"]
        shutil.copytree(os.path.join(HERE, "projects", "checks"), p.path(".rail", "checks"))
        with open(p.path(".rail", "checks", "product.json"), "w") as f:
            json.dump(more["product"], f)
        starts = ('\n[product]\nstart = "python3 .rail/checks/start.py"\nready = "python3 .rail/checks/ready.py"\n'
                  'seed = "python3 .rail/checks/seed.py"\nstop = "python3 .rail/checks/stop.py"\nready_secs = 120\n'
                  if "start" in more["product"] else "")
        with open(p.path(".rail/config.toml"), "a") as f:
            f.write(f'{starts}\n[[surfaces]]\nname = "{surface}"\nkind = "{kind}"\nprojects = ["{reached}"]\n'
                    f'check = ".rail/checks/{kind}.py"\n')
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "say how the product is started and driven")
        drive = more["drive"]
        nn, _, work = self.take(p, card("Say what the list holds", (drive + "LISTING.md",), f"test -f {drive}LISTING.md",
                                        "Nobody can read anywhere what the list of notes holds."))
        edit(work, drive + "LISTING.md", "", "# The list\n\nEvery note, in the order it was added.\n")
        broken = p.rail("advance", nn, expect=3, env_extra={"RAIL_TEST_PLANT": "1"})
        self.assertEqual((broken["reason"]["code"], failed(broken)), ("STEP_FAILED", [f"product:{surface}"]), broken)
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", nn)
        self.assertEqual([(s["step"], s["result"]) for s in shipped["steps"] if s["step"].split(":")[0] == "product"],
                         [("product", "pass"), (f"product:{surface}", "pass")], shipped["steps"])
        self.merge(p, nn)
        # What the check wrote down is kept with the ticket, for the reviewer and for a person.
        (kept,) = json.loads(p.git("show", f"main:.rail/journal/{nn}-evidence.json")).values()
        self.assertIn("write the report", "".join(kept[surface]["files"].values()))

        # 9. The numbers of all of it.
        stats = p.rail("stats")
        data, text = stats["stats"], stats["text"]
        self.assertEqual(data["merged"], 7)
        self.assertEqual((data["tiers"]["AUTO"]["merged"], data["tiers"]["PERSON"]["merged"]), (6, 1))
        held = data["person_changed_nothing"]["runs-with-secrets"]
        self.assertEqual((held["tickets"], held["changed_nothing"]), (1, 1))
        asked = {"old-test": {"lost": 1}, "stuck": {"approach": 1}, **({} if rooted else {"uncovered": {"needs-checks": 1}})}
        self.assertEqual({kind: (row["questions"], row["answers"]) for kind, row in data["triage"].items()},
                         {kind: (1, answers) for kind, answers in asked.items()})
        self.assertEqual(data["stuck"], {"diagnosed": 1, "answers": {"approach": 1}, "merged_after": 1})
        self.assertEqual(data["driving"], {surface: {"tickets": 1, "runs": 2, "failed": 1, "share": 0.5}})
        # A split shows a group of five tickets or more. Every ticket reaches a project that is the repository's
        # root; no crate of the Rust workspace is reached by five, so there the split is by language alone.
        split = data["outcomes"]["by_project"]
        if rooted:
            self.assertEqual(split[first]["merged"], 7, split)
            self.assertIn("BY PROJECT", text)
        else:
            self.assertEqual((split, data["outcomes"]["by_profile"][name]["merged"]), ({}, 5))
        for line in ("DRIVING CHECKS", "old-test: lost 1 (100%).", "stuck: approach 1 (100%).",
                     "Stuck tickets that got a diagnosis: 1 (approach 1).", "runs-with-secrets 1 of 1"):
            self.assertIn(line, text)

    def test_a_python_service_a_typescript_app_and_a_library_both_use(self):
        """tests/projects/shop: a uv workspace and a pnpm workspace that share `lib`. From rail init to a merged
        ticket in the library, which runs the library's checks and both users', with the members' own commands."""
        missing = [tool for tool in ("uv", "node", "pnpm") if not have(tool)]
        if missing:
            said = f"the shop project needs {', '.join(missing)} on this machine"
            self.fail(said) if STRICT else self.skipTest(said)
        p = Fixture(os.path.join(self.tmp, "shop"), tree=os.path.join(HERE, "projects", "shop"), init=False)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertIn("found api (python, uv), lib-python (python, uv), lib-typescript (typescript, pnpm),"
                      " web (typescript, pnpm). ", step(done, "projects")["detail"])
        text = read(p.path(".rail/config.toml"))
        found, left = initmod.found(p.root), []
        for f in found:  # as in `project`: a part whose tool this machine lacks is left out, and said
            here = [part for part in f["parts"] if have(part["tool"])]
            left += [f"shop {f['name']} {part['part']} ({part['tool']})" for part in f["parts"] if part not in here]
            if len(here) < len(f["parts"]):
                verify = " && ".join(part["run"] for part in here)
                text += f'\n[[projects]]\nname = "{f["name"]}"\nverify = {initmod.toml_string(verify)}\n'
        secrets = profile("common")["secrets"]
        if not have(secrets["tool"]):
            left.append(f"shop secrets ({secrets['tool']})")
            text = text.replace(f"verify = {initmod.toml_string(secrets['run'])}", 'verify = ""')
        report = os.environ.get("RAIL_LANGUAGES_REPORT")
        if report and left:
            with open(report, "a") as f:
                f.write(f"shop: not run, the tool is not on this machine: {', '.join(left)}\n")
        p.write(".rail/config.toml", stand_ins(text))
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "set up Rail")

        everyone = ["lib-python", "api", "lib-typescript", "web"]
        ran = lambda answer, family: [s["step"].split(":")[1] for s in answer["steps"]  # noqa: E731
                                      if s["step"].startswith(family + ":") and s.get("result") == "pass"]
        p.add('+++\ntitle = "Refuse a negative price"\ntier = "AUTO"\nscope_paths = ["lib/src/**", "lib/tests/**"]\n+++\n\n'
              "## Why\nA negative price lowers the total of a cart, and nothing refuses it.\n\n"
              "## Done Contract\n- Check: `cd lib && uv run pytest -q tests/test_negative.py`\n")
        claimed = p.rail("next")
        self.assertEqual((claimed["ticket"], claimed["reason"]["code"]), ("1", "IMPLEMENT"), claimed)
        self.assertEqual(ran(claimed, "setup"), everyone, claimed["steps"])  # the library, then both of its users
        work = p.worktree("1")
        edit(work, "lib/tests/test_negative.py", "", "import unittest\n\nfrom shop_lib.money import total\n\n\n"
             "class NegativeTest(unittest.TestCase):\n    def test_a_negative_price_is_refused(self) -> None:\n"
             "        with self.assertRaises(ValueError):\n            total([250, -100])\n")
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual([(s["step"], s["result"]) for s in failed["steps"] if s.get("result") == "fail"],
                         [("verify:lib-python", "fail")], failed["steps"])
        edit(work, "lib/src/shop_lib/money.py", "    return sum(prices)\n",
             '    if any(price < 0 for price in prices):\n        raise ValueError("a price is negative")\n    return sum(prices)\n')
        p.queue_reviews({"summary": "Clean.", "findings": []})
        shipped = p.rail("advance", "1")
        self.assertEqual(ran(shipped, "verify"), everyone, shipped["steps"])
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertIn("a price is negative", p.git("show", "main:lib/src/shop_lib/money.py"))

    def test_python(self):
        self.project("python")

    def test_typescript(self):
        self.project("typescript")

    def test_rust(self):
        self.project("rust")

    def test_go(self):
        self.project("go")
