"""A project file, bench/sets/SET/PROJECT.toml: the repository, its commands, Rail's config for it, and one table per
situation. The loader refuses an unknown key and a value of the wrong type, and says which."""

import datetime
import fnmatch
import os
import re
import shlex
import tomllib

from .common import BenchError

LANGUAGES = ("python", "typescript", "rust", "go")
KINDS = ("crash", "race", "wrong-result", "missing-behaviour", "vague-request")
HALVES = ("work", "held")
# The folders a build makes, left out of saved stages. Per language, added to the project's own build_dirs.
BUILD_DIRS = {"python": [".venv", "__pycache__", ".pytest_cache", ".mypy_cache"], "typescript": ["node_modules", "dist"],
              "rust": ["target"], "go": []}

# Each table's keys: (type, required, default).
PROJECT = {
    "name": (str, True, None),
    "repo": (str, True, None),          # what git clones: a URL, or a local path
    "slug": (str, False, ""),           # OWNER/REPO on the forge, for the taint search; read from a GitHub URL when empty
    "language": (str, True, None),
    "package": (str, False, ""),        # the project's own package name, for the taint search of a fetch
    "tests": (list, True, None),        # globs of test files, such as "tests/**" or "**/*_test.go"
    "clash": (str, False, ""),          # "path" or "dir": which of an arm's test files clash with a hidden one
    "build_dirs": (list, False, []),
}
COMMANDS = {
    "setup": (str, False, ""),          # run once when the sealed copy is built, with the network: fetch dependencies
    "test_files": (str, True, None),    # the given test files; {files} is replaced by them, quoted
    "test_package": (str, True, None),  # one package's tests; {package} is replaced by it, quoted
    "package_of": (str, False, "root"), # root, dir, top, nearest:FILE or regex:PATTERN (see package_of)
    "failed": (str, True, None),        # a regex whose first group names a failing test in the output
    "timeout_minutes": (int, False, 30),
    "env": (dict, False, {}),           # set for every command, such as CARGO_NET_OFFLINE = "true"
}
SITUATION = {
    "id": (str, True, None),
    "request": (str, True, None),       # the issue's title on the first line, then its first message, as first posted
    "start": (str, True, None),         # the commit before the fix
    "hidden_tests": (list, True, None), # test files kept outside the sealed copy, as the fix has them
    "fix": (str, True, None),           # the upstream fix's commit: the oracle grade applies start..fix
    "closed": ((str, datetime.date), True, None),
    "kind": (str, True, None),
    "extra": (list, False, []),         # hidden security tests and planted faults: not built yet (PLAN 4b, 4c)
    "half": (str, True, None),
    "issue": (str, False, ""),          # the issue's URL, for the taint search
    "pull": (int, False, 0),            # the fix's pull request number, for the taint search
}


class Situation:
    def __init__(self, project, data):
        self.project = project
        for key, value in data.items():
            setattr(self, key, value)
        lines = self.request.strip().splitlines()
        self.title = lines[0].strip() if lines else ""
        self.body = "\n".join(lines[1:]).strip()

    @property
    def key(self):
        return f"{self.project.set}/{self.project.name}/{self.id}"


class Project:
    def __init__(self, path, data):
        self.path = os.path.abspath(path)
        self.set = os.path.basename(os.path.dirname(self.path))
        for key, value in data["project"].items():
            setattr(self, key, value)
        self.commands = data["commands"]
        self.rail_config = data.get("rail", {}).get("config", {})
        if "://" not in self.repo and not self.repo.startswith("git@"):
            self.repo = os.path.join(os.path.dirname(self.path), os.path.expanduser(self.repo))  # a local path
        if not self.slug:
            m = re.match(r"(?:https?://|git@)github\.com[/:]([^/]+/[^/]+?)(?:\.git)?/?$", self.repo)
            self.slug = m.group(1) if m else ""
        if not self.clash:
            self.clash = "dir" if self.language == "go" else "path"
        self.build_dirs = list(dict.fromkeys(BUILD_DIRS[self.language] + self.build_dirs))
        self.situations = [Situation(self, s) for s in data["situation"]]

    def situation(self, sid):
        for s in self.situations:
            if s.id == sid:
                return s
        raise BenchError(f"{self.path}: no situation '{sid}'")

    @property
    def timeout(self):
        return 60 * self.commands["timeout_minutes"]

    def is_test(self, path):
        return any(fnmatch.fnmatch(path, glob) for glob in self.tests)

    def test_files_command(self, files):
        return self.commands["test_files"].replace("{files}", " ".join(shlex.quote(f) for f in files))

    def test_package_command(self, package):
        return self.commands["test_package"].replace("{package}", shlex.quote(package))

    def failing(self, output):
        """The failing tests the output names, by the project's `failed` pattern."""
        return sorted(set(m.group(1) for m in re.finditer(self.commands["failed"], output, re.M)))

    def package_of(self, path, root):
        """The package a changed path belongs to, by [commands] package_of:
        root: the whole project ("."); dir: the file's folder; top: its first path part;
        nearest:FILE: the nearest folder above it that holds FILE (such as Cargo.toml or go.mod), else ".";
        regex:PATTERN: the pattern's first group on the path, else "."."""
        rule = self.commands["package_of"]
        if rule == "root":
            return "."
        if rule == "dir":
            return os.path.dirname(path) or "."
        if rule == "top":
            return path.split("/", 1)[0] if "/" in path else "."
        if rule.startswith("nearest:"):
            name = rule.split(":", 1)[1]
            d = os.path.dirname(path)
            while d:
                if os.path.exists(os.path.join(root, d, name)):
                    return d
                d = os.path.dirname(d)
            return "."
        if rule.startswith("regex:"):
            m = re.match(rule.split(":", 1)[1], path)
            return m.group(1) if m else "."
        raise BenchError(f"unknown package_of rule '{rule}'")


