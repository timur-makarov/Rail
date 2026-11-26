"""The drivers. No Claude session sits in the loop: the bench follows `rail next --json` as a script (Rail), or runs one
agent on the request (plain), and then grades what came out.

Rail: the request is filed as `rail intake` files an issue, then each answer of `rail next` is acted on:
- a ticket's agent work runs through `rail work NN`, then the command it returns (`rail advance NN`);
- a script that is a rail command runs as given (`rail advance`, `rail next --ticket`, `rail sweep`);
- a wait for a person on a PERSON ticket (approve the contract or an amend, merge) is answered with `rail accept NN`
  and counted;
- STUCK (an AUTO ticket at the retry cap, which the next `rail next` drops with its worktree and branch) ends the run
  before that drop, so the change at the stop is still there to grade;
- any other wait, rest or task ends the run, and its code is how it ended.

Plain: the request, one fixed sentence, and the project's commands go to the arm's worker command once. See
says_done for when its change counts as merged.

Every run is bounded by the run's wall clock (the driver ends it) and by the budget flag in the arm's command. A run
that ends on a rate-limit or overload error is marked to run again and never graded."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from . import arms as armsmod
from . import grade as grademod
from . import netlock, proxy, rail_install, runs, sealed, taint, tomlw
from .common import BENCH, BenchError, Clock, git, kill, now_iso, run, write

# engine/rail/work.py CODES: the briefs rail work runs
WORK_CODES = ("TICKET_LINT", "VERIFY_ASSUMPTIONS", "IMPLEMENT", "STEP_FAILED", "RED_CHECK", "ANSWER_FINDINGS", "CONFLICT",
              "REBASING", "SPLIT", "SWEEP_TICKETS", "AFTER_DROPPED")
# engine/rail/cli.py worker(): the briefs that run on [worker] contract's model, so on the arm's contract role
CONTRACT_CODES = ("TICKET_LINT", "SWEEP_TICKETS", "AFTER_DROPPED")
PERSON_WAITS = ("APPROVE_CONTRACT", "APPROVE_AMEND", "MERGE_BY_PERSON")
REVIEW_STEPS = ("review", "security", "refuter")
AGAIN = re.compile(r"rate[ _-]?limit|overloaded|\b429\b|\b529\b|usage limit", re.I)
# A child that could not sign in did no work: its run is run again once the sign-in is fixed, never graded.
SIGN_IN = re.compile(r"Not logged in|authentication_failed|Invalid API key|\b401\b", re.I)

PLAIN_SENTENCE = ("Make the change this issue asks for in this repository, with tests. When you are finished, end your"
                  " reply with one line that says only DONE if the change is complete, or NOT DONE and why if it is"
                  " not.")

STREAM_TEE = ' | tee -a "${BENCH_STREAM:-/dev/null}"'
# Rail runs the reviewer inside `rail advance`, whose ANTHROPIC_BASE_URL is the consult role's proxy: this prefix points
# the reviewer at its own. With no proxy, BENCH_URL_REVIEW is unset and the prefix is a bare `env`.
REVIEW_URL = 'env ${BENCH_URL_REVIEW:+ANTHROPIC_BASE_URL="$BENCH_URL_REVIEW"} '
ROLES = ("worker", "contract", "review", "consult")


class Ended(Exception):
    def __init__(self, code, **fields):
        super().__init__(code)
        self.code, self.fields = code, fields


# --- the environment -------------------------------------------------------------------------------


def child_env(conf, run_, project, store_root, extra=None):
    """A scrubbed environment: only what conf pass_env names, then the run's own HOME and TMPDIR, an empty gh config,
    the session id the bench sets, and the copy's rail on PATH."""
    env = {k: os.environ[k] for k in conf["pass_env"] if k in os.environ}
    for d in (run_.home, run_.tmp, os.path.join(run_.home, ".config", "gh")):
        os.makedirs(d, exist_ok=True)
    gitconfig = os.path.join(run_.home, ".gitconfig")
    if not os.path.exists(gitconfig):
        write(gitconfig, "[user]\n\tname = bench\n\temail = bench@localhost\n[commit]\n\tgpgsign = false\n"
                         "[init]\n\tdefaultBranch = main\n")
    env.update(HOME=run_.home, TMPDIR=run_.tmp, GIT_CONFIG_GLOBAL=gitconfig, GIT_CONFIG_NOSYSTEM="1",
               GH_CONFIG_DIR=os.path.join(run_.home, ".config", "gh"), XDG_CONFIG_HOME=os.path.join(run_.home, ".config"),
               RAIL_CLOUD="0", CLAUDE_CODE_SESSION_ID=run_.session)
    env.update(sealed.project_env(project, store_root, base={}))
    env["PATH"] = os.path.join(run_.copy, ".rail", "bin") + os.pathsep + env.get("PATH", os.defpath)
    env.update(extra or {})
    return env


