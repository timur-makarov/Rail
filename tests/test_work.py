"""rail work: the engine starts the worker on a ticket's brief, keeps the claim alive while it works, and records the
run. The worker is tests/fake_worker.py, which prints what the test queues in the shape of the CLI's stream."""

import json
import os
import shlex
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, FAKE_WORKER, RAIL, RailTest, ticket

WORK = CONFIG + f'\n[worker]\ncommand = "python3 {FAKE_WORKER}"\n'
FIXED = "def add(a, b):\n    return a + b\n"


def events(fx, ref="1-fix-add", name=None, nn="1"):
    text = fx.git("show", f"{ref}:.rail/journal/{nn}-events.jsonl")
    found = [json.loads(line) for line in text.splitlines()]
    return [e for e in found if e["event"] == name] if name else found


def run_log(fx, nn="1"):
    path = fx.path(".git", "rail", "cache", "work", nn)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return f.read().splitlines()


def rail_in_worker(*args):
    """A rail command the stand-in worker runs, as a worker would from its Bash tool."""
    return " ".join([sys.executable, RAIL, *args, "--json"])


class Work(RailTest):
    def test_a_run_does_the_brief_and_records_a_worked_event(self):
        p = self.fixture(config=WORK)
        p.add(ticket())
        told = p.rail("next")
        self.assertEqual(told["reason"]["code"], "IMPLEMENT")
        p.queue_work({"write": {"src/calc.py": FIXED}, "session": "s-1",
                      "result": {"total_cost_usd": 0.42, "num_turns": 7, "result": "Fixed add."}})
        done = p.rail("work", "1")
        self.assertEqual((done["reason"]["code"], done["owner"], done["action"]["kind"], done["action"]["command"]),
                         ("WORKED", "agent", "script", "rail advance 1"))
        self.assertEqual(done["reply"], "Fixed add.")
        self.assertEqual(done["steps"][-1]["step"], "worker")
        ran = p.work_log()[0]
        self.assertEqual(ran["cwd"], p.worktree("1"))
        self.assertTrue(ran["brief"].startswith(told["action"]["brief"]))  # the brief next gives, word for word
        self.assertTrue(ran["brief"].rstrip().endswith(
            "reply in one line. Don't run `rail advance`: the runner runs it after you exit."))
        self.assertEqual(ran["env"], {"RAIL_TICKET": "1", "RAIL_MODEL": "claude-sonnet-5-5", "RAIL_EFFORT": "medium",
                                      "RAIL_SESSION": "", "ANTHROPIC_MODEL": "claude-sonnet-5-5", "RAIL_WORKER": "1"})
        worked = events(p, name="worked")
        self.assertEqual(len(worked), 1)
        e = worked[0]
        self.assertEqual((e["code"], e["model"], e["effort"], e["cost_usd"], e["turns"], e["session"], e["end"],
                          e["resumed"]), ("IMPLEMENT", "claude-sonnet-5-5", "medium", 0.42, 7, "s-1", "done", False))
        self.assertIn("minutes", e)
        self.assertEqual(done["worked"]["session"], "s-1")
        shipped = p.rail("advance", "1")  # the runner's next move ships what the worker left
        self.assertNotEqual(shipped["state"], "implementing", shipped)

    def test_it_runs_only_for_a_tickets_agent_work(self):
        p = self.fixture(config=WORK.replace("timeout_secs = 60", 'setup = "exit 1"\ntimeout_secs = 60'))
        p.add(ticket())
        failed = p.rail("next", expect=3)
        self.assertEqual(failed["reason"]["code"], "SETUP_FAILED")
        again = p.rail("work", "1")
        self.assertEqual((again["reason"]["code"], again["action"]["brief"]),
                         ("SETUP_FAILED", p.rail("next")["action"]["brief"]))  # untouched
        p.add(ticket(title="Person work", tier="PERSON", scope=("api/**",)))
        self.assertEqual(p.rail("work", "2")["reason"]["code"], "APPROVE_CONTRACT")
        self.assertEqual(p.work_log(), [])  # no worker started
        self.assertEqual(p.rail("work", expect=2)["reason"]["message"], "which ticket? Run rail work NN")

    def test_a_contract_is_written_from_the_projects_root_on_the_contract_model(self):
        p = self.fixture(config=WORK)
        request = os.path.join(self.tmp, "request.md")
        with open(request, "w") as f:
            f.write("Make add add.\n")
        p.rail("intake", "--external-id", "jira#1", "--title", "Fix add", "--brief", request)
        self.assertEqual(p.rail("work", "1")["reason"]["code"], "WORKED")
        ran = p.work_log()[0]
        self.assertEqual((ran["cwd"], ran["env"]["RAIL_MODEL"], ran["env"]["RAIL_EFFORT"]),
                         (p.root, "claude-opus-5-5", "high"))
        self.assertIn("isn't complete", ran["brief"])
        self.assertEqual(events(p, ref="1-jira-1-fix-add", name="worked")[0]["code"], "TICKET_LINT")

    def test_inside_a_run_the_engines_moves_refuse(self):
        p = self.fixture(config=WORK)
        p.add(ticket())
        p.rail("next")
        p.queue_work({"write": {"src/calc.py": FIXED},
                      "run": [rail_in_worker(verb, "1") for verb in ("advance", "next", "work", "save")]
                      + [rail_in_worker("status")]})
        p.rail("work", "1")
        ran = p.work_log()[0]["ran"]
        for refused in ran[:4]:
            answer = json.loads(refused["output"])
            self.assertEqual((refused["code"], answer["reason"]["code"]), (2, "WORKER_RUN"), refused["command"])
            self.assertIn("is the runner's to run after you exit", answer["reason"]["message"])
        self.assertEqual(ran[4]["code"], 0)  # the other verbs work
        self.assertEqual(events(p, name="shipped"), [])  # nothing shipped inside the run
        # The worker's own save hooks do nothing: the claim and its saves are the runner's.
        before = events(p)
        hook = subprocess.run([p.path(".rail", "bin", "rail"), "hook", "stop"], cwd=p.worktree("1"), text=True,
                              input=json.dumps({"session_id": "worker-session", "cwd": p.worktree("1")}),
                              capture_output=True, env=dict(os.environ, RAIL_WORKER="1", RAIL_CLOUD="0",
                                                            CLAUDE_CODE_SESSION_ID="session-a"))
        self.assertEqual((hook.returncode, hook.stdout), (0, ""))
        self.assertEqual(events(p), before)

    def test_a_run_longer_than_stale_minutes_keeps_its_claim(self):
        a, b = self.remote_pair(config=WORK + "\n[claim]\nsave_minutes = 0\n")  # 0: save at every chance
        a.add(ticket())
        a.rail("next")
        # The ticket's journal says nothing happened for two hours: another session would take it over now.
        tree = a.worktree("1")
        journal = os.path.join(tree, ".rail", "journal", "1-events.jsonl")
        with open(journal) as f:
            old = [dict(json.loads(line), at="2020-01-01T00:00:00Z") for line in f]
        with open(journal, "w") as f:
            f.write("".join(json.dumps(e) + "\n" for e in old))
        a.git("commit", "--quiet", "-am", "1: two hours ago", cwd=tree)
        a.git("push", "--quiet", "origin", "1-fix-add", cwd=tree)
        b.git("fetch", "--quiet")
        self.assertEqual(b.rail("status", session="session-b")["tickets"][0]["note"],
                         "left by an ended session: rail next resumes it")
        a.queue_work({"write": {"src/calc.py": FIXED}, "sleep": 8})
        worker = threading.Thread(target=lambda: a.rail("work", "1"))
        worker.start()
        bare = os.path.join(self.tmp, "remote.git")
        for _ in range(100):  # until the run has saved once
            text = subprocess.run(["git", "--git-dir", bare, "show", "1-fix-add:.rail/journal/1-events.jsonl"],
                                  capture_output=True, text=True).stdout
            if '"via":"work"' in text:
                break
            time.sleep(0.1)
        other = b.rail("next", session="session-b")
        self.assertNotEqual(other["ticket"], "1", other)  # the ticket is left alone
        self.assertIn("1", [h["ticket"] for h in other["held"]])
        worker.join()
        a.git("fetch", "--quiet")
        saves = [e for e in events(a, ref="origin/1-fix-add", name="saved") if e["via"] == "work"]
        self.assertTrue(saves)
        claims = events(a, ref="origin/1-fix-add", name="claimed")
        self.assertEqual(claims[-1]["session"], "session-a")
        self.assertEqual(a.git("show", "origin/1-fix-add:src/calc.py"), FIXED)  # the save pushed the work too

    def test_a_run_past_timeout_minutes_is_ended_and_recorded(self):
        # timeout_minutes is whole minutes in the config: the engine is called here with a few seconds instead.
        p = self.fixture(config=WORK)
        p.add(ticket())
        p.rail("next")
        p.queue_work({"sleep": 60, "detach": 40})
        script = "\n".join([
            "import argparse, json, sys",
            f"sys.path.insert(0, {p.path('.rail', 'engine')!r})",
            "from rail import cli",
            "from rail.project import Project",
            f"project = Project({p.root!r})",
            'project.config["worker"]["timeout_minutes"] = 0.03',
            'print(json.dumps(cli.cmd_work(project, argparse.Namespace(ticket="1"))))'])
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="session-a", RAIL_CLOUD="0", RAIL_FAKE_WORKER=p.root + ".worker.json",
                   RAIL_FAKE_WORKER_LOG=p.root + ".worker.log")
        env.pop("RAIL_TICKET", None)
        began = time.monotonic()
        done = subprocess.run([sys.executable, "-c", script], cwd=p.root, env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(time.monotonic() - began, 30)
        worked = events(p, name="worked")[-1]
        self.assertEqual(worked["end"], "timeout")
        self.assertNotIn("cost_usd", worked)
        self.assertEqual(json.loads(done.stdout)["steps"][-1]["result"], "fail")

    def test_after_a_failed_ship_the_workers_brief_has_the_failures_output(self):
        p = self.fixture(config=WORK)
        check = ("python3 -c \"import sys; sys.path.insert(0, 'src'); import calc;"
                 " assert calc.add(2, 3) == 5, 'known-' + 'failure-line-7'\"")  # the line is only in its output
        p.add(ticket(check=check))
        p.rail("next")
        p.queue_work({}, {})
        p.rail("work", "1")  # the worker changes nothing
        failed = p.rail("advance", "1", expect=3)
        self.assertEqual(failed["reason"]["code"], "STEP_FAILED")
        self.assertIn("known-failure-line-7", failed["action"]["brief"])
        self.assertIn("known-failure-line-7", p.rail("next")["action"]["brief"])
        p.rail("work", "1")
        brief = p.work_log()[-1]["brief"]
        self.assertIn("The last ship of ticket 1 failed at 'checks'", brief)
        self.assertIn("known-failure-line-7", brief)  # what advance's answer showed, though the journal keeps less
        self.assertNotIn("known-failure-line-7", p.git("show", "1-fix-add:.rail/journal/1-events.jsonl"))

    def test_a_save_steps_aside_while_the_worker_holds_the_index_lock(self):
        p = self.fixture(config=WORK + "\n[claim]\nsave_minutes = 0\n")  # 0: save at every chance
        p.add(ticket())
        p.rail("next")
        hold = ('L=$(git rev-parse --path-format=absolute --git-path index.lock); touch "$L"; sleep 4;'
                ' rm -f "$L"')
        p.queue_work({"write": {"src/calc.py": FIXED}, "run": [hold]})
        p.rail("work", "1")
        self.assertEqual([e for e in events(p, name="saved") if e["via"] == "work"], [])  # every tick skipped
        self.assertIn("src/calc.py", p.git("status", "--porcelain", cwd=p.worktree("1")))  # left for the ship

    def test_the_same_worker_goes_on_while_the_rung_stays_and_its_run_ended_done(self):
        p = self.fixture(config=WORK)
        p.add(ticket())
        p.rail("next")
        p.queue_work({"session": "s-1"}, {"result": {"subtype": "error_max_budget_usd", "is_error": True}},
                     {"session": "s-3"}, {"resume_fails": True}, {})
        p.rail("work", "1")
        second = p.rail("work", "1", expect=3)  # the budget ended it: a failed step
        self.assertEqual(second["worked"]["end"], "budget")
        p.rail("work", "1")
        p.rail("work", "1")
        sessions = [run["env"]["RAIL_SESSION"] for run in p.work_log()]
        # The second run resumes the first; the third starts fresh after the budget end; the fourth resumes the third,
        # the resume fails as on a new machine, and it runs once more fresh.
        self.assertEqual(sessions[:4], ["", "s-1", "", "s-3"])
        self.assertEqual(sessions[4], "")
        worked = events(p, name="worked")
        self.assertEqual([e["resumed"] for e in worked], [False, True, False, False])
        self.assertEqual([e.get("resume_failed", False) for e in worked], [False, False, False, True])
        self.assertEqual([e["end"] for e in worked], ["done", "budget", "done", "done"])

    def test_a_command_with_no_json_gives_an_event_with_no_cost(self):
        p = self.fixture(config=WORK)
        p.add(ticket())
        p.rail("next")
        p.queue_work({"raw": "I fixed it."})
        done = p.rail("work", "1")
        worked = events(p, name="worked")[0]
        self.assertEqual(worked["end"], "done")
        for key in ("cost_usd", "turns", "session"):
            self.assertNotIn(key, worked)
        self.assertEqual(done["reply"], "I fixed it.")

    def test_a_stream_with_tool_calls_gives_a_run_log_and_counts(self):
        p = self.fixture(config=WORK)
        p.add(ticket())
        p.rail("next")
        calls = [
            ["Bash", {"command": "FOO=1 uv run pytest -x"}, "failed", "Exit code 1\nE   assert 1 == 5"],
            ["Bash", {"command": "cd app && pytest"}, "ok", "1 passed"],
            ["Bash", {"command": "pytest -k add"}, "failed", "Exit code 1"],  # after a pass: no relearning
            ["Bash", {"command": "make test"}, "failed", "Exit code 127\n(eval):1: command not found: make"],
            ["Bash", {"command": "git push --force origin main"}, "denied", "Rail guard: force pushes are denied"],
            ["Bash", {"command": "TOKEN=sk-secret-123 curl https://example.com"}, "ok", ""],
            *[["Read", {"file_path": "src/calc.py"}, "ok", "def add"] for _ in range(3)],
            ["Grep", {"pattern": "x" * 300}, "ok", ""],
            *[["Glob", {"pattern": f"src/{n}/*.py"}, "ok", ""] for n in range(600)],
        ]
        p.queue_work({"calls": calls}, {"calls": calls[:2]})
        p.rail("work", "1")
        worked = events(p, name="worked")[0]
        self.assertEqual(worked["counts"], {"failed": 1, "not_found": 1, "denied": 1, "reread": 1})
        self.assertEqual(worked["keys"], {"failed": ["pytest"], "not_found": ["make"],
                                          "denied": ["git: Rail guard: force pushes are denied"],
                                          "reread": ["src/calc.py"]})
        log = run_log(p)
        self.assertEqual(len(log), 501)  # its header, then 500 lines of a run's 609 calls
        self.assertTrue(log[0].startswith("# ") and "IMPLEMENT" in log[0])
        self.assertEqual(log[1], "Bash failed: FOO=1 uv run pytest -x")
        self.assertEqual(log[5], "Bash denied: git push --force origin main")
        self.assertEqual(len(log[10]), 200)  # the Grep's long pattern, cut
        p.rail("work", "1")
        log = run_log(p)
        self.assertEqual((len(log), sum(line.startswith("# ") for line in log)), (504, 2))  # the second run appends
        found = subprocess.run("git grep -I sk-secret-123 $(git rev-list --all) -- . || true", shell=True, cwd=p.root,
                               capture_output=True, text=True).stdout
        self.assertEqual(found, "")  # the log is never committed

    def test_a_run_that_ends_inside_a_rebase_writes_its_event_once_the_rebase_ends(self):
        a, b = self.remote_pair(config=WORK)
        a.add(ticket())
        a.rail("next")
        tree = a.worktree("1")
        a.write("src/calc.py", FIXED, base=tree)
        a.git("commit", "--quiet", "-am", "1: mine", cwd=tree)
        b.git("pull", "--quiet")
        b.write("src/calc.py", "def add(a, b):\n    return b + a  # theirs\n")
        b.git("commit", "--quiet", "-am", "theirs")
        b.git("push", "--quiet", "origin", "main")
        a.git("fetch", "--quiet")
        subprocess.run(["git", "rebase", "origin/main"], cwd=tree, capture_output=True, text=True)
        self.assertEqual(a.rail("next")["reason"]["code"], "REBASING")
        tip = a.git("rev-parse", "1-fix-add")
        a.queue_work({"calls": [["Bash", {"command": "make"}, "failed", "Exit code 127"]]})  # it doesn't finish the rebase
        done = a.rail("work", "1")
        self.assertEqual(done["worked"]["code"], "REBASING")
        self.assertIn("git rebase --continue", a.work_log()[0]["brief"])
        self.assertEqual(a.git("rev-parse", "1-fix-add"), tip)  # nothing was written to the branch
        self.assertEqual(events(a, name="worked"), [])
        self.assertEqual(len(run_log(a)), 2)  # the log is there already
        self.assertEqual(a.rail("advance", "1")["reason"]["code"], "REBASING")  # still held back
        self.assertEqual(events(a, name="worked"), [])
        a.write("src/calc.py", FIXED, base=tree)
        a.git("add", "src/calc.py", cwd=tree)
        subprocess.run(["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=tree, check=True,
                       capture_output=True)
        a.rail("advance", "1")
        worked = events(a, name="worked")
        self.assertEqual(len(worked), 1)
        self.assertEqual((worked[0]["code"], worked[0]["counts"]["not_found"], worked[0]["keys"]["not_found"]),
                         ("REBASING", 1, ["make"]))
        self.assertFalse(os.path.exists(a.path(".git", "rail", "cache", "worked", "1")))  # written, so gone


class Sweep(RailTest):
    def test_a_due_sweeps_task_runs_through_rail_work_on_the_contract_model(self):
        # A script that drives Rail with next, work and advance only, as an unattended runner would.
        p = self.fixture(config=WORK + "\n[sweep]\nevery = 2\n")
        parked = {"severity": "parked", "file": "src/calc.py", "claim": "calc has no subtract, and callers negate add."}
        for nn, title, scope, check, path, text in (
                ("1", "Fix add", ("src/**",), None, "src/calc.py", FIXED),
                ("2", "Add a status code", ("api/**",), "grep -q 201 api/handlers.py", "api/handlers.py",
                 "def handle():\n    return 201\n")):
            p.add(ticket(title=title, scope=scope, **({"check": check} if check else {})))
            p.rail("next")
            p.queue_work({"write": {path: text}})
            p.rail("work", nn)
            if nn == "1":
                p.queue_reviews({"summary": "Read it.", "findings": [parked]})
            p.rail("advance", nn)
            self.assertEqual(p.rail("advance", nn)["state"], "merged")
        offer = p.rail("next")
        self.assertEqual((offer["reason"]["code"], offer["action"]["command"]), ("SWEEP", "rail sweep"))
        swept = p.rail(*offer["action"]["command"].split()[1:])
        self.assertEqual((swept["ticket"], swept["reason"]["code"], swept["action"]["model"], swept["action"]["effort"]),
                         ("3", "SWEEP_TICKETS", "claude-opus-5-5", "high"))
        filed = os.path.join(self.tmp, "subtract.md")
        p.queue_work({"write": {filed: ticket(title="Add subtract", check="grep -q sub src/calc.py")},
                      "run": [rail_in_worker("add", filed)]})
        done = p.rail("work", "3")
        self.assertEqual((done["reason"]["code"], done["action"]["command"]), ("WORKED", "rail advance 3"))
        ran = p.work_log()[-1]
        self.assertEqual((ran["cwd"], ran["env"]["RAIL_MODEL"], ran["env"]["RAIL_EFFORT"]),
                         (p.worktree("3"), "claude-opus-5-5", "high"))
        self.assertIn("read .rail/journal/3-summary.md", ran["brief"])
        self.assertEqual(ran["ran"][0]["code"], 0, ran["ran"][0]["output"])  # the worker filed its ticket
        branch = next(t["branch"] for t in p.rail("status")["tickets"] if t["ticket"] == "3")
        worked = events(p, ref=branch, name="worked", nn="3")
        self.assertEqual((worked[0]["code"], worked[0]["model"], worked[0]["effort"]),
                         ("SWEEP_TICKETS", "claude-opus-5-5", "high"))
        p.rail("advance", "3")
        self.assertEqual(p.rail("advance", "3")["state"], "merged")
        self.assertIn("Sweep: since", p.git("log", "-1", "--format=%b", "main"))
        self.assertEqual([t["title"] for t in p.rail("status")["tickets"]][-1], "Add subtract")


class AfterDropped(RailTest):
    """Ticket 2 comes after ticket 1, and ticket 1 is dropped: on AUTO the decision is the contract writer's, and a
    script that drives Rail with next, work and advance goes through it."""

    def chain(self):
        p = self.fixture(config=WORK)
        p.add(ticket(title="Add a status code", scope=("api/**",), check="grep -q 201 api/handlers.py"))
        p.add(ticket(front=('after = ["1"]',)))
        p.rail("drop", "1", "--reason", "not needed")
        task = p.rail("next")
        self.assertEqual((task["ticket"], task["reason"]["code"]), ("2", "AFTER_DROPPED"))
        return p

    def test_the_worker_keeps_the_ticket_and_the_chain_goes_on_to_merge(self):
        p = self.chain()
        written = os.path.join(self.tmp, "2.md")
        p.queue_work({"write": {written: ticket()}, "run": [rail_in_worker("amend", "2", shlex.quote("add stands alone"),
                                                                            "--file", written)]})
        done = p.rail("work", "2")
        self.assertEqual((done["reason"]["code"], done["action"]["command"]), ("WORKED", "rail advance 2"))
        ran = p.work_log()[-1]
        self.assertEqual((ran["cwd"], ran["env"]["RAIL_MODEL"], ran["env"]["RAIL_EFFORT"]),
                         (p.root, "claude-opus-5-5", "high"))
        self.assertIn("rail amend 2", ran["brief"])
        self.assertEqual(ran["ran"][0]["code"], 0, ran["ran"][0]["output"])
        worked = events(p, ref="2-fix-add", name="worked", nn="2")
        self.assertEqual((worked[0]["code"], worked[0]["model"]), ("AFTER_DROPPED", "claude-opus-5-5"))
        after = p.rail("advance", "2")
        self.assertNotEqual(after["reason"]["code"], "AFTER_DROPPED")
        told = p.rail("next")
        self.assertEqual(told["reason"]["code"], "IMPLEMENT")
        p.queue_work({"write": {"src/calc.py": FIXED}})
        p.rail("work", "2")
        p.rail("advance", "2")
        self.assertEqual(p.rail("advance", "2")["state"], "merged")

    def test_the_worker_drops_the_ticket_and_the_chain_ends(self):
        p = self.chain()
        p.queue_work({"run": [rail_in_worker("drop", "2", "--reason", shlex.quote("it only made sense with the status code"))]})
        done = p.rail("work", "2")
        self.assertEqual(done["reason"]["code"], "WORKED")
        self.assertEqual(p.work_log()[-1]["ran"][0]["code"], 0, p.work_log()[-1]["ran"][0]["output"])
        self.assertEqual([e["code"] for e in events(p, ref="2-fix-add", name="worked", nn="2")], ["AFTER_DROPPED"])
        after = p.rail("advance", "2")
        self.assertEqual(after["state"], "dropped")
        self.assertEqual(p.rail("next")["reason"]["code"], "NO_WORK")
