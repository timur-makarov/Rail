"""The bench's second part with the fake arms: the Rail and plain drivers, saved stages and restarts, a driver killed
mid-run, the taint search, a PERSON ticket, and the arm files."""

import json
import os
import re
import signal
import subprocess
import time
import tomllib

from benchtest import BENCH_CLI, BenchTest

from bench import arms, common, driver, runs, sealed, taint

BLOCKING = {"severity": "blocking", "file": "calc/ops.py", "line": 2, "claim": "add(-1, 1) gives the wrong sign."}
CHECK = "python3 -m unittest tests.test_ops"
BROKEN = "def add(a, b):\n    return a +\n"


def tree(copy):
    """The base branch's files with their blob ids, the journal left out."""
    return [line for line in common.git(["ls-tree", "-r", "main"], copy).splitlines() if ".rail/journal/" not in line]


TIMES = re.compile(r'"(at|merged_at)":\s*"[0-9T:Z.+-]+"')
MINUTES = re.compile(r'"(minutes|duration_ms|ms)":\s*[0-9.]+')
HEAD = re.compile(r'"head":\s*"[0-9a-f]+"')


def journals(copy):
    """Each journal file on the base branch, with what must differ between two runs made the same: the times of its
    events, the minutes and milliseconds a step took, and the branch head a ship records. The journal is committed
    with its times, so every commit after the first event has a new id in each run, and so does a recorded head."""
    out = {}
    for path in common.git(["ls-tree", "-r", "--name-only", "main", ".rail/journal"], copy).split():
        text = common.git(["show", f"main:{path}"], copy)
        out[path] = HEAD.sub('"head": "H"', MINUTES.sub(r'"\1": 0', TIMES.sub(r'"\1": "T"', text)))
    return out


class FullRun(BenchTest):
    def test_check_arm_fake_runs_the_trivial_situation_end_to_end(self):
        out = self.bench("check-arm", "fake")
        self.assertIn("ended MERGED; merged; right", out)
        self.assertIn("check-arm fake: pass", out)

    def test_a_full_run_merges_grades_right_and_keeps_its_stages_in_a_scrubbed_environment(self):
        os.environ["GH_TOKEN"] = "not-for-children"
        try:
            dump = os.path.join(self.tmp, "env.json")
            r = self.run_fake(plan=self.plan(work=[{"patch": self.fix(), "dump_env": dump}]))
        finally:
            os.environ.pop("GH_TOKEN")
        res = r.result
        self.assertEqual((res["end"], res["merged"], res["right_merged"], res["right_stop"]), ("MERGED", True, True, True))
        self.assertEqual(res["person_acts"], [])
        self.assertFalse(res["tainted"])
        self.assertEqual((res["contract_runs"], res["worker_runs"], res["review_rounds"]), (1, 1, 1))
        self.assertEqual([s["name"] for s in r.stages()], ["intake", "contract", "work-1", "review-1", "end"])
        self.assertEqual(r.stream_files(), ["001-contract.jsonl", "002-worker.jsonl"])
        self.assertEqual([(w["code"], w["role"]) for w in res["worked"]], [("TICKET_LINT", "contract"),
                                                                              ("IMPLEMENT", "worker")])
        with open(dump) as f:
            env = json.load(f)
        self.assertNotIn("GH_TOKEN", env)
        self.assertEqual((env["HOME"], env["TMPDIR"]), (r.home, r.tmp))
        self.assertEqual(env["CLAUDE_CODE_SESSION_ID"], r.session)
        self.assertEqual(env["GH_CONFIG_DIR"], os.path.join(r.home, ".config", "gh"))
        self.assertEqual(env["RAIL_WORKER"], "1")
        self.assertTrue(env["PATH"].startswith(os.path.join(r.copy, ".rail", "bin")))
        # the copy stays sealed: one start commit under Rail's, no remote
        self.assertEqual(common.git(["remote"], r.copy).strip(), "")
        # Rail's config is the one rail init wrote, with the project's tables and the arm's on top: the seed's guides
        # stay, so the first IMPLEMENT brief carried the build guide
        config = tomllib.loads(common.git(["show", f"{r.base}:.rail/config.toml"], r.copy))
        self.assertEqual(config["guides"]["start"], ".rail/engine/guides/build.md")
        self.assertEqual(config["commands"]["verify"], "python3 -m unittest tests.test_ops")
        self.assertEqual(config["review"]["model"], "claude-opus-5-5")
        self.assertIn("fake_agent.py --review", config["review"]["command"])
        events = [json.loads(line) for line in common.git(["show", "main:.rail/journal/1-events.jsonl"],
                                                          r.copy).splitlines() if line.strip()]
        self.assertIn("start", [e.get("situation") for e in events if e.get("event") == "guided"])
        # a second bench run on a finished run grades nothing again
        self.assertIn("ended MERGED", self.bench("run", self.project_file, "--id", "calc-01", "--arm", "fake"))
        self.assertEqual(sum(1 for e in r.log_lines() if e["kind"] == "graded"), 1)

    def fix(self):
        s = self.situation()
        sealed.build(self.store, s)
        return sealed.fix_diff(self.store, s)