# --- reading a stream ----------------------------------------------------------------------------------


def read_stream(path):
    """The last result line of a stream file, or None."""
    result = None
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("type") == "result":
                result = data
    return result


def again_reason(path):
    """Why a run that ended in an error should run again: a rate-limit or overload error, or a failed sign-in, in its
    stream. None when its result is not an error or the stream names no such error."""
    result = read_stream(path)
    if result and not result.get("is_error"):
        return None
    if result and result.get("api_error_status") in (429, 529):
        return f"api error {result['api_error_status']}"
    if not os.path.exists(path):
        return None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "result" or data.get("error") or data.get("subtype") == "api_error":
                text = json.dumps({k: data.get(k) for k in ("result", "error", "errors", "message", "api_error_status")})
                if AGAIN.search(text):
                    return AGAIN.search(text).group(0)
                if SIGN_IN.search(text):
                    return f"sign-in failed ({SIGN_IN.search(text).group(0)})"
    return None


def role_of(code):
    """The arm's role a rail work run takes, by its brief's code: its env, its cost proxy and the report's role."""
    return "contract" if code in CONTRACT_CODES else "worker"


def says_done(exit_code, result):
    """Whether a plain run's change counts as merged: the command exited 0 within its time, its last result line is a
    success, and the last non-empty line of the reply is DONE. Spaces, backticks, asterisks and a closing period
    around it are ignored; anything else on the line, NOT DONE included, is not DONE."""
    if exit_code != 0 or not result or result.get("is_error") or result.get("subtype") != "success":
        return False
    lines = [line for line in str(result.get("result") or "").splitlines() if line.strip()]
    return bool(lines) and lines[-1].strip("`*_ .") == "DONE"


# --- Rail ----------------------------------------------------------------------------------------------


def rail_overrides(arm, conf):
    """The config tables the bench writes for an arm: the arm's own, with the worker's stream copied for the taint
    search."""
    out = arm.rail_overrides(conf)
    return out


def rail_config(project, arm, conf, seeded=None):
    """The .rail/config.toml a Rail run gets: `seeded` (the config rail init wrote), the project's, the arm's."""
    config = rail_install.config_for(project, rail_overrides(arm, conf), seeded)
    worker = config.setdefault("worker", {})
    if not worker.get("command"):
        raise BenchError(f"arm {arm.name}: no worker command, in the arm or the project's Rail config")
    if armsmod.RESUME.search(worker["command"]):
        raise BenchError(f"arm {arm.name}: the [worker] command it gets (the project's, or Rail's seed's) resumes a"
                         " session; give the arm a worker command: no bench arm resumes a worker session")
    worker["command"] = worker["command"] + STREAM_TEE
    worker["timeout_minutes"] = conf["worker_minutes"]
    review = config.setdefault("review", {})
    review["command"] = REVIEW_URL + (review.get("command") or engine_default("review", "command"))
    return config


def engine_default(table, key):
    """A default of the engine's config, read from the engine the copy gets."""
    sys.path.insert(0, os.path.join(BENCH, os.pardir, "engine"))
    try:
        from rail import config as engine_config
    finally:
        sys.path.pop(0)
    return engine_config.DEFAULTS[table][key]


