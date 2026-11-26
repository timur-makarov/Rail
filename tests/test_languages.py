"""Language profiles: rail init finds Python, TypeScript, Rust and Go from tracked manifests and writes each
profile's commands, rules, paths and sandbox domains. `Projects` takes one small real program per language from
rail init to a merged ticket with the language's own toolchain; it skips a language whose toolchain this machine
lacks, and `python3 tests/run.py --languages` fails there instead."""

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
from railtest import CONFIG, FAKE, RAIL, Fixture, RailTest, ticket  # noqa: E402

FRAMEWORK = os.path.dirname(os.path.dirname(RAIL))
sys.path.insert(0, os.path.join(FRAMEWORK, "engine"))
from rail import config as configmod, init as initmod  # noqa: E402
from rail.util import globmatch  # noqa: E402

LANGUAGES = ("go", "python", "rust", "typescript")


def profile(name):
    with open(os.path.join(FRAMEWORK, "profiles", name, "profile.toml"), "rb") as f:
        return tomllib.load(f)


def read(path):
    with open(path) as f:
        return f.read()


def step(answer, name):
    return [s for s in answer["steps"] if s["step"] == name][-1]


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
        return [(f["name"], f["paths"]) for f in initmod.detect(self.repo(files))]

    def test_each_manifest_gives_its_profile(self):
        cases = {"pyproject.toml": "python", "setup.cfg": "python", "requirements-dev.txt": "python",
                 "package.json": "typescript", "Cargo.toml": "rust", "go.mod": "go"}
        for manifest, name in cases.items():
            with self.subTest(manifest):
                self.assertEqual(self.found({manifest: "x\n"}), [(name, "**")])
        self.assertEqual(self.found({"README.md": "x\n", "src/main.c": "x\n"}), [])

    def test_package_json_without_tsconfig_gives_typescript_with_type_checking_off(self):
        [without] = initmod.detect(self.repo({"package.json": "{}\n"}))
        [with_it] = initmod.detect(self.repo({"package.json": "{}\n", "tsconfig.json": "{}\n"}))
        self.assertEqual((without["name"], without["type_check"], with_it["type_check"]), ("typescript", False, True))
        self.assertEqual(initmod._describe([without]), "typescript (**, no tsconfig.json: type checking off)")
        [go] = initmod.detect(self.repo({"go.mod": "module x\n"}))
        self.assertIsNone(go["type_check"])

    def test_manifests_below_the_root_give_their_folders(self):
        self.assertEqual(self.found({"web/package.json": "{}\n", "api/go.mod": "module x\n"}),
                         [("go", "api/**"), ("typescript", "web/**")])
        # The top-most folders only, joined with braces; a manifest at the root takes the whole repository.
        self.assertEqual(self.found({"a/go.mod": "x\n", "a/tool/go.mod": "x\n", "b/c/go.mod": "x\n"}),
                         [("go", "{a,b/c}/**")])
        self.assertEqual(self.found({"pyproject.toml": "x\n", "libs/one/pyproject.toml": "x\n"}), [("python", "**")])

    def test_vendored_installed_built_and_untracked_manifests_give_nothing(self):
        root = self.repo({"node_modules/x/package.json": "{}\n", "vendor/y/go.mod": "x\n", "web/vendor/z/go.mod": "x\n",
                          "target/debug/Cargo.toml": "x\n", ".venv/lib/pyproject.toml": "x\n", "dist/package.json": "x\n"})
        with open(os.path.join(root, "Cargo.toml"), "w") as f:
            f.write("[package]\n")  # not tracked
        self.assertEqual(initmod.detect(root), [])

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
    def test_init_writes_the_profiles_into_a_new_config_and_merges_the_registries(self):
        settings = {"sandbox": {"network": {"allowedDomains": ["example.com"]}}}
        p = Fixture(os.path.join(self.tmp, "mono"), init=False, files={
            "pyproject.toml": "[project]\nname = 'api'\n", "web/package.json": "{}\n", "web/tsconfig.json": "{}\n",
            ".claude/settings.json": json.dumps(settings)})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual(step(done, "profiles")["detail"],
                         "found python (**), typescript (web/**); wrote each to .rail/config.toml with its default"
                         " setup and verify, rules, migration paths, generated files and [tests] paths")
        with open(p.path(".rail/config.toml"), "rb") as f:
            config = tomllib.load(f)
        self.assertEqual(config["profiles"], [{"name": "python", "paths": "**"}, {"name": "typescript", "paths": "web/**"}])
        self.assertEqual(config["migration_paths"], ["**/migrations/**", "**/alembic/versions/**", "**/drizzle/**"])
        self.assertEqual(config["size"]["exclude"], ["**/*_pb2.py", "**/*_pb2_grpc.py"])
        self.assertEqual(config["tests"]["paths"], profile("python")["tests"] + profile("typescript")["tests"])
        # No lockfile is tracked, so each language gets the manager a new project starts with.
        self.assertEqual(config["commands"]["setup"],
                         "uv sync --locked && (cd web && pnpm install --frozen-lockfile --ignore-scripts)")
        self.assertEqual(config["commands"]["verify"].split(" && ")[:2], [
            "uv run ruff format --check --extend-exclude .rail --extend-exclude .claude .",
            "uv run ruff check --extend-exclude .rail --extend-exclude .claude ."])
        brief = p.rail("next")["action"]["brief"]
        self.assertIn("rail init found python (**), typescript (web/**) and wrote each language's default `setup` and"
                      " `verify` into [commands]. The repository's own commands win over a default", brief)
        self.assertIn("rail init found python (**), typescript (web/**)", p.rail("next", cloud=True)["action"]["brief"])
        ids = [r["id"] for r in config["rules"]]
        self.assertEqual(ids, ["no-new-suppressions", "shortcut-names-its-ticket", "sensor-marker-names-its-ticket",
                               "no-new-python-suppressions",
                               "no-new-typescript-suppressions"])
        self.assertEqual(config["rules"][3], profile("python")["rules"][0])
        self.assertIn("\n[tests]", read(p.path(".rail/config.toml")))  # the seed's own comment stays

        domains = json.loads(read(p.path(".claude/settings.json")))["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(domains, ["example.com", "api.anthropic.com", "pypi.org", "files.pythonhosted.org",
                                   "registry.npmjs.org", "registry.yarnpkg.com"])
        self.assertIn("the sandbox allows pypi.org", step(done, ".claude/settings.json")["detail"])
        self.assertEqual(p.rail("status")["reason"]["code"], "STATUS")  # the engine loads what init wrote

        again = p.rail("init")
        self.assertEqual(step(again, ".claude/settings.json")["status"], "not_run")
        self.assertIn(".rail/config.toml was there already", step(again, "profiles")["detail"])

    def test_an_existing_config_is_left_alone_and_the_registries_still_merge(self):
        p = Fixture(os.path.join(self.tmp, "existing"), init=False, files={"go.mod": "module x\n",
                                                                         ".rail/config.toml": CONFIG})
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual(read(p.path(".rail/config.toml")), CONFIG)
        self.assertEqual(step(done, "profiles")["detail"],
                         "found go (**); .rail/config.toml was there already, so nothing was written to it")
        domains = json.loads(read(p.path(".claude/settings.json")))["sandbox"]["network"]["allowedDomains"]
        self.assertEqual(domains, ["api.anthropic.com", "proxy.golang.org", "sum.golang.org"])

    def test_a_repository_in_no_profiles_language_gets_the_seed_config_as_it_is(self):
        p = Fixture(os.path.join(self.tmp, "plain"), init=False)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "start")
        done = p.rail("init")
        self.assertEqual(step(done, "profiles")["status"], "not_run")
        self.assertEqual(read(p.path(".rail/config.toml")), read(os.path.join(FRAMEWORK, "seed", "config.toml")))


