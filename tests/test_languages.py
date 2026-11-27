"""Language profiles: Rail finds the projects of Python, TypeScript, Rust and Go from the tracked manifests, each
time it needs them, and each project gets its profile's commands, rules and paths with nothing written for it
(tests/test_projects.py has what a change reaches). `Projects` takes one small real program per language from rail
init to a merged ticket with the language's own toolchain; it skips a language whose toolchain this machine lacks,
and `python3 tests/run.py --languages` fails there instead."""

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
    """Each language's project from rail init to a merged ticket, with the commands its profile gives it."""

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
