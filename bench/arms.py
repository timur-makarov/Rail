"""An arm, bench/arms/NAME.toml: per role a command, model and effort, and files to put in place of the copy's; or
`plain = true` with only a worker command.

Commands may hold placeholders the bench fills: {model}, {effort}, {budget} (the budget flag's value, the same for
every arm), {tools} (the fixed tool list), {bench} (the bench's folder). A role's `env` sets variables for that role's
runs; {run} in a value is the run's folder.

For Rail the roles map onto .rail/config.toml:
  worker   command -> [worker] command; model and effort -> [worker] ladder and person_ladder, one rung
  contract model and effort -> [worker] contract (Rail runs the contract writer through the worker's command)
  review   command -> [review] command; model -> [review] model
  consult  command -> [consult] command; model -> [consult] model
A role left out keeps what the project's Rail config, or Rail's seed, says."""

import os
import re
import tomllib

from .common import BENCH, BenchError

ROLES = ("worker", "contract", "review", "consult")
ROLE_KEYS = {"command": str, "model": str, "effort": str, "env": dict}
TOP_KEYS = {"description": str, "plain": bool, "files": dict} | {r: dict for r in ROLES}
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# A worker that resumes an earlier session would carry what it saw into a run restarted from a saved stage.
RESUME = re.compile(r"RAIL_SESSION|--resume\b|--continue\b")


class Arm:
    def __init__(self, name, path, data):
        self.name, self.path = name, path
        self.description = data.get("description", "")
        self.plain = data.get("plain", False)
        self.roles = {r: data.get(r, {}) for r in ROLES}
        base = os.path.dirname(path)
        self.files = {dest: os.path.join(base, src) for dest, src in data.get("files", {}).items()}

    def role(self, name):
        return self.roles[name]

    def fill(self, text, role, conf, run_dir=""):
        r = self.roles[role]
        for key, value in (("{model}", r.get("model", "")), ("{effort}", r.get("effort", "")),
                           ("{budget}", str(conf["budget_usd"])), ("{tools}", conf["tools"]), ("{bench}", BENCH),
                           ("{run}", run_dir)):
            text = text.replace(key, value)
        return text

    def command(self, role, conf):
        r = self.roles[role]
        return self.fill(r["command"], role, conf) if r.get("command") else ""

    def env(self, role, conf, run_dir):
        return {k: self.fill(v, role, conf, run_dir) for k, v in self.roles[role].get("env", {}).items()}

    def rail_overrides(self, conf):
        """The .rail/config.toml tables this arm sets."""
        out = {}
        w, c, rv, cs = (self.roles[r] for r in ROLES)
        if w.get("command"):
            out.setdefault("worker", {})["command"] = self.command("worker", conf)
        if w.get("model"):
            rung = f"{w['model']}:{w.get('effort') or 'medium'}"
            out.setdefault("worker", {}).update(ladder=[rung], person_ladder=[rung])
        if c.get("model"):
            out.setdefault("worker", {})["contract"] = f"{c['model']}:{c.get('effort') or 'high'}"
        for role, table in (("review", rv), ("consult", cs)):
            if table.get("command"):
                out.setdefault(role, {})["command"] = self.command(role, conf)
            if table.get("model"):
                out.setdefault(role, {})["model"] = table["model"]
        return out


def path_of(name):
    if name.endswith(".toml") or os.sep in name:
        return os.path.abspath(name)
    return os.path.join(BENCH, "arms", f"{name}.toml")


def load(name):
    path = path_of(name)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError:
        raise BenchError(f"no arm '{name}' ({path})")
    except tomllib.TOMLDecodeError as e:
        raise BenchError(f"{path}: {e}")
    where = os.path.basename(path)
    for key, value in data.items():
        if key not in TOP_KEYS:
            raise BenchError(f"{where}: unknown key '{key}'")
        if not isinstance(value, TOP_KEYS[key]):
            raise BenchError(f"{where}: {key} has the wrong type")
    for role in ROLES:
        for key, value in data.get(role, {}).items():
            if key not in ROLE_KEYS:
                raise BenchError(f"{where}: unknown key '{role}.{key}'")
            if not isinstance(value, ROLE_KEYS[key]):
                raise BenchError(f"{where}: {role}.{key} has the wrong type")
        effort = data.get(role, {}).get("effort")
        if effort and effort not in EFFORTS:
            raise BenchError(f"{where}: {role}.effort must be one of {', '.join(EFFORTS)}")
    worker = data.get("worker", {})
    if RESUME.search(worker.get("command", "")):
        raise BenchError(f"{where}: the worker command resumes a session (RAIL_SESSION, --resume or --continue); no "
                         "bench arm resumes a worker session, so a run restarted from a saved stage starts it fresh")
    if data.get("contract", {}).get("command"):
        raise BenchError(f"{where}: contract.command: Rail runs the contract writer through the worker's command; give"
                         " the contract role a model and effort only")
    if data.get("plain"):
        if not worker.get("command"):
            raise BenchError(f"{where}: a plain arm needs worker.command")
        others = [r for r in ROLES[1:] if data.get(r)] + (["files"] if data.get("files") else [])
        if others:
            raise BenchError(f"{where}: a plain arm has only a worker; remove {', '.join(others)}")
    name = os.path.splitext(os.path.basename(path))[0]
    for dest, src in data.get("files", {}).items():
        if dest.startswith("/") or ".." in dest.split("/"):
            raise BenchError(f"{where}: files: {dest} must be a path inside the copy")
        if not os.path.isfile(os.path.join(os.path.dirname(path), src)):
            raise BenchError(f"{where}: files: no file {src}")
    return Arm(name, path, data)
