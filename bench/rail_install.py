"""Install Rail into a copy with no agent. `rail init` copies the engine and the seed files and needs no agent; its
second half, the init task (the project's commands, ## Areas, person_paths, rules), is what an agent would write, and
the project file gives it instead: [rail.config] becomes .rail/config.toml. One commit on main holds it all."""

import copy as copymod
import json
import os
import shutil
import subprocess
import sys

from . import tomlw
from .common import FRAMEWORK, BenchError, commit_all, write


def config_for(project, overrides=None):
    """Rail's config for the project with an arm's overrides on top, table by table."""
    config = copymod.deepcopy(project.rail_config)
    for table, values in (overrides or {}).items():
        if isinstance(values, dict):
            config.setdefault(table, {}).update(values)
        else:
            config[table] = values
    return config


def rail_env(base, home=None):
    """What a rail command needs: no cloud flows, nothing of the forge."""
    env = dict(base)
    env["RAIL_CLOUD"] = "0"
    for key in ("GITHUB_ACTIONS", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE", "RAIL_TICKET", "RAIL_WORKER"):
        env.pop(key, None)
    if home:
        env["HOME"] = home
    return env


def install(root, project, overrides=None, files=None, env=None, framework=FRAMEWORK):
    """Run `rail init` in `root`, write the config and the arm's files, and commit. Returns the commit id."""
    env = rail_env(env if env is not None else os.environ)
    done = subprocess.run([sys.executable, os.path.join(framework, "bin", "rail"), "init", "--json"], cwd=root,
                          env=env, capture_output=True, text=True)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = {}
    if done.returncode != 0 or not answer.get("ok", False):
        raise BenchError(f"rail init failed in {root}: {done.stdout[-2000:]}{done.stderr[-2000:]}")
    write(os.path.join(root, ".rail", "config.toml"), tomlw.dumps(config_for(project, overrides)))
    for dest, src in (files or {}).items():
        target = os.path.join(root, dest)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(src, target)
    return commit_all(root, "Install Rail for the bench", env)
