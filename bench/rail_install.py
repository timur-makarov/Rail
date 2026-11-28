"""Install Rail into a copy with no agent. `rail init` copies the engine and the seed files and needs no agent; its
second half, the init task (the project's commands, ## Areas, person_paths, rules), is what an agent would write, and
the project file gives it instead: [rail.config] goes on top of the .rail/config.toml `rail init` wrote, table by
table, as the init task edits that file. So the seed's [guides], rules and models stay unless the project or the arm
sets its own. Two commits on main: what `rail init` wrote, then the bench's config and the arm's files."""

import copy as copymod
import json
import os
import shutil
import subprocess
import sys
import tomllib

from . import tomlw
from .common import FRAMEWORK, BenchError, commit_all, git, write


def config_for(project, overrides=None, seeded=None):
    """Rail's config for the project: the config `rail init` wrote (`seeded`), then the project's [rail.config], then an
    arm's overrides, each on top of the last, table by table."""
    config = copymod.deepcopy(seeded or {})
    for layer in (project.rail_config, overrides or {}):
        for table, values in layer.items():
            if isinstance(values, dict) and isinstance(config.get(table), dict):
                config[table].update(copymod.deepcopy(values))
            else:
                config[table] = copymod.deepcopy(values)
    return config


def seeded(root, base):
    """The config `rail init` wrote in a copy whose Rail was installed at commit `base`: its parent's."""
    return tomllib.loads(git(["show", f"{base}^:.rail/config.toml"], root))


def rail_env(base, home=None):
    """What a rail command needs: no cloud flows, nothing of the forge."""
    env = dict(base)
    env["RAIL_CLOUD"] = "0"
    for key in ("GITHUB_ACTIONS", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE", "RAIL_TICKET", "RAIL_WORKER"):
        env.pop(key, None)
    if home:
        env["HOME"] = home
    return env


def install(root, project, make_config=None, files=None, env=None, framework=FRAMEWORK):
    """Run `rail init` in `root` and commit what it wrote; then write the config, `make_config(seeded)` or else
    config_for(project, seeded=seeded) from the config init wrote, and the arm's files, and commit. Returns the second
    commit's id."""
    env = rail_env(env if env is not None else os.environ)
    done = subprocess.run([sys.executable, os.path.join(framework, "bin", "rail"), "init", "--json"], cwd=root,
                          env=env, capture_output=True, text=True)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        answer = {}
    if done.returncode != 0 or not answer.get("ok", False):
        raise BenchError(f"rail init failed in {root}: {done.stdout[-2000:]}{done.stderr[-2000:]}")
    commit_all(root, "Install Rail for the bench: rail init", env)
    path = os.path.join(root, ".rail", "config.toml")
    with open(path) as f:
        init_config = tomllib.loads(f.read())
    config = make_config(init_config) if make_config else config_for(project, seeded=init_config)
    write(path, tomlw.dumps(config))
    for dest, src in (files or {}).items():
        target = os.path.join(root, dest)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(src, target)
    return commit_all(root, "Install Rail for the bench", env)