def _check(table, spec, where):
    if not isinstance(table, dict):
        raise BenchError(f"{where} must be a table")
    out = {}
    for key, value in table.items():
        if key not in spec:
            raise BenchError(f"{where}: unknown key '{key}'")
        kind = spec[key][0]
        if isinstance(value, bool) and kind is not bool or not isinstance(value, kind):
            raise BenchError(f"{where}.{key} has the wrong type ({type(value).__name__})")
        out[key] = value
    for key, (kind, required, default) in spec.items():
        if key not in out:
            if required:
                raise BenchError(f"{where}: '{key}' is missing")
            out[key] = default.copy() if isinstance(default, (list, dict)) else default
    return out


def load(path):
    """The project file at `path`, checked. Raises BenchError naming the first thing wrong."""
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise BenchError(f"{path}: {e}")
    for key in raw:
        if key not in ("project", "commands", "rail", "situation"):
            raise BenchError(f"{path}: unknown table '{key}'")
    data = {"project": _check(raw.get("project", {}), PROJECT, "project"),
            "commands": _check(raw.get("commands", {}), COMMANDS, "commands")}
    rail = raw.get("rail", {})
    if not isinstance(rail, dict) or set(rail) - {"config"}:
        raise BenchError(f"{path}: [rail] holds only config, the project's .rail/config.toml")
    data["rail"] = rail
    if data["project"]["language"] not in LANGUAGES:
        raise BenchError(f"project.language must be one of {', '.join(LANGUAGES)}")
    if data["project"]["clash"] not in ("", "path", "dir"):
        raise BenchError("project.clash must be path or dir")
    for key in ("tests", "build_dirs"):
        if not all(isinstance(x, str) for x in data["project"][key]):
            raise BenchError(f"project.{key} must be a list of strings")
    if "{files}" not in data["commands"]["test_files"]:
        raise BenchError("commands.test_files must hold {files}")
    if "{package}" not in data["commands"]["test_package"]:
        raise BenchError("commands.test_package must hold {package}")
    try:
        re.compile(data["commands"]["failed"])
    except re.error as e:
        raise BenchError(f"commands.failed is not a regex: {e}")
    if not all(isinstance(v, str) for v in data["commands"]["env"].values()):
        raise BenchError("commands.env values must be strings")
    situations = raw.get("situation", [])
    if not isinstance(situations, list) or not situations:
        raise BenchError(f"{path}: no [[situation]] tables")
    seen = set()
    data["situation"] = []
    for n, item in enumerate(situations):
        s = _check(item, SITUATION, f"situation[{n}]")
        where = f"situation '{s['id']}'"
        if s["id"] in seen:
            raise BenchError(f"{where} is there twice")
        seen.add(s["id"])
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", s["id"]):
            raise BenchError(f"{where}: id may hold letters, digits, '.', '_' and '-' only")
        if s["kind"] not in KINDS:
            raise BenchError(f"{where}: kind must be one of {', '.join(KINDS)}")
        if s["half"] not in HALVES:
            raise BenchError(f"{where}: half must be work or held")
        if not s["hidden_tests"] or not all(isinstance(p, str) and p and not p.startswith("/") and ".." not in
                                            p.split("/") for p in s["hidden_tests"]):
            raise BenchError(f"{where}: hidden_tests must list relative paths")
        if s["extra"]:
            raise BenchError(f"{where}: extra is not built yet (hidden security tests and planted faults, PLAN 4b and"
                             " 4c); leave it empty")
        if isinstance(s["closed"], str):
            try:
                s["closed"] = datetime.date.fromisoformat(s["closed"])
            except ValueError:
                raise BenchError(f"{where}: closed must be a date, YYYY-MM-DD")
        if not s["request"].strip():
            raise BenchError(f"{where}: request is empty")
        data["situation"].append(s)
    return Project(path, data)