class Restart(BenchTest):
    def test_a_restart_from_each_saved_stage_gives_the_same_tree_and_journals(self):
        plan = self.plan(review=[{"summary": "Ran it.", "findings": [BLOCKING]}],
                         work=[{"patch": self.fix_path()},
                               {"answer": [["F1", "fixed", "add now adds"]], "write": {"calc/notes.py": "X = 1\n"}}])
        r = self.run_fake(plan=plan)
        self.assertTrue(r.result["right_merged"], r.result)
        names = [s["name"] for s in r.stages()]
        self.assertEqual(names, ["intake", "contract", "work-1", "review-1", "work-2", "review-2", "end"])
        procs = [(name, subprocess.Popen([BENCH_CLI, "run", "--from", r.id, "--stage", name, "--arm", "fake"],
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
                 for name in names[1:]]
        for name, proc in procs:
            out, _ = proc.communicate(timeout=900)
            self.assertEqual(proc.returncode, 0, out)
        want_tree, want_journals = tree(r.copy), journals(r.copy)
        self.assertTrue(want_journals)
        for name in names[1:]:
            other = runs.Run(os.path.join(self.store, "runs", f"{r.id}.from-{name}.fake.1"))
            with self.subTest(stage=name):
                self.assertEqual(other.result["end"], "MERGED")
                self.assertEqual(other.origin["restored"], names[names.index(name) - 1])
                self.assertEqual(tree(other.copy), want_tree)
                self.assertEqual(journals(other.copy), want_journals)

    def fix_path(self):
        s = self.situation()
        sealed.build(self.store, s)
        return sealed.fix_diff(self.store, s)


class Killed(BenchTest):
    def test_a_driver_killed_mid_run_goes_on_from_its_last_stage(self):
        s = self.situation()
        sealed.build(self.store, s)
        plan = self.plan(work=[{"patch": sealed.fix_diff(self.store, s), "sleep": 20}])
        args = [BENCH_CLI, "run", self.project_file, "--id", "calc-01", "--arm", "fake", "--plan", plan]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        index = os.path.join(self.store, "runs", "calc.calc-01.fake.1", "stages", "stages.jsonl")
        deadline = time.time() + 600
        while time.time() < deadline:
            if os.path.exists(index) and '"contract"' in open(index).read():
                break
            time.sleep(0.5)
        time.sleep(3)  # the worker sleeps now, inside rail work
        os.killpg(proc.pid, signal.SIGKILL)  # as the cloud machine kills every process when it pauses
        proc.wait()
        r = runs.Run(os.path.dirname(os.path.dirname(index)))
        self.assertFalse(r.result)
        self.bench("run", self.project_file, "--id", "calc-01", "--arm", "fake")
        self.assertEqual((r.result["end"], r.result["right_merged"]), ("MERGED", True))
        resumed = [e for e in r.log_lines() if e["kind"] == "resume"]
        self.assertEqual([e["stage"] for e in resumed], ["contract"])
        self.assertEqual(sum(1 for e in r.log_lines() if e["kind"] == "graded"), 1)
        self.assertEqual([x["name"] for x in r.stages()], ["intake", "contract", "work-1", "review-1", "end"])


class Waits(BenchTest):
    def test_a_person_ticket_is_approved_in_the_persons_place_and_counted(self):
        r = self.run_fake(plan=self.plan(contract={"tier": "PERSON", "scope": ["calc/**"],
                                                   "check": "python3 -m unittest tests.test_ops",
                                                   "person_reason": "data-shape: calc/ops.py"}))
        res = r.result
        self.assertEqual(res["person_acts"], ["APPROVE_CONTRACT", "MERGE_BY_PERSON"])
        self.assertEqual((res["end"], res["right_merged"]), ("MERGED", True))

    def test_another_wait_ends_the_run_with_its_code_and_the_stop_is_graded(self):
        self.edit_project("timeout_secs = 120", "timeout_secs = 120\n\n[rail.config.retry]\nbudget = 1\ncap = 1")
        r = self.run_fake(plan=self.plan(contract={"tier": "PERSON", "scope": ["calc/**"], "check": CHECK,
                                                   "person_reason": "data-shape: calc/ops.py"},
                                         work=[{"write": {"calc/ops.py": BROKEN}}]))
        res = r.result
        self.assertEqual(res["end"], "RETRY_CAP")  # a PERSON ticket at the cap waits for a person
        self.assertFalse(res["merged"])
        self.assertNotIn("right_merged", res)
        self.assertFalse(res["right_stop"])

    def test_a_stuck_auto_ticket_ends_the_run_before_its_drop_and_its_change_is_graded(self):
        self.edit_project("timeout_secs = 120", "timeout_secs = 120\n\n[rail.config.retry]\nbudget = 1\ncap = 1")
        r = self.run_fake(plan=self.plan(work=[{"write": {"calc/ops.py": BROKEN}}]))
        res = r.result
        self.assertEqual(res["end"], "STUCK")
        self.assertFalse(res["merged"])
        self.assertFalse(res["right_stop"])
        with open(os.path.join(r.path, "change.diff")) as f:
            self.assertIn("+    return a +", f.read())  # the change at the stop, not lost to the drop

    def test_a_rate_limit_marks_the_run_to_run_again_and_it_is_not_graded(self):
        r = self.run_fake(plan=self.plan(work=[{"error": "rate_limit"}]))
        res = r.result
        self.assertTrue(res["again"])
        self.assertEqual(res["end"], "AGAIN")
        self.assertNotIn("right_stop", res)

    def test_the_wall_clock_ends_a_run(self):
        self.write_config(run_minutes=0.5)
        r = self.run_fake(plan=self.plan(work=[{"sleep": 120}]))
        self.assertEqual(r.result["end"], "WALL_CLOCK")
        self.assertLess(r.result["minutes"], 2)
        self.assertFalse(r.result["right_stop"])


class Taint(BenchTest):
    def test_a_planted_leak_marks_the_run_tainted(self):
        calls = [["Bash", {"command": "gh pr view 8 --repo acme/calc"}],
                 ["WebFetch", {"url": "https://github.com/acme/calc/pull/8", "prompt": "the diff"}]]
        r = self.run_fake(plan=self.plan(work=[{"patch": self.fix(), "calls": calls}]))
        self.assertTrue(r.result["tainted"])
        terms = sorted({h["term"] for h in r.result["taint"]})
        self.assertEqual(terms, ["fetch of the project", "gh command", "pull request link", "pull request number"])

    def fix(self):
        s = self.situation()
        sealed.build(self.store, s)
        return sealed.fix_diff(self.store, s)

    def search(self, *calls):
        path = os.path.join(self.tmp, "stream.jsonl")
        with open(path, "w") as f:
            for tool, tool_input in calls:
                f.write(json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "t", "name": tool, "input": tool_input}]}}) + "\n")
        s = self.situation()
        return sorted({h["term"] for h in taint.search([path], s, "abcdef1234567890", folders=["/store/sealed"])})

    def test_what_the_search_finds_and_what_it_leaves(self):
        self.assertEqual(self.search(["Bash", {"command": "git show abcdef12"}]), ["fix commit"])
        self.assertEqual(self.search(["WebFetch", {"url": "https://github.com/acme/calc/issues/7"}]),
                         ["fetch of the project", "issue URL"])
        self.assertEqual(self.search(["Bash", {"command": "cd x && gh api repos/acme/calc"}]), ["gh command"])
        self.assertEqual(self.search(["Bash", {"command": "pip install acme-calc==2.0"}]), ["fetch of the project"])
        self.assertEqual(self.search(["Bash", {"command": "git clone https://github.com/acme/calc"}]),
                         ["fetch of the project"])
        self.assertEqual(self.search(["WebSearch", {"query": "acme-calc add bug"}]), ["fetch of the project"])
        self.assertEqual(self.search(["Read", {"file_path": "/store/sealed/fixture/calc/calc-01/hidden/x.py"}]),
                         ["bench folder"])
        # ordinary work names none of them
        self.assertEqual(self.search(["Bash", {"command": "go test github.com/acme/calc/..."}],
                                     ["Bash", {"command": "python3 -m unittest discover -s tests"}],
                                     ["Read", {"file_path": "calc/ops.py"}],
                                     ["Bash", {"command": "git log --oneline"}],
                                     ["Grep", {"pattern": "def add"}]), [])