def stopped(answer):
    """End the run at STUCK: the engine's drop, which its script (`rail next --ticket NN`) or any later `rail next` makes,
    removes the ticket's worktree and branch, and with them the change at the stop."""
    if (answer.get("reason") or {}).get("code") == "STUCK":
        raise Ended("STUCK", detail=((answer.get("action") or {}).get("brief") or "")[:300])


class RailDriver:
    def __init__(self, ctx, state):
        self.ctx, self.state = ctx, state
        self.r = ctx.run

    # --- talking to rail ---

    def env(self, role_envs=(), extra=None):
        merged = {}
        for role in role_envs:
            merged.update(self.ctx.arm.env(role, self.ctx.conf, self.r.path))
        merged.update(extra or {})
        return child_env(self.ctx.conf, self.r, self.ctx.project, self.ctx.store, merged)

    def rail(self, args, roles=(), extra=None):
        self.ctx.check_clock()
        launcher = os.path.join(self.r.copy, ".rail", "bin", "rail")
        proc = subprocess.Popen(self.ctx.locked([sys.executable, launcher, *args, "--json"]), cwd=self.r.copy, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, env=self.env(roles, extra),
                                start_new_session=True)
        try:
            out, err = proc.communicate(timeout=self.ctx.remaining())
        except subprocess.TimeoutExpired:
            kill(proc)  # the whole group: a worker rail work started goes too
            proc.communicate()
            raise Ended("WALL_CLOCK")
        try:
            answer = json.loads(out)
        except ValueError:
            raise Ended("RAIL_ERROR", detail=f"rail {' '.join(args)} exited {proc.returncode}: {out[-500:]}{err[-500:]}")
        self.state["steps"] += 1
        self.r.log("rail", args=args, code=(answer.get("reason") or {}).get("code"), ok=answer.get("ok", True),
                   steps=[f"{s['step']}:{s.get('result', s['status'])}" for s in answer.get("steps", [])])
        return answer

    def status(self):
        rows = self.rail(["status"]).get("tickets", [])
        return {row["ticket"]: row for row in rows}

    # --- the loop ---

    def file(self):
        """File the request as rail intake files an issue: the request verbatim, the contract left to write."""
        s = self.ctx.situation
        brief = os.path.join(self.r.path, "request.md")
        write(brief, s.body + "\n")
        answer = self.rail(["intake", "--external-id", f"bench#{s.id}", "--title", s.title, "--brief", brief])
        created = answer.get("created") or []
        if not created:
            raise Ended("INTAKE_FAILED", detail=json.dumps(answer)[:500])
        self.state["ticket"] = created[0]
        self.save("intake")

    def save(self, name):
        self.state["elapsed"] = self.ctx.elapsed()
        self.r.save_stage(name, dict(self.state), self.ctx.project.build_dirs, self.ctx.conf["piece_mb"])

    def work(self, nn, code):
        role = role_of(code)
        self.state["runs"] += 1
        stream = self.r.stream(self.state["runs"], role)
        extra = {"BENCH_STREAM": stream, "BENCH_ROLE": role}
        extra.update(self.ctx.role_url(role))
        answer = self.rail(["work", nn], roles=("worker",) + (("contract",) if role == "contract" else ()),
                           extra=extra)
        if (answer.get("reason") or {}).get("code") != "WORKED":
            raise Ended((answer.get("reason") or {}).get("code") or "WORK_ERROR")
        worked = answer.get("worked") or {}
        self.state["worked"].append(dict({k: worked.get(k) for k in ("code", "model", "effort", "end", "cost_usd",
                                                                     "turns", "minutes") if worked.get(k) is not None},
                                         role=role))
        if worked.get("end") == "error":
            why = again_reason(stream)
            if why:
                raise Ended("AGAIN", detail=why)
        # the command rail work returned runs next; a run resumed from this stage runs it first
        self.state["pending"] = (answer.get("action") or {}).get("command")
        if role == "worker":
            self.state["worker_runs"] += 1
            self.save(f"work-{self.state['worker_runs']}")
        else:
            self.state["contract_runs"] += 1
        return answer

    def script(self, command):
        try:
            words = shlex.split(command)
        except ValueError:
            words = []
        if not words or words[0] != "rail":
            raise Ended("SCRIPT", detail=command)
        args = words[1:]
        reviews = args[:1] in (["advance"], ["sweep"])  # the commands that run the reviewer and consult
        roles = ("review", "consult") if reviews else ()
        extra = {}
        if reviews:
            extra.update(self.ctx.role_url("consult"))
            if self.ctx.proxies.get("review"):
                extra["BENCH_URL_REVIEW"] = self.ctx.proxies["review"]
        answer = self.rail(args, roles=roles, extra=extra)
        self.state["pending"] = None
        if args[:1] == ["advance"] and any(s["step"] in REVIEW_STEPS and s["status"] == "ran"
                                           for s in answer.get("steps", [])):
            self.state["review_rounds"] += 1
            self.save(f"review-{self.state['review_rounds']}")
        stopped(answer)
        return answer

    def after(self, answer):
        """Save the stage after the contract is accepted, once: the first answer about the ticket in a later state."""
        if self.state["contract_saved"] or answer.get("ticket") != self.state["ticket"]:
            return
        if answer.get("state") not in (None, "new"):
            self.state["contract_saved"] = True
            self.save("contract")

    def loop(self):
        nn = self.state["ticket"]
        if self.state.get("pending"):  # resumed from the stage saved after a worker run: its command first
            self.after(self.script(self.state["pending"]))
        for _ in range(500):
            overlay(self.ctx, self.r.copy)  # a claim makes a worktree from the base: the arm's files go in it too
            answer = self.rail(["next"])
            self.after(answer)
            stopped(answer)
            if not answer.get("ok", True):
                raise Ended(answer["reason"]["code"], detail=answer["reason"]["message"][:300])
            code = answer["reason"]["code"]
            action = answer.get("action") or {}
            kind, ticket = action.get("kind"), answer.get("ticket")
            if kind == "agent_task":
                if not ticket or code not in WORK_CODES:
                    raise Ended(code)
                overlay(self.ctx, self.r.copy)
                self.after(self.work(ticket, code))
                self.after(self.script(self.state["pending"]))
            elif kind == "script":
                self.after(self.script(action["command"]))
            elif kind == "person_wait":
                waits = answer.get("waits") or [{"ticket": ticket, "needs": code}]
                rows = self.status()
                wait = waits[0]
                if wait["needs"] not in PERSON_WAITS or rows.get(wait["ticket"], {}).get("tier") != "PERSON":
                    raise Ended(wait["needs"])
                self.state["person_acts"].append(wait["needs"])
                self.after(self.rail(["accept", wait["ticket"]]))
            else:
                if self.status().get(nn, {}).get("state") == "merged":
                    raise Ended("MERGED", merged=True)
                raise Ended(code, detail=action.get("brief", "")[:300])
        raise Ended("LOOP")

    # --- what the run changed ---

    def changes(self, merged):
        """(the merged change or None, the change at the stop): patches from the commit Rail was installed in."""
        base, copy = self.r.base, self.r.copy
        if merged:
            patch = grademod.diff(copy, base, "main")
            return patch, patch
        nn = self.state.get("ticket")
        wt = os.path.join(copy, ".claude", "worktrees", nn) if nn else None
        if wt and os.path.exists(os.path.join(wt, ".git")):
            return None, grademod.diff(wt, base)
        branches = git(["for-each-ref", "--format=%(refname:short)", f"refs/heads/{nn}-*"], copy).split() if nn else []
        if branches:
            return None, grademod.diff(copy, base, branches[0])
        return None, b""


