"""`.rail/config.toml`: the whole config surface, with defaults and type checks."""

import copy
import difflib
import os
import tomllib

from .util import RailError

REVIEW_COMMAND = (
    "claude -p --safe-mode --system-prompt-file .rail/engine/reviewer.md "
    "--tools Read,Grep,Glob,Bash,Edit,Write --allowedTools Bash,Edit,Write "
    "--disallowedTools 'Bash(git push *)' --output-format json "
    "--json-schema \"$(cat .rail/engine/review-v1.json)\""
)

DEFAULTS = {
    "base_branch": "main",
    "person_paths": [".rail/bin/**", ".rail/engine/**", ".rail/config.toml", ".claude/**", ".github/workflows/**"],
    "migration_paths": ["**/migrations/**"],
    "commands": {"setup": "", "verify": "", "provision": "", "timeout_secs": 900, "base_checks": True},
    "size": {"cap": 600, "exclude": []},
    "review": {"command": REVIEW_COMMAND, "model": "", "skip_paths": []},
    "retry": {"budget": 2, "cap": 5},
    "consult": {"command": "claude -p --safe-mode --tools Read,Grep,Glob", "model": ""},
    "claim": {"stale_minutes": 30, "save_minutes": 10},
    "worker": {"ladder": ["claude-sonnet-5-5:medium", "claude-sonnet-5-5:high", "claude-opus-5-5:medium"],
               "person_ladder": ["claude-opus-5-5:medium", "claude-opus-5-5:high"],
               "contract": "claude-opus-5-5:high"},
    "sweep": {"after": 20, "every": 20},
    "map": {"depth": 1, "ignore": []},
    "tests": {"paths": []},
    # A page named in the brief when its situation applies. The pages come with the seed config only: a project
    # whose config has no [guides] table gets no guide.
    "guides": {key: "" for key in ("start", "stuck", "findings", "conflict", "contract", "split", "setup")},
    "rules": [],
    "profiles": [],
}

EFFORTS = ("low", "medium", "high", "xhigh", "max")
RULE_KEYS = {"id": str, "files": str, "forbid": list, "only_in": str, "allow": list, "fix": str, "why": str}
PROFILE_KEYS = {"name": str, "paths": str}
# Arrays of tables: each item's keys and types, and the key every item needs.
TABLE_ARRAYS = {"rules": (RULE_KEYS, "id"), "profiles": (PROFILE_KEYS, "name")}


def _suggest(key, known):
    close = difflib.get_close_matches(key, list(known), n=1)
    return f" (did you mean '{close[0]}'?)" if close else ""


def _check(value, default, where):
    """Check a value against the default's type, recursing into tables. Returns the merged value."""
    if isinstance(default, dict):
        if not isinstance(value, dict):
            raise RailError(f"config: {where} must be a table")
        merged = copy.deepcopy(default)
        for key, item in value.items():
            if key not in default:
                raise RailError(f"config: unknown key '{where}.{key}'{_suggest(key, default)}")
            merged[key] = _check(item, default[key], f"{where}.{key}")
        return merged
    if isinstance(value, bool) != isinstance(default, bool) or not isinstance(value, type(default)):
        raise RailError(f"config: {where} must be {type(default).__name__}")
    if isinstance(default, list) and not all(isinstance(v, str) for v in value):
        raise RailError(f"config: {where} must be a list of strings")
    return value


def _check_item(name, item, n):
    """One table of an array of tables, such as a [[rules]] entry."""
    keys, needed = TABLE_ARRAYS[name]
    if not isinstance(item, dict):
        raise RailError(f"config: {name}[{n}] must be a table")
    for key, value in item.items():
        if key not in keys:
            raise RailError(f"config: unknown key '{name}[{n}].{key}'{_suggest(key, keys)}")
        if not isinstance(value, keys[key]):
            raise RailError(f"config: {name}[{n}].{key} must be {keys[key].__name__}")
    if needed not in item:
        raise RailError(f"config: {name}[{n}] needs {'an' if needed[0] in 'aeiou' else 'a'} {needed}")
    return item


def _check_ladder(config):
    """Each rung of a worker ladder, and worker.contract when it is set, is model:effort."""
    rungs = [(f"worker.{key}[{n}]", rung) for key in ("ladder", "person_ladder")
             for n, rung in enumerate(config["worker"][key])]
    if config["worker"]["contract"]:
        rungs.append(("worker.contract", config["worker"]["contract"]))
    for name, rung in rungs:
        model, _, effort = rung.rpartition(":")
        if not model.strip() or effort not in EFFORTS:
            raise RailError(f"config: {name} must be model:effort, such as \"claude-sonnet-5-5:medium\","
                            f" with an effort of {', '.join(EFFORTS)}; got \"{rung}\"")


def load(root):
    path = os.path.join(root, ".rail", "config.toml")
    if not os.path.exists(path):
        raise RailError("no .rail/config.toml here: this is not a Rail project", code="NOT_A_PROJECT")
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise RailError(f"config: .rail/config.toml is not valid TOML: {e}")
    packs_dir = os.path.join(root, ".rail", "packs")
    config = copy.deepcopy(DEFAULTS)
    for key, value in raw.items():
        if key in TABLE_ARRAYS:
            if not isinstance(value, list):
                raise RailError(f"config: {key} must be an array of tables ([[{key}]])")
            config[key] = [_check_item(key, item, n) for n, item in enumerate(value)]
        elif key in DEFAULTS:
            config[key] = _check(value, DEFAULTS[key], key)
        elif isinstance(value, dict) and os.path.isdir(os.path.join(packs_dir, key)):
            config[key] = value  # a pack's own section; the pack reads it
        else:
            raise RailError(f"config: unknown key '{key}'{_suggest(key, DEFAULTS)}")
    _check_ladder(config)
    return config