class Markers(RailTest):
    def test_each_languages_markers_fail_in_its_own_files_and_not_in_a_markdown_file(self):
        rules = "".join("\n" + initmod._toml_table("rules", rule, name)
                        for name in LANGUAGES for rule in profile(name)["rules"])
        p = self.fixture(config=CONFIG + rules)
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        files = {"go": ["src/a.go"], "python": ["src/a.py"], "rust": ["src/a.rs"],
                 "typescript": ["src/a.ts", "src/b.tsx", "src/c.mjs"]}
        expected, markdown = [], []
        for name in LANGUAGES:
            markers = profile(name)["rules"][0]["forbid"]
            for path in files[name]:
                p.write(path, "".join(f"x = 1  {marker}\n" for marker in markers), base=p.worktree("1"))
                expected += [f"{path} adds '{marker}'" for marker in markers]
            markdown += markers
            # The marker in another language's file breaks nothing.
            other = files[LANGUAGES[(LANGUAGES.index(name) + 1) % 4]][0].replace("src/a", "src/other")
            p.write(other, "".join(f"x = 1  {marker}\n" for marker in markers), base=p.worktree("1"))
        p.write("src/notes.md", "".join(f"Never write {m}\n" for m in markdown), base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        brief = failed["action"]["brief"]
        for line in expected:
            self.assertIn(line, brief)
        self.assertNotIn("notes.md", brief)
        self.assertNotIn("src/other", brief)
        self.assertTrue(step(failed, "rules")["detail"].startswith(f"{len(expected)} broken: "), step(failed, "rules"))


class Data(RailTest):
    def test_every_profile_has_its_keys_and_the_languages_page_names_its_data(self):
        page = read(os.path.join(FRAMEWORK, "engine", "docs", "languages.md"))
        names = sorted(n for n in os.listdir(os.path.join(FRAMEWORK, "profiles")) if n != "common")
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
            # The commands: every manager and its lockfile, and each line of the one a new project starts with.
            first = data["managers"][0]
            for word in [w for m in data["managers"] for w in (m["name"], m["lockfile"])] + [first["setup"]] + \
                    [part["run"].replace("|", "\\|") for part in first["verify"]]:
                self.assertIn(f"`{word}`", page, name)
        for folder in profile("common")["ignore"]:
            self.assertIn(f"`{folder}`", page)
        self.assertIn(f"`{profile('common')['secrets']['run']}`", page)


def tree(root, *paths):
    """A git repository at root that tracks these empty files: what detection reads."""
    os.makedirs(root)
    for path in paths:
        os.makedirs(os.path.dirname(os.path.join(root, path)), exist_ok=True)
        open(os.path.join(root, path), "w").close()
    subprocess.run(["git", "init", "--quiet", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return initmod.detect(root)


class Defaults(RailTest):
    """The commands a new config starts with, from the profiles alone: no toolchain runs here."""

    def test_the_lockfile_names_the_manager_and_each_folder_runs_its_own_commands(self):
        found = tree(os.path.join(self.tmp, "mono"), "api/pyproject.toml", "api/poetry.lock", "web/package.json",
                     "web/package-lock.json", "web/tsconfig.json", "tools/gen/go.mod", "tools/lint/go.mod")
        self.assertEqual([(f["name"], f["dirs"], f["manager"]["name"]) for f in found],
                         [("go", ["tools/gen", "tools/lint"], "go"), ("python", ["api"], "poetry"),
                          ("typescript", ["web"], "npm")])
        setup, verify, left = initmod.default_commands(found)
        self.assertEqual(setup, "(cd tools/gen && go mod download) && (cd tools/lint && go mod download)"
                                " && (cd api && poetry install) && (cd web && npm ci --ignore-scripts)")
        self.assertEqual(left, [])
        # A part runs in its folder, and a language in two folders runs each part in both.
        self.assertTrue(verify.startswith('(cd tools/gen && test -z "$(gofmt -l .)") && (cd tools/gen && go vet ./...)'))
        self.assertIn('(cd tools/lint && test -z "$(gofmt -l .)")', verify)
        self.assertIn("(cd api && poetry run pytest -q)", verify)
        self.assertIn("(cd web && npx --no-install tsc --noEmit)", verify)
        # An audit runs only on a change that touches the folder's lockfile.
        self.assertIn('{ git diff --quiet "$RAIL_BASE"...HEAD -- web/package-lock.json || (cd web && npm audit); }', verify)
        self.assertIn('{ git diff --quiet "$RAIL_BASE"...HEAD -- tools/gen/go.sum || (cd tools/gen && govulncheck ./...); }',
                      verify)
        # One secret scan over the branch's commits, after every language.
        self.assertTrue(verify.endswith(' && gitleaks git --no-banner --log-opts="$RAIL_BASE..HEAD"'), verify)

    def test_types_are_left_out_where_type_checking_is_off_and_a_missing_tool_is_named(self):
        found = tree(os.path.join(self.tmp, "js"), "package.json", "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock")
        self.assertEqual([(f["name"], f["type_check"]) for f in found], [("rust", None), ("typescript", False)])
        _, parts, left = initmod.default_parts(found)
        self.assertEqual([(p["profile"], p["part"], p["tool"]) for p in parts], [
            ("rust", "format", "rustfmt"), ("rust", "lint", "cargo-clippy"), ("rust", "tests", "cargo"),
            ("rust", "audit", "cargo-deny"), ("typescript", "lint", "oxlint"), ("typescript", "tests", "pnpm"),
            ("typescript", "audit", "pnpm"), ("common", "secrets", "gitleaks")])
        self.assertEqual(left, [])
        setup, verify, left = initmod.default_commands(found, available=lambda tool: tool in ("cargo", "pnpm"))
        self.assertEqual(setup, "cargo fetch --locked && pnpm install --frozen-lockfile --ignore-scripts")
        self.assertEqual(verify, 'cargo test --locked && pnpm test && { git diff --quiet "$RAIL_BASE"...HEAD --'
                                 ' pnpm-lock.yaml || pnpm audit; }')
        self.assertEqual(left, ["rust format (rustfmt)", "rust lint (cargo-clippy)", "rust audit (cargo-deny)",
                                "typescript lint (oxlint)", "secrets (gitleaks)"])

    def test_every_default_is_a_command_the_config_can_hold(self):
        for name in LANGUAGES:
            for manager in profile(name)["managers"]:
                self.assertTrue(manager["name"] and manager["lockfile"] and manager["setup"], name)
                self.assertLessEqual({p["part"] for p in manager["verify"]}, {"format", "lint", "types", "tests", "audit"})
                for part in manager["verify"]:
                    self.assertEqual(sorted(part), ["part", "run", "tool"], name)
                    self.assertEqual(tomllib.loads("x = " + initmod.toml_string(part["run"]))["x"], part["run"])


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
            "test": ("tests/test_trim.py", '''import pytest

from notes.store import Store


def test_the_spaces_around_a_title_are_dropped():
    assert Store().add("  write the report ")["title"] == "write the report"


def test_a_title_of_only_spaces_is_refused():
    with pytest.raises(ValueError):
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


def edit(root, path, old, new):
    full = os.path.join(root, path)
    text = read(full) if os.path.exists(full) else ""
    if old and old not in text:
        raise AssertionError(f"{path} doesn't hold {old!r}")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text.replace(old, new, 1) if old else text + new)


class Projects(RailTest):
    """Each language's project from rail init to a merged ticket, with the profile's own commands."""

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
        self.assertIn(f"found {name} (**); wrote each to .rail/config.toml with its default setup and verify",
                      step(done, "profiles")["detail"])
        found = initmod.detect(p.root)
        setup, verify, _ = initmod.default_commands(found)
        text = read(p.path(".rail/config.toml"))
        written = tomllib.loads(text)["commands"]
        self.assertEqual((written["setup"], written["verify"]), (setup, verify))
        brief = p.rail("next")["action"]["brief"]
        self.assertIn(f"rail init found {name} (**) and wrote each language's default `setup` and `verify`", brief)
        self.assertIn("The repository's own commands win over a default", brief)

        # What the init task leaves on this machine: the parts whose tools are here, and Rail's stand-in reviewer.
        setup, parts, left = initmod.default_parts(found, available=have)
        report = os.environ.get("RAIL_LANGUAGES_REPORT")
        if report and left:
            with open(report, "a") as f:
                f.write(f"{name}: not run, the tool is not on this machine: {', '.join(left)}\n")
        here = " && ".join(part["run"] for part in parts)
        text = text.replace(f"verify = {initmod.toml_string(verify)}", f"verify = {initmod.toml_string(here)}")
        text, swapped = re.subn(r"(?m)^command = '''claude -p --safe-mode .*--json-schema.*$",
                                f'command = "python3 {FAKE}"', text)
        self.assertEqual(swapped, 1)
        p.write(".rail/config.toml", text)
        p.git("add", "-A")
        p.git("commit", "--quiet", "-m", "set up Rail")

        change = spec["ticket"]
        scope = ", ".join(f'"{s}"' for s in change["scope"])
        p.add(f'+++\ntitle = "Trim note titles"\ntier = "AUTO"\nscope_paths = [{scope}]\n+++\n\n## Why\n'
              "A title keeps the spaces typed around it, and a title of only spaces is taken as a note.\n\n"
              f"## Done Contract\n- Check: `{change['check']}`\n")
        claimed = p.rail("next")
        self.assertEqual((claimed["ticket"], claimed["reason"]["code"]), ("1", "IMPLEMENT"), claimed)
        self.assertEqual(step(claimed, "setup")["result"], "pass", claimed["steps"])  # the profile's setup, run by Rail
        work = p.worktree("1")

        # verify passes on the untouched project, and each part catches the mistake made for it.
        code, output = shell(here, work)
        self.assertEqual(code, 0, output)
        for part in parts:
            mistake = spec["mistakes"].get((part["part"], part["tool"]))
            if part["part"] == "secrets":
                edit(work, "deploy.pem", "", fake_key())
                subprocess.run("git add -A && git commit --quiet -m 'add a key'", shell=True, cwd=work, check=True)
                code, output = shell(part["run"], work)
                subprocess.run(["git", "reset", "--quiet", "--hard", "HEAD~1"], cwd=work, check=True)
            elif mistake:
                edit(work, *mistake)
                code, output = shell(part["run"], work)
                subprocess.run("git checkout --quiet -- . && git clean --quiet -fd", shell=True, cwd=work, check=True)
            else:
                continue  # an audit: these projects have no dependency to pin to a version with an advisory
            self.assertNotEqual(code, 0, f"{name} {part['part']} ({part['tool']}) passed a planted mistake:\n{output}")
            self.assertNotEqual(code, 127, f"{name} {part['part']}: the command could not run:\n{output}")
        code, output = shell(here, work)
        self.assertEqual(code, 0, output)  # every mistake is gone again

        # The ticket: its test alone fails verify, through Rail; with the fix it is reviewed and merged.
        edit(work, change["test"][0], "", change["test"][1])
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual((failed["reason"]["code"], step(failed, "verify")["result"]), ("STEP_FAILED", "fail"), failed)
        for key in ("fix", "fix_too"):
            if key in change:
                edit(work, *change[key])
        p.queue_reviews({"summary": "Clean.", "findings": []})
        shipped = p.rail("advance", "1")
        self.assertEqual(step(shipped, "verify")["result"], "pass", shipped["steps"])
        self.assertEqual(step(shipped, "checks")["result"], "pass", shipped["steps"])
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        self.assertIn(change["fix"][2].strip().splitlines()[-1].strip(), p.git("show", f"main:{change['fix'][0]}"))
        self.assertEqual(p.git("show", f"main:{change['test'][0]}"), change["test"][1])

    def test_python(self):
        self.project("python")

    def test_typescript(self):
        self.project("typescript")

    def test_rust(self):
        self.project("rust")

    def test_go(self):
        self.project("go")