class Context:
    """What a run needs: the bench config, the store, the situation, the arm, the run, and its clock."""

    def __init__(self, conf, store, situation, arm, run_, proxies=None, lock=None):
        self.conf, self.store, self.situation, self.arm, self.run = conf, store, situation, arm, run_
        self.project = situation.project
        self.clock = Clock()
        self.before = 0.0
        self.proxies = proxies or {}  # {role: url}
        self.lock = lock  # {port: unix socket} when the children's network is locked, else None
        self.sock_dir = None

    def locked(self, argv):
        """argv, run in a network of its own when the run is locked."""
        return netlock.wrap(argv, self.lock) if self.lock is not None else argv

    def elapsed(self):
        return self.before + self.clock.seconds()

    def remaining(self):
        return max(1.0, 60 * self.conf["run_minutes"] - self.elapsed())

    def check_clock(self):
        if self.elapsed() >= 60 * self.conf["run_minutes"]:
            raise Ended("WALL_CLOCK")

    def role_url(self, role):
        """ANTHROPIC_BASE_URL for one role, when a cost proxy runs for it."""
        url = self.proxies.get(role)
        return {"ANTHROPIC_BASE_URL": url} if url else {}


# --- runs ----------------------------------------------------------------------------------------------


def fresh_state():
    return {"ticket": None, "runs": 0, "worker_runs": 0, "contract_runs": 0, "review_rounds": 0, "person_acts": [],
            "worked": [], "contract_saved": False, "steps": 0, "elapsed": 0.0, "pending": None}