class Plain(BenchTest):
    def test_a_plain_arm_that_says_done_counts_as_merged_and_is_graded(self):
        r = self.run_fake(arm="fake-plain")
        res = r.result
        self.assertEqual((res["end"], res["merged"], res["right_merged"]), ("DONE", True, True))
        self.assertEqual(r.stream_files(), ["001-worker.jsonl"])
        self.assertEqual(r.stages(), [])

    def test_a_plain_arm_that_does_not_say_done_is_not_merged_but_its_stop_is_graded(self):
        r = self.run_fake(arm="fake-plain", plan=self.plan(plain={"patch": self.fix(), "say": "Fixed add.\nNOT DONE: no tests"}))
        res = r.result
        self.assertEqual((res["end"], res["merged"], res["right_stop"]), ("NOT_DONE", False, True))
        self.assertNotIn("right_merged", res)

    def test_a_plain_rate_limit_is_to_run_again(self):
        r = self.run_fake(arm="fake-plain", plan=self.plan(plain={"error": "rate_limit"}))
        self.assertTrue(r.result["again"])

    def test_a_child_that_could_not_sign_in_is_to_run_again_and_not_graded(self):
        r = self.run_fake(arm="fake-plain", plan=self.plan(plain={"error": "sign_in"}))
        self.assertEqual((r.result["again"], r.result["detail"]), (True, "sign-in failed (Not logged in)"))
        self.assertNotIn("right_stop", r.result)

    def fix(self):
        s = self.situation()
        sealed.build(self.store, s)
        return sealed.fix_diff(self.store, s)

    def test_a_brief_on_the_contract_model_runs_as_the_contract_role(self):
        # Rail runs the sweep's ticket filing on [worker] contract, as it does the contract: so does the bench.
        self.assertEqual({code: driver.role_of(code) for code in driver.WORK_CODES},
                         {code: "contract" if code in ("TICKET_LINT", "SWEEP_TICKETS", "AFTER_DROPPED") else "worker"
                          for code in driver.WORK_CODES})

    def test_the_done_rule(self):
        ok = {"type": "result", "subtype": "success", "is_error": False}
        for text, want in (("Fixed it.\nDONE", True), ("DONE", True), ("**DONE**", True), ("`DONE`.", True),
                           ("DONE\n\n", True), ("NOT DONE: tests fail", False), ("Done", False),
                           ("DONE, mostly", False), ("DONE\nbut one more thing", False), ("", False)):
            with self.subTest(text=text):
                self.assertEqual(driver.says_done(0, dict(ok, result=text)), want)
        self.assertFalse(driver.says_done(1, dict(ok, result="DONE")))
        self.assertFalse(driver.says_done(None, dict(ok, result="DONE")))
        self.assertFalse(driver.says_done(0, dict(ok, result="DONE", subtype="error_max_budget_usd", is_error=True)))
        self.assertFalse(driver.says_done(0, None))

    def test_the_prompt_is_the_request_one_sentence_and_the_commands(self):
        prompt = driver.plain_prompt(self.situation())
        self.assertTrue(prompt.startswith("add() gives the wrong answer\ncalc.ops.add(2, 3) returns -1."))
        self.assertIn(driver.PLAIN_SENTENCE, prompt)
        self.assertIn("python3 -m unittest tests.test_ops", prompt)
        self.assertNotIn("test_add", prompt)


