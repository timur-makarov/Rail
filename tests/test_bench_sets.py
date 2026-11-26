"""The arms of the first run and the cloud scripts load as the bench reads them, with no model and no network, and a
situation's three flags are checked."""

import glob
import os
import subprocess
import types
import unittest

from benchtest import ROOT, BenchTest

from bench import arms, common, rail_install

LADDER = ["claude-sonnet-5-5:medium", "claude-opus-5-5:medium"]


def bash_parses(command):
    done = subprocess.run(["bash", "-n", "-c", command], capture_output=True, text=True)
    return done.returncode == 0, done.stderr


class SituationFlags(BenchTest):
    def test_the_three_flags_load_and_default_to_false(self):
        self.edit_project('kind = "crash"', 'kind = "crash"\nself_filed = true')
        flags = [(s.self_filed, s.bot_filed, s.security_trap) for s in self.project().situations]
        self.assertEqual(sum(f[0] for f in flags), 1)
        self.assertFalse(any(f[1] or f[2] for f in flags))

    def test_a_flag_of_the_wrong_type_is_refused(self):
        self.edit_project('kind = "crash"', 'kind = "crash"\nself_filed = "no"')
        with self.assertRaises(common.BenchError) as e:
            self.project()
        self.assertIn("self_filed", str(e.exception))


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
        # A project file sets the two-rung ladder, since an arm can name one rung only.
        project = types.SimpleNamespace(rail_config={"worker": {"ladder": LADDER}})
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