def default_plan(store_root, situation):
    """The fake agent's plan for a situation: an AUTO contract whose check is Rail's verify, and the upstream fix as
    its work. It is the oracle walking through the loop."""
    fix = sealed.fix_diff(store_root, situation)
    with open(fix, "rb") as f:
        paths = grademod.changed_paths(f.read())
    scope = sorted({(p.split("/", 1)[0] + "/**") if "/" in p else p for p in paths + situation.hidden_tests})
    check = situation.project.rail_config.get("commands", {}).get("verify") or "true"
    return {"contract": {"tier": "AUTO", "scope": scope, "check": check, "why": "The request asks for it."},
            "work": [{"patch": fix}], "review": [], "plain": {"patch": fix}}


def run_id(situation, arm, n, origin=None):
    base = f"{situation.project.name}.{situation.id}.{arm.name}"
    if origin:
        base = f"{origin['run']}.from-{origin['stage']}.{arm.name}"
    return f"{base}.{n}"


def create(conf, store_root, situation, arm, rid, origin=None, plan=None, session=None):
    """Make the run's folder and its run.toml. Returns the Run."""
    path = os.path.join(store_root, "runs", rid)
    os.makedirs(path, exist_ok=True)
    meta = sealed.meta(store_root, situation)
    data = {"id": rid, "project": situation.project.path, "set": situation.project.set,
            "project_name": situation.project.name, "situation": situation.id, "arm": arm.name, "arm_file": arm.path,
            "plain": arm.plain, "session": session or f"bench-{rid}", "start": meta["commit"], "created": now_iso(),
            "framework": git(["rev-parse", "HEAD"], os.path.dirname(BENCH), check=False).strip()}
    if origin:
        data["origin"] = origin
    write(os.path.join(path, "run.toml"), tomlw.dumps(data))
    plan_path = os.path.join(path, "fake-plan.json")
    if plan:
        shutil.copyfile(plan, plan_path)
    elif any("fake-plan.json" in v for r in armsmod.ROLES for v in arm.roles[r].get("env", {}).values()):
        if origin and os.path.exists(os.path.join(origin["path"], "fake-plan.json")):
            shutil.copyfile(os.path.join(origin["path"], "fake-plan.json"), plan_path)
        else:
            write(plan_path, json.dumps(default_plan(store_root, situation), indent=1))
    return runs.Run(path)


def set_meta(run_, **fields):
    data = dict(run_.meta)
    data.update(fields)
    write(os.path.join(run_.path, "run.toml"), tomlw.dumps(data))
    run_.meta = data


def start_rail(ctx):
    """A new Rail run: the copy, Rail installed, the request filed."""
    r = ctx.run
    if os.path.exists(r.copy):
        shutil.rmtree(r.copy)
    sealed.fresh(ctx.store, ctx.situation, r.copy)
    env = child_env(ctx.conf, r, ctx.project, ctx.store)
    base = rail_install.install(r.copy, ctx.project, files=ctx.arm.files, env=env,
                                make_config=lambda seeded: rail_config(ctx.project, ctx.arm, ctx.conf, seeded))
    set_meta(r, base=base)
    state = fresh_state()
    d = RailDriver(ctx, state)
    d.file()
    return d