class Arms(BenchTest):
    def write_arm(self, text):
        path = os.path.join(self.tmp, "arm.toml")
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_the_shipped_arms_load(self):
        for name in ("rail", "plain-sonnet", "plain-opus", "plain-haiku", "fake", "fake-plain"):
            arm = arms.load(name)
            self.assertEqual(arm.plain, name.startswith("plain") or name == "fake-plain", name)
        conf = dict(self.conf)
        self.assertIn("--model claude-opus-5-5 --effort medium", arms.load("plain-opus").command("worker", conf))
        self.assertIn(f"--max-budget-usd {conf['budget_usd']}", arms.load("rail").command("worker", conf))

    def test_an_arm_maps_onto_rails_config(self):
        arm = arms.load(self.write_arm('[worker]\ncommand = "w {model}"\nmodel = "m1"\neffort = "high"\n'
                                       '[contract]\nmodel = "m2"\n[review]\ncommand = "r --effort {effort}"\n'
                                       'model = "m3"\neffort = "max"\n[consult]\nmodel = "m4"\n'))
        self.assertEqual(arm.rail_overrides(self.conf), {
            "worker": {"command": "w m1", "ladder": ["m1:high"], "person_ladder": ["m1:high"], "contract": "m2:high"},
            "review": {"command": "r --effort max", "model": "m3"}, "consult": {"model": "m4"}})

    def test_bad_arms_are_refused_and_say_why(self):
        for text, word in (('[worker]\ncommand = "claude -p --resume x"\n', "resumes"),
                           ('[worker]\ncommand = "claude ${RAIL_SESSION:+--resume $RAIL_SESSION}"\n', "resumes"),
                           ('plain = true\n[worker]\ncommand = "c"\n[review]\ncommand = "r"\n', "only a worker"),
                           ('plain = true\n', "needs worker.command"),
                           ('[contract]\ncommand = "c"\n', "contract.command"),
                           ('[worker]\nturns = 3\n', "worker.turns"),
                           ('[worker]\neffort = "huge"\n', "effort"),
                           ('[files]\n".rail/x" = "nope.md"\n', "no file"),
                           ('colour = "red"\n', "colour")):
            with self.subTest(word=word):
                with self.assertRaises(common.BenchError) as e:
                    arms.load(self.write_arm(text))
                self.assertIn(word, str(e.exception))
