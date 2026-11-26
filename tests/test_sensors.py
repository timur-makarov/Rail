"""Sensors: a tool's output lines fail the ship when they are on lines the change adds."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, RailTest, ticket

# The stand-in tool: it reports every line under src/ that holds one of the words its config lists, as a linter
# reports violations, and reads that config where the engine says the base branch's copy is.
FIND = '''import os
import sys

with open(os.path.join(os.environ["RAIL_SENSORS"], "words.txt")) as f:
    words = f.read().split()
found = 0
for root, _, names in os.walk("src"):
    for name in sorted(n for n in names if n.endswith(".py")):
        path = os.path.join(root, name)
        with open(path) as f:
            for n, line in enumerate(f, 1):
                for word in words:
                    if word in line:
                        print(f"\\x1b[31m./{path}:{n}:7: the word {word}\\x1b[0m")
                        found += 1
print(f"{found} found")
sys.exit(int(os.environ.get("TOOL_EXIT", "1")) if found else 0)
'''
SENSOR = '''
[[sensors]]
id = "words"
paths = ["src/**"]
command = 'python3 "$RAIL_SENSORS/find.py"'
fix = "Say it another way."

'''
LEGACY = ("def add(a, b):\n    return a - b\n\n\ndef legacy_total_of_everything(values):\n"
          "    # FIXME: this walks the whole list of values twice\n    return sum(values) + len(values) * 0\n")
FIXED = LEGACY.replace("return a - b", "return a + b")
CLEAN = {"summary": "Clean.", "findings": []}
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seed", "config.toml")) as f:
    MARKER_RULE = "\n[[rules]]\n" + f.read().split("[[rules]]")[3]  # the seed's third rule, as it ships


def step(answer, name):
    return [s for s in answer["steps"] if s["step"] == name][-1]


class Sensors(RailTest):
    def project(self, sensor=SENSOR, **files):
        return self.fixture(config=CONFIG + sensor, files={
            ".rail/sensors/find.py": FIND, ".rail/sensors/words.txt": "FIXME\n", "src/calc.py": LEGACY, **files})

    def claimed(self, p=None, **kw):
        p = p or self.project()
        p.add(ticket(**kw))
        p.rail("next")
        return p

    def test_a_violation_on_an_added_line_fails_and_old_code_never_does(self):
        p = self.claimed()
        work = p.worktree("1")
        # The base already holds a FIXME, on a line this change leaves alone: the sensor reports it, and it fails nothing.
        p.write("src/calc.py", FIXED, base=work)
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "1")
        self.assertEqual(step(shipped, "sensors"), {"step": "sensors", "status": "ran", "result": "pass"})
        self.assertEqual(shipped["steps"][[s["step"] for s in shipped["steps"]].index("checks") + 1]["step"], "sensors")

        p.add(ticket(title="More", check="grep -q more src/calc.py"))
        p.rail("advance", "1")
        p.rail("next")
        p.write("src/calc.py", FIXED + "\n\ndef more():\n    return 1  # FIXME later\n", base=p.worktree("2"))
        failed = p.rail("advance", "2", expect=3)
        self.assertEqual(step(failed, "sensors"), {"step": "sensors", "status": "ran", "result": "fail",
                                                   "detail": "1 violations: words"})
        brief = failed["action"]["brief"]
        self.assertIn("src/calc.py:11: the word FIXME. Sensor words: Say it another way.", brief)  # no colour codes
        self.assertNotIn("src/calc.py:6", brief)
        self.assertIn("SENSOR(2): the reason", brief)
        # It counts like any failed step: rail next gives the same failure again.
        again = p.rail("next", "--ticket", "2")
        self.assertEqual(again["reason"]["code"], "STEP_FAILED")
        self.assertIn("failed at 'sensors': 1 violations: words", again["action"]["brief"])

    def test_code_that_only_moved_is_not_new(self):
        p = self.claimed(check="grep -q legacy src/old.py")
        work = p.worktree("1")
        moved = LEGACY.split("\n\n\n")[1]
        p.write("src/calc.py", "def add(a, b):\n    return a + b\n", base=work)
        p.write("src/old.py", moved, base=work)
        p.queue_reviews(CLEAN)
        self.assertEqual(step(p.rail("advance", "1"), "sensors")["result"], "pass")

    def test_code_that_was_copied_is_new(self):
        p = self.claimed(check="grep -q legacy src/old.py")
        work = p.worktree("1")
        p.write("src/calc.py", FIXED, base=work)
        p.write("src/old.py", LEGACY.split("\n\n\n")[1], base=work)  # the same block, and the first copy stays
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "sensors")["detail"], "1 violations: words")
        self.assertIn("src/old.py:2: the word FIXME", failed["action"]["brief"])

    def test_a_marker_with_the_tickets_number_answers_a_violation_and_the_reviewer_is_told(self):
        p = self.claimed()
        work = p.worktree("1")
        p.write("src/calc.py", FIXED + "\n\n# SENSOR(1): the word is the name of the upstream field\nFIXME_FIELD = 'x'\n"
                               "OTHER = 'FIXME'  # SENSOR(1): quoted from the vendor's file\n", base=work)
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "1")
        self.assertEqual(step(shipped, "sensors")["result"], "pass")
        brief = p.briefs()[-1]["brief"]
        self.assertIn("## Sensor markers this change adds", brief)
        self.assertIn("- src/calc.py: # SENSOR(1): the word is the name of the upstream field", brief)
        self.assertIn("- src/calc.py: OTHER = 'FIXME'  # SENSOR(1): quoted from the vendor's file", brief)

    def test_a_marker_with_no_number_is_refused_by_the_seeds_rule(self):
        self.assertIn("sensor-marker-names-its-ticket", MARKER_RULE)
        p = self.claimed(self.project(sensor=SENSOR + MARKER_RULE))
        p.write("src/calc.py", FIXED + "\n\nOTHER = 'FIXME'  # SENSOR: trust me\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "rules")["result"], "fail")
        self.assertIn("sensor-marker-names-its-ticket", failed["action"]["brief"])

    def test_a_sensors_config_changed_on_the_tickets_branch_changes_nothing_for_its_ship(self):
        p = self.project()
        p.add(ticket(tier="PERSON", scope=("src/**", ".rail/sensors/**")))
        self.assertEqual(p.rail("status")["tickets"][0]["tier"], "PERSON")  # the sensors' files are Rail's own gates
        p.rail("accept", "1")
        p.rail("next")
        work = p.worktree("1")
        p.write(".rail/sensors/words.txt", "NOTHING\n", base=work)
        p.write(".rail/sensors/find.py", "import sys\nsys.exit(0)\n", base=work)
        p.write("src/calc.py", FIXED + "\n\nOTHER = 'FIXME'\n", base=work)
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "sensors")["detail"], "1 violations: words")  # the base's tool and its words

    def test_an_exit_the_sensor_does_not_declare_is_a_crash_not_a_missing_tool(self):
        crashing = SENSOR.replace("command = 'python3", "command = 'TOOL_EXIT=4 python3")
        p = self.claimed(self.project(sensor=crashing))
        p.write("src/calc.py", FIXED + "\n\nOTHER = 'FIXME'\n", base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "sensors"), {"step": "sensors", "status": "could_not_run", "result": "fail",
                                                   "detail": "words: exit 4, which the sensor does not declare"})
        brief = failed["action"]["brief"]
        self.assertIn("declares neither as clean (ok_exit) nor as violations (violations_exit)", brief)
        self.assertNotIn("install it here", brief)
        later = p.rail("next", "--ticket", "1")["action"]["brief"]
        self.assertIn("could not run 'sensors': words: exit 4, which the sensor does not declare", later)
        self.assertIn("the tool crashed, or its command or config is wrong", later)
        self.assertNotIn("install it here", later)

    def test_a_sensor_whose_tool_is_missing_could_not_run_and_doctor_says_so_first(self):
        missing = SENSOR.replace("command = 'python3 \"$RAIL_SENSORS/find.py\"'", "command = 'no-such-linter --all src'")
        p = self.claimed(self.project(sensor=missing))
        p.write("src/calc.py", FIXED, base=p.worktree("1"))
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(step(failed, "sensors")["status"], "could_not_run")
        self.assertIn("words: could not run (exit 127", step(failed, "sensors")["detail"])
        self.assertIn("install it here", failed["action"]["brief"])
        doctor = {s["step"]: s for s in p.rail("doctor", expect=None)["steps"]}
        self.assertEqual(doctor["sensors"]["result"], "fail")
        self.assertIn("not on this machine: no-such-linter (sensor words)", doctor["sensors"]["detail"])

    def test_a_sensor_runs_only_when_the_change_touches_its_paths(self):
        p = self.project()
        p.add(ticket(title="Other", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.rail("next")
        p.write("api/handlers.py", "def handle():\n    return 201  # FIXME\n", base=p.worktree("1"))
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", "1")
        self.assertEqual(step(shipped, "sensors"), {"step": "sensors", "status": "not_run"})

    def test_a_sensor_needs_an_id_a_command_and_exit_codes_that_are_numbers(self):
        for n, (old, new, said) in enumerate((
                ('id = "words"\n', "", "config: sensors[0] needs an id"),
                ("command = 'python3 \"$RAIL_SENSORS/find.py\"'", "command = ' '", "config: sensors[0] needs a command"),
                ('fix = "Say it another way."', 'ok_exit = ["0"]', "config: sensors[0].ok_exit must be a list of exit codes"),
                ('paths = ["src/**"]', "paths = [1]", "config: sensors[0].paths must be a list of strings"),
                ('fix = "Say it another way."', "exit = [1]", "config: unknown key 'sensors[0].exit'"))):
            self.assertIn(old, SENSOR)
            p = self.fixture(name=f"p{n}", config=CONFIG + SENSOR.replace(old, new))
            self.assertIn(said, p.rail("status", expect=None)["reason"]["message"])