def overlay(ctx, copy):
    """Put the arm's config and files in place of the copy's, in the root and every worktree, without a commit: git
    is told to leave them out (skip-worktree for tracked files, info/exclude for new ones), so a ship never commits
    them. Run after a restore with another arm, and after every claim, which makes a new worktree from the base."""
    seeded = rail_install.seeded(copy, ctx.run.base)
    files = {".rail/config.toml": tomlw.dumps(rail_config(ctx.project, ctx.arm, ctx.conf, seeded))}
    for dest, src in ctx.arm.files.items():
        with open(src) as f:
            files[dest] = f.read()
    changed = False
    for root in [copy] + runs.worktree_paths(copy):
        for dest, text in files.items():
            target = os.path.join(root, dest)
            current = open(target).read() if os.path.exists(target) else None
            if current == text:
                continue
            changed = True
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as f:
                f.write(text)
            tracked = git(["ls-files", "--", dest], root).strip()
            if tracked:
                git(["update-index", "--skip-worktree", "--", dest], root)
            else:
                exclude = os.path.join(git(["rev-parse", "--git-common-dir"], root).strip(), "info", "exclude")
                exclude = exclude if os.path.isabs(exclude) else os.path.join(root, exclude)
                os.makedirs(os.path.dirname(exclude), exist_ok=True)
                with open(exclude, "a") as f:
                    f.write(f"/{dest}\n")
    return changed


def drive_rail(ctx, resume_meta=None):
    """Run or go on with a Rail run. Returns the end: {end, merged, detail}."""
    r = ctx.run
    if resume_meta is None:
        try:
            d = start_rail(ctx)
        except Ended as e:
            return {"end": e.code, "merged": False, **e.fields}, None
    else:
        d = RailDriver(ctx, resume_meta["state"])
    try:
        d.loop()
    except Ended as e:
        end = {"end": e.code, "merged": bool(e.fields.get("merged")), **{k: v for k, v in e.fields.items()
                                                                          if k != "merged"}}
    if end["end"] != "AGAIN":
        try:
            d.save("end")
        except Exception as e:  # the end stage is a convenience; the grade does not need it
            r.log("error", what="end stage", detail=str(e)[:300])
    return end, d


# --- plain ---------------------------------------------------------------------------------------------


def plain_prompt(situation):
    p = situation.project
    commands = p.rail_config.get("commands", {})
    lines = [situation.request.strip(), "", PLAIN_SENTENCE, "", "The project's commands:"]
    if commands.get("setup"):
        lines.append(f"- set up: `{commands['setup']}`")
    if commands.get("verify"):
        lines.append(f"- check the whole project: `{commands['verify']}`")
    lines.append(f"- run given test files: `{p.commands['test_files']}`, with {{files}} the files")
    lines.append(f"- run one package's tests: `{p.commands['test_package']}`, with {{package}} the package")
    return "\n".join(lines) + "\n"


def drive_plain(ctx):
    r = ctx.run
    if os.path.exists(r.copy):
        shutil.rmtree(r.copy)
    sealed.fresh(ctx.store, ctx.situation, r.copy)
    for name in r.stream_files():
        os.unlink(os.path.join(r.streams, name))
    stream = r.stream(1, "worker")
    env = child_env(ctx.conf, r, ctx.project, ctx.store, {**ctx.arm.env("worker", ctx.conf, r.path),
                                                           **ctx.role_url("worker")})
    env["PATH"] = env["PATH"].split(os.pathsep, 1)[1]  # no rail here
    timeout = min(60 * ctx.conf["worker_minutes"], ctx.remaining())
    r.log("plain", command=ctx.arm.command("worker", ctx.conf))
    command = ctx.arm.command("worker", ctx.conf)
    if ctx.lock is not None:
        command = shlex.join(ctx.locked(["bash", "-c", command]))
    with open(stream, "w") as out:
        code, _ = run(command, r.copy, env, timeout, stdin=plain_prompt(ctx.situation), stdout=out)
    result = read_stream(stream)
    worked = {"end": "timeout" if code is None else ("done" if code == 0 else "error")}
    for key in ("total_cost_usd", "num_turns", "subtype", "session_id"):
        if result and result.get(key) is not None:
            worked[key] = result[key]
    state = fresh_state()
    state["runs"] = state["worker_runs"] = 1
    state["worked"] = [worked]
    if code is None:
        return {"end": "WALL_CLOCK", "merged": False}, state
    if code != 0 or (result and result.get("is_error")):
        why = again_reason(stream)
        if why:
            return {"end": "AGAIN", "merged": False, "detail": why}, state
    merged = says_done(code, result)
    return {"end": "DONE" if merged else "NOT_DONE", "merged": merged}, state


