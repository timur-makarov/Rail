"""Language profiles: rail init finds Python, TypeScript, Rust and Go from tracked manifests and writes each
profile's rules, paths and sandbox domains."""

import json
import os
import subprocess
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RAIL, Fixture, RailTest, ticket  # noqa: E402

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
                         "found python (**), typescript (web/**); wrote each to .rail/config.toml with its rules,"
                         " migration paths, generated files and [tests] paths")
        with open(p.path(".rail/config.toml"), "rb") as f:
            config = tomllib.load(f)
        self.assertEqual(config["profiles"], [{"name": "python", "paths": "**"}, {"name": "typescript", "paths": "web/**"}])
        self.assertEqual(config["migration_paths"], ["**/migrations/**", "**/alembic/versions/**", "**/drizzle/**"])
        self.assertEqual(config["size"]["exclude"], ["**/*_pb2.py", "**/*_pb2_grpc.py"])
        self.assertEqual(config["tests"]["paths"], profile("python")["tests"] + profile("typescript")["tests"])
        ids = [r["id"] for r in config["rules"]]
        self.assertEqual(ids, ["no-new-suppressions", "shortcut-names-its-ticket", "no-new-python-suppressions",
                               "no-new-typescript-suppressions"])
        self.assertEqual(config["rules"][2], profile("python")["rules"][0])
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
        for folder in profile("common")["ignore"]:
            self.assertIn(f"`{folder}`", page)
