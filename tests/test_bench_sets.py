"""The project files of set 2026-12 and the arms of the first run load as the bench reads them, with no model and no
network: every file passes the loader, its commands are bash that parses, and the arms give Rail what PLAN section 6
says."""

import glob
import os
import subprocess
import unittest

from benchtest import ROOT

from bench import arms, common, rail_install, sets

SET = os.path.join(ROOT, "bench", "sets", "2026-12")
PROPOSED = {"ha-core": "python", "pandas": "python", "vue-core": "typescript", "typescript-eslint": "typescript",
            "turso": "rust", "nushell": "rust", "caddy": "go", "typescript-go": "go"}
RESERVES = {"sqlfluff": "python", "marimo": "python", "vitest": "typescript", "svelte": "typescript", "ruff": "rust",
            "rolldown": "rust", "rclone": "go", "tailscale": "go"}
LADDER = ["claude-sonnet-5-5:medium", "claude-opus-5-5:medium"]


def project_files():
    return sorted(p for p in glob.glob(os.path.join(SET, "*.toml")) if os.path.basename(p) != "CHOSEN.toml")


def bash_parses(command):
    done = subprocess.run(["bash", "-n", "-c", command], capture_output=True, text=True)
    return done.returncode == 0, done.stderr


class SetFiles(unittest.TestCase):
    def test_sixteen_project_files_two_proposed_and_two_reserves_per_language(self):
        names = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(SET, "*.toml"))
                       if os.path.basename(p) != "CHOSEN.toml")
        self.assertEqual(names, sorted({**PROPOSED, **RESERVES}))
        for name, language in {**PROPOSED, **RESERVES}.items():
            with self.subTest(project=name):
                p = sets.load(os.path.join(SET, f"{name}.toml"))
                self.assertEqual((p.name, p.language, p.set), (name, language, "2026-12"))
                self.assertTrue(p.slug and p.package, "the taint search needs the slug and the package")
                self.assertGreaterEqual(len(p.situations), 20)
                self.assertLessEqual(len(p.situations), 45)

    def test_every_situation_carries_what_the_taint_search_and_the_report_read(self):
        for path in project_files():
            p = sets.load(path)
            for s in p.situations:
                with self.subTest(situation=s.id):
                    self.assertTrue(s.id.startswith(p.name + "-"))
                    self.assertRegex(s.issue, rf"^https://github\.com/{p.slug}/issues/\d+$")
                    self.assertGreater(s.pull, 0)
                    self.assertRegex(s.start, r"^[0-9a-f]{40}$")
                    self.assertRegex(s.fix, r"^[0-9a-f]{40}$")
                    self.assertTrue(s.title and s.body)
                    self.assertIn(s.half, ("work", "held"))  # the split comes after admission and the hardness runs
                    self.assertGreaterEqual(s.closed.isoformat(), "2026-07-01")
                    for flag in ("self_filed", "bot_filed", "security_trap"):
                        self.assertIsInstance(getattr(s, flag), bool)

    def test_the_commands_are_bash_that_parses_and_the_failure_pattern_is_a_regex(self):
        for path in project_files():
            p = sets.load(path)
            commands = {"setup": p.commands["setup"],
                        "test_files": p.test_files_command(p.situations[0].hidden_tests),
                        "test_package": p.test_package_command("."),
                        "rail setup": p.rail_config["commands"]["setup"],
                        "rail verify": p.rail_config["commands"]["verify"]}
            for name, command in commands.items():
                with self.subTest(project=p.name, command=name):
                    ok, err = bash_parses(command)
                    self.assertTrue(ok, err)

    def test_rail_gets_the_two_rung_ladder_and_a_stale_limit_above_its_longest_command(self):
        for path in project_files():
            p = sets.load(path)
            with self.subTest(project=p.name):
                self.assertEqual(p.rail_config["worker"]["ladder"], LADDER)
                c = p.rail_config["commands"]
                longest = max(c.get("timeout_secs", 900), c.get("setup_timeout_secs", 0),
                              c.get("verify_timeout_secs", 0))
                self.assertGreater(p.rail_config["claim"]["stale_minutes"] * 60, longest + 600)
                self.assertTrue(c["setup"].strip() and c["verify"].strip())

    def test_a_flag_of_the_wrong_type_is_refused(self):
        path = os.path.join(SET, "caddy.toml")
        with open(path) as f:
            text = f.read()
        bad = os.path.join(self.tmp_dir(), "2026-12", "caddy.toml")
        os.makedirs(os.path.dirname(bad))
        with open(bad, "w") as f:
            f.write(text.replace("self_filed = false", 'self_filed = "no"', 1))
        with self.assertRaises(common.BenchError) as e:
            sets.load(bad)
        self.assertIn("self_filed", str(e.exception))

    def tmp_dir(self):
        import shutil
        import tempfile
        d = tempfile.mkdtemp(prefix="bench-sets-")
        self.addCleanup(shutil.rmtree, d, True)
        return d


class CloudScripts(unittest.TestCase):
    def test_each_cloud_script_compiles_and_says_what_it_does(self):
        import ast
        folder = os.path.join(ROOT, "bench", "cloud")
        for path in sorted(glob.glob(os.path.join(folder, "*.py"))):
            with self.subTest(script=os.path.basename(path)):
                with open(path) as f:
                    tree = ast.parse(f.read())
                self.assertTrue(ast.get_docstring(tree))
        ok, err = bash_parses(open(os.path.join(folder, "killtree.sh")).read())
        self.assertTrue(ok, err)


class FirstRunArms(unittest.TestCase):
    CONF = dict(common.DEFAULTS)

    def test_the_rail_arm_keeps_the_project_ladder_and_sets_the_other_roles(self):
        arm = arms.load("rail-ladder")
        self.assertFalse(arm.plain)
        over = arm.rail_overrides(self.CONF)
        self.assertNotIn("ladder", over["worker"])
        self.assertEqual(over["worker"]["contract"], "claude-opus-5-5:high")
        self.assertEqual(over["review"], {"model": "claude-opus-5-5"})
        self.assertEqual(over["consult"], {"model": "claude-fable-5-2"})
        self.assertIn("--tools " + self.CONF["tools"], over["worker"]["command"])
        self.assertIn("--max-budget-usd " + str(self.CONF["budget_usd"]), over["worker"]["command"])
        project = sets.load(os.path.join(SET, "turso.toml"))
        seed = {"worker": {"ladder": ["seed"], "person_ladder": ["claude-opus-5-5:medium", "claude-opus-5-5:high"]},
                "review": {"command": "seed review --effort high", "model": ""},
                "consult": {"command": "seed consult --effort high", "model": ""}}
        config = rail_install.config_for(project, over, seed)
        self.assertEqual(config["worker"]["ladder"], LADDER)
        self.assertEqual(config["worker"]["person_ladder"], ["claude-opus-5-5:medium", "claude-opus-5-5:high"])
        self.assertEqual(config["review"]["command"], "seed review --effort high")

    def test_the_plain_arms_are_opus_and_haiku_at_medium(self):
        for name, model in (("plain-opus", "claude-opus-5-5"), ("plain-haiku", "claude-haiku-5-5")):
            with self.subTest(arm=name):
                arm = arms.load(name)
                self.assertTrue(arm.plain)
                self.assertEqual((arm.role("worker")["model"], arm.role("worker")["effort"]), (model, "medium"))
                command = arm.command("worker", self.CONF)
                self.assertIn(f"--model {model} --effort medium", command)
                self.assertNotRegex(command, arms.RESUME)


if __name__ == "__main__":
    unittest.main()