# --- the whole run ---------------------------------------------------------------------------------------


def go(ctx, plan=None):
    """Run, or go on with, the run in ctx.run: drive it unless it has ended, then grade it unless it has a result.
    Returns the result."""
    r = ctx.run
    if r.result:
        return r.result
    if not r.ended:
        servers = start_network(ctx)
        try:
            drive(ctx)
        finally:
            for server in servers.values():
                server.close()
            if ctx.sock_dir:
                os.rmdir(ctx.sock_dir)
    return grade_ended(ctx)


def start_network(ctx):
    """Start a cost proxy per role and decide the lock; note in run.toml whether every part of the run was locked.
    Returns {role: Proxy}."""
    conf, r = ctx.conf, ctx.run
    can_lock = netlock.available() and conf["network_lock"] != "off"
    if conf["network_lock"] == "required" and not can_lock:
        raise BenchError("network_lock = 'required', but this machine can't lock a child's network (it needs Linux, "
                         "root and unshare)")
    servers = {}
    if conf["proxy"]:
        # the Unix sockets the lock's relays reach, in /tmp: a socket's path must be short
        folder = ctx.sock_dir = tempfile.mkdtemp(prefix="bench-sock-", dir="/tmp") if can_lock else None
        upstream = conf["upstream"] or proxy.default_upstream()
        for role in ROLES:
            sock = os.path.join(folder, role) if folder else None
            servers[role] = proxy.Proxy(role, os.path.join(r.path, f"proxy-{role}.jsonl"), upstream, sock)
        ctx.proxies = {role: s.url for role, s in servers.items()}
    if can_lock:
        ctx.lock = {s.port: s.sock for s in servers.values()}
    source_locked = True
    if r.meta.get("origin"):
        source_locked = runs.Run(r.meta["origin"]["path"]).meta.get("locked", False)
    set_meta(r, locked=bool(can_lock and source_locked and r.meta.get("locked", True)))
    r.log("network", locked=can_lock, proxies=sorted(servers))
    return servers


def drive(ctx):
    """Drive the run to its end and write ended.toml."""
    r = ctx.run
    stages = r.stages()
    if ctx.arm.plain:
        r.log("start" if not r.log_lines() else "restart", arm=ctx.arm.name)
        end, state = drive_plain(ctx)
    else:
        resume = stages[-1] if stages else None
        if resume:
            ctx.before = resume["state"].get("elapsed", 0.0)
            env = child_env(ctx.conf, r, ctx.project, ctx.store)
            source = runs.Run(resume["source"]) if resume.get("source") else r
            runs.restore(source, resume, r, ctx.situation, ctx.store, env, ctx.project.build_dirs)
            overlay(ctx, r.copy)
            r.log("resume", stage=resume["name"])
        else:
            r.log("start", arm=ctx.arm.name)
        end, d = drive_rail(ctx, resume)
        state = d.state if d else fresh_state()
    end.update(minutes=round(ctx.elapsed() / 60, 2), ended=now_iso())
    if not end["merged"] and end["end"] != "AGAIN":
        limited = {role: code for role, code in proxy.last_statuses(r.path, ROLES).items() if code in (429, 529)}
        if limited:
            end.update(end="AGAIN", detail=f"the last request of {', '.join(sorted(limited))} got "
                                           f"{', '.join(str(c) for c in sorted(set(limited.values())))}")
    r.write_ended({"end": end, "state": state})
    r.log("ended", **end)


def grade_ended(ctx):
    """Grade an ended run once: the taint search, then the grade unless it is to run again. Returns the result."""
    r = ctx.run
    ended = r.ended
    end, state = ended["end"], ended["state"]
    result = {"run": r.id, "situation": ctx.situation.id, "set": ctx.project.set, "project": ctx.project.name,
              "arm": ctx.arm.name, "plain": ctx.arm.plain, "end": end["end"], "merged": end["merged"],
              "again": end["end"] == "AGAIN", "minutes": end.get("minutes", 0.0), "person_acts": state["person_acts"],
              "worker_runs": state["worker_runs"], "contract_runs": state["contract_runs"],
              "review_rounds": state["review_rounds"], "worked": state["worked"],
              "cost_usd": round(sum(w.get("cost_usd") or w.get("total_cost_usd") or 0 for w in state["worked"]), 4),
              "turns": sum(w.get("turns") or w.get("num_turns") or 0 for w in state["worked"])}
    if end.get("detail"):
        result["detail"] = str(end["detail"])[:500]
    if r.meta.get("origin"):
        result["origin"] = r.meta["origin"]
    meta = sealed.meta(ctx.store, ctx.situation)
    hits = taint.search([os.path.join(r.streams, f) for f in r.stream_files()], ctx.situation, meta["fix"],
                        folders=(os.path.join(ctx.store, "sealed"), os.path.dirname(ctx.project.path)))
    result["tainted"] = bool(hits)
    if hits:
        result["taint"] = hits[:20]
    result["unsearched"] = ["review", "consult"] if not ctx.arm.plain else []
    result["locked"] = bool(r.meta.get("locked"))
    result["models"] = sorted({m for m in (ctx.arm.roles[role].get("model") for role in armsmod.ROLES) if m}
                              | {w["model"] for w in state["worked"] if w.get("model")})
    used = proxy.usage(r.path, ROLES)
    if used:
        result["usage"] = used
    if not result["again"]:
        result.update(grade_run(ctx, end, state))
    r.write_result(result)
    r.log("graded", right_merged=result.get("right_merged"), right_stop=result.get("right_stop"))
    return result


def grade_run(ctx, end, state):
    r = ctx.run
    rounds = ctx.conf["grade_rounds"]
    if ctx.arm.plain:
        stop = grademod.diff(r.copy, r.start)
        merged_patch = stop if end["merged"] else None
    else:
        d = RailDriver(ctx, state)
        merged_patch, stop = d.changes(end["merged"])
    write(os.path.join(r.path, "change.diff"), stop.decode(errors="replace"))
    graded = grademod.grade(ctx.store, ctx.situation, stop, rounds)
    out = {"right_stop": graded["right"], "grade_why": graded.get("why", ""), "aside": graded["aside"],
           "packages": graded["packages"]}
    if merged_patch is not None:
        out["right_merged"] = graded["right"] if merged_patch == stop else grademod.grade(
            ctx.store, ctx.situation, merged_patch, rounds)["right"]
    return out


def restart(conf, store_root, source, stage, situation, arm, n=1, plan=None):
    """A new run that starts from the state saved before `stage` in run `source`, and runs on with `arm`'s roles."""
    if source.plain or arm.plain:
        raise BenchError("a plain run has no stages to restart from, and a plain arm can't go on with a Rail run")
    before = source.stage_before(stage)
    origin = {"run": source.id, "path": source.path, "stage": stage, "restored": before["name"]}
    rid = run_id(situation, arm, n, origin)
    runs.aside_if_again(os.path.join(store_root, "runs", rid))
    target = runs.Run(os.path.join(store_root, "runs", rid)) if os.path.exists(
        os.path.join(store_root, "runs", rid, "run.toml")) else None
    if target is None:
        target = create(conf, store_root, situation, arm, rid, origin=origin, plan=plan, session=source.session)
        set_meta(target, base=source.base)
        os.makedirs(target.stages_dir, exist_ok=True)
        with open(os.path.join(target.stages_dir, "stages.jsonl"), "w") as f:
            for s in source.stages()[:before["index"]]:
                s = dict(s, source=s.get("source") or source.path)
                f.write(json.dumps(s) + "\n")
    return target
