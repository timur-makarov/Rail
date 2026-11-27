"""The projects inside a repository, derived from the tree in front of the engine (rail docs languages).

A folder that tracks a language's manifest is a project, named after its folder (`root` for the repository's root),
with the language profile's commands run in that folder. A workspace gives one project for each member, and its own
files say which member uses which. `[[projects]]` in the config changes a derived project, or declares one that no
manifest marks. Nothing is written anywhere: the projects are worked out from the files of one tree each time they
are needed, so a manifest a ticket or a person adds is a project from then on.

A `Layout` is the projects of one tree. `reach` gives the projects a change reaches, over the base's layout and the
branch's. `Layout.uncovered` lists the files inside no project, which the triage step asks about (rail docs triage).
"""

import functools
import json
import os
import posixpath
import re
import shlex
import tomllib

from . import gitx
from .util import RailError, match_any

# The language profiles: data, in the engine's own folder, so a project's copy of the engine has them.
PROFILES = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "profiles")
ROOT = "root"                                # the name of the project at the repository's root
OWNED = (".rail", ".claude", ".github")      # the folders Rail and the host own: never asked about
# What the ships of tickets were answered about uncovered folders: a file for each ticket that was answered.
COVERAGE = re.compile(r"\.rail/journal/[^/]+-coverage\.json$")
NOTHING, NEEDS = "nothing-to-check", "needs-checks"


@functools.lru_cache(maxsize=None)
def profiles():
    """{name: the profile's data}, `common` among them."""
    found = {}
    for name in sorted(os.listdir(PROFILES)) if os.path.isdir(PROFILES) else []:
        path = os.path.join(PROFILES, name, "profile.toml")
        if os.path.isfile(path):
            with open(path, "rb") as f:
                found[name] = tomllib.load(f)
    return found


def languages():
    return {name: data for name, data in profiles().items() if name != "common"}


def common():
    return profiles().get("common") or {}


# --- a tree ---------------------------------------------------------------------------------------


class Tree:
    """The tracked files of one tree, and the text of the few the derivation reads."""

    def __init__(self, files, read):
        self.files, self.names = files, set(files)
        self._read, self._texts = read, {}

    def load(self, paths):
        """Read these files in one go; a later `text` of one of them asks nothing."""
        missing = [p for p in dict.fromkeys(paths) if p in self.names and p not in self._texts]
        if missing:
            self._texts.update(self._read(missing))

    def text(self, path):
        self.load([path])
        return self._texts.get(path)

    def toml(self, path):
        try:
            return tomllib.loads(self.text(path) or "")
        except (tomllib.TOMLDecodeError, ValueError):
            return {}

    def json(self, path):
        try:
            found = json.loads(self.text(path) or "{}")
        except ValueError:
            return {}
        return found if isinstance(found, dict) else {}


def at(root, ref):
    """The tree of a commit."""
    files = [p for p in gitx.git(["ls-tree", "-r", "-z", "--name-only", ref], root).stdout.split("\0") if p]

    def read(paths):
        held = gitx.read_blobs([f"{ref}:{p}" for p in paths], root)
        return {p: held.get(f"{ref}:{p}") for p in paths}
    return Tree(files, read)


def checkout(root):
    """The tree a checkout tracks, with the files as they are on disk."""
    files = [p for p in gitx.git(["ls-files", "-z"], root).stdout.split("\0") if p]

    def read(paths):
        found = {}
        for p in paths:
            try:
                with open(os.path.join(root, p), encoding="utf-8", errors="replace") as f:
                    found[p] = f.read()
            except OSError:
                found[p] = None
        return found
    return Tree(files, read)


# --- workspaces -----------------------------------------------------------------------------------
#
# Each reader gives [{profile, root, members: {folder: package name}, uses: {folder: [member folders]}, virtual}]:
# the members a workspace's own files name, and the dependencies between them those files show. The files are read
# and nothing is run. `virtual`: the root is no package of its own, so it is no project.


def _join(folder, name):
    return f"{folder}/{name}" if folder else name


def _under(folder, path):
    """Whether `path` is the folder or lies below it."""
    return not folder or path == folder or path.startswith(folder + "/")


def _rel(folder, path):
    return path[len(folder) + 1:] if folder else path


def _norm(folder, rel):
    found = posixpath.normpath(posixpath.join(folder, rel))
    return "" if found == "." else found


def _members(root, folders, include, exclude=()):
    """The folders below a workspace's root that its globs name."""
    return [f for f in sorted(folders) if f != root and _under(root, f) and match_any(include, _rel(root, f))
            and not match_any(exclude, _rel(root, f))]


def _pep503(name):
    return re.sub(r"[-_.]+", "-", str(name)).lower()


def _requirement(text):
    """The package a PEP 508 requirement names."""
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(text))
    return _pep503(m.group(1)) if m else ""


def _uv(tree, folders):
    found = []
    for root in sorted(folders):
        data = tree.toml(_join(root, "pyproject.toml"))
        uv = (data.get("tool") or {}).get("uv") or {}
        space = uv.get("workspace")
        if not isinstance(space, dict):
            continue
        members = {}
        for folder in _members(root, folders, space.get("members") or [], space.get("exclude") or []):
            name = (tree.toml(_join(folder, "pyproject.toml")).get("project") or {}).get("name")
            members[folder] = name or posixpath.basename(folder)
        own = (data.get("project") or {}).get("name")
        if own:
            members[root] = own  # the root package is a member too
        names = {_pep503(name): folder for folder, name in members.items()}
        uses = {}
        for folder in members:
            mine = tree.toml(_join(folder, "pyproject.toml"))
            project = mine.get("project") or {}
            wanted = list(project.get("dependencies") or [])
            for group in (project.get("optional-dependencies") or {}).values():
                wanted += group
            for group in (mine.get("dependency-groups") or {}).values():
                wanted += [item for item in group if isinstance(item, str)]
            wanted = {_requirement(item) for item in wanted}
            sources = {**(uv.get("sources") or {}), **(((mine.get("tool") or {}).get("uv") or {}).get("sources") or {})}
            local = {_pep503(name) for name, source in sources.items() if isinstance(source, dict) and source.get("workspace")}
            uses[folder] = sorted({names[n] for n in wanted & local if n in names and names[n] != folder})
        found.append({"profile": "python", "root": root, "members": members, "uses": uses, "virtual": not own})
    return found


def _yaml_list(text, key):
    """The strings of one top-level list of a YAML file, written as a block (`- item` lines) or inline (`[a, b]`).
    It reads what a pnpm-workspace.yaml holds, not YAML."""
    items, inside = [], False
    for line in (text or "").splitlines():
        bare = line.split(" #")[0].rstrip()
        if not bare.strip():
            continue
        if not line[:1].isspace() and not bare.startswith("-"):
            inside = bare.split(":")[0].strip() == key
            rest = bare.split(":", 1)[1].strip() if ":" in bare else ""
            if inside and rest.startswith("["):
                items += [item.strip().strip("'\"") for item in rest.strip("[]").split(",") if item.strip()]
        elif inside and bare.strip().startswith("- "):
            items.append(bare.strip()[2:].strip().strip("'\""))
    return items


def _pnpm(tree, folders, files):
    found = []
    for path in files:
        if posixpath.basename(path) != "pnpm-workspace.yaml":
            continue
        root = posixpath.dirname(path)
        globs = _yaml_list(tree.text(path), "packages")
        members = {}
        for folder in _members(root, folders, [g for g in globs if not g.startswith("!")],
                               [g[1:] for g in globs if g.startswith("!")]):
            members[folder] = tree.json(_join(folder, "package.json")).get("name") or posixpath.basename(folder)
        names = {name: folder for folder, name in members.items()}
        uses = {}
        for folder in members:
            data = tree.json(_join(folder, "package.json"))
            wanted = set()
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                group = data.get(key)
                wanted |= {name for name, spec in (group.items() if isinstance(group, dict) else [])
                           if isinstance(spec, str) and spec.startswith("workspace:")}
            uses[folder] = sorted({names[n] for n in wanted if n in names and names[n] != folder})
        # The root's package.json is the workspace's own file: it holds the tools, not a package of the product.
        found.append({"profile": "typescript", "root": root, "members": members, "uses": uses, "virtual": True})
    return found


def _cargo(tree, folders):
    found = []
    for root in sorted(folders):
        data = tree.toml(_join(root, "Cargo.toml"))
        space = data.get("workspace")
        if not isinstance(space, dict):
            continue
        members = {}
        for folder in _members(root, folders, space.get("members") or [], space.get("exclude") or []):
            name = (tree.toml(_join(folder, "Cargo.toml")).get("package") or {}).get("name")
            members[folder] = name if isinstance(name, str) else posixpath.basename(folder)
        own = (data.get("package") or {}).get("name")
        if own:
            members[root] = own
        shared = space.get("dependencies") or {}
        uses = {}
        for folder in members:
            mine, used = tree.toml(_join(folder, "Cargo.toml")), set()
            for table in ("dependencies", "dev-dependencies", "build-dependencies"):
                for name, spec in (mine.get(table) or {}).items():
                    if not isinstance(spec, dict):
                        continue
                    if spec.get("path"):
                        used.add(_norm(folder, spec["path"]))
                    elif spec.get("workspace") and isinstance(shared.get(name), dict) and shared[name].get("path"):
                        used.add(_norm(root, shared[name]["path"]))
            uses[folder] = sorted(f for f in used if f in members and f != folder)
        found.append({"profile": "rust", "root": root, "members": members, "uses": uses, "virtual": not own})
    return found


def _go_work(tree, folders, files):
    found = []
    for path in files:
        if posixpath.basename(path) != "go.work":
            continue
        root, text = posixpath.dirname(path), tree.text(path) or ""
        named = re.findall(r"^use\s+([^\s(]\S*)", text, re.M)
        for block in re.findall(r"^use\s*\(([^)]*)\)", text, re.M | re.S):
            named += [line.split("//")[0].strip() for line in block.splitlines() if line.split("//")[0].strip()]
        members = {}
        for rel in named:
            folder = _norm(root, rel.strip('"'))
            if folder in folders:
                module = re.search(r"^module\s+(\S+)", tree.text(_join(folder, "go.mod")) or "", re.M)
                members[folder] = module.group(1) if module else folder
        modules = {name: folder for folder, name in members.items()}
        uses = {}
        for folder in members:
            mod, used = tree.text(_join(folder, "go.mod")) or "", set()
            for line in mod.splitlines():
                words = line.split("//")[0].split()
                if words[:1] == ["require"]:
                    words = words[1:]
                if words and words[0] in modules:
                    used.add(modules[words[0]])
                if "=>" in words and words[-1].startswith("."):
                    used.add(_norm(folder, words[-1]))
            uses[folder] = sorted(f for f in used if f in members and f != folder)
        found.append({"profile": "go", "root": root, "members": members, "uses": uses, "virtual": root not in members})
    return found


# --- the projects of a tree ---------------------------------------------------------------------


def _manager(profile, names, folder, space):
    """The profile's package manager for a project: the first whose lockfile is tracked in the project's folder or at
    its workspace's root; with none tracked, the first whose `without_lockfile` names a file tracked in the folder,
    with that file's name in its commands; else the first one. `lock` is the lockfile's path."""
    managers = profile.get("managers") or []
    spots = [folder] + ([space] if space is not None and space != folder else [])
    for m in managers:
        for spot in spots:
            if _join(spot, m["lockfile"]) in names:
                return dict(m, lock=_join(spot, m["lockfile"]))
    for m in managers:
        loose = sorted(posixpath.basename(p) for p in names if posixpath.dirname(p) == folder
                       and match_any([m.get("without_lockfile") or ""], posixpath.basename(p)))
        if loose:
            swap = lambda text: text.replace(m["lockfile"], loose[0])  # noqa: E731
            return dict(m, lockfile=loose[0], lock=_join(folder, loose[0]), setup=swap(m["setup"]),
                        verify=[dict(part, run=swap(part["run"])) for part in m["verify"]])
    return dict(managers[0], lock=_join(spots[-1], managers[0]["lockfile"])) if managers else None


def _commands(manager, member, type_check):
    """(setup, the parts of verify) for a project: a part is {part, tool, run}. A member of a workspace runs the
    commands that name it. A part named `types` is left out where type checking is off, and an `audit` runs only when
    the change touches the lockfile."""
    if not manager:
        return "", []
    named = member if member and re.fullmatch(r"[\w@./+-]+", member) else shlex.quote(member or "")
    setup = (manager.get("member_setup") if member else None) or manager["setup"]
    parts = []
    for part in manager["verify"]:
        if part["part"] == "types" and type_check is False:
            continue
        run = ((part.get("member") if member else None) or part["run"]).replace("{name}", named)
        if part["part"] == "audit":
            run = f'{{ git diff --quiet "$RAIL_BASE"...HEAD -- {shlex.quote(":(top)" + manager["lock"])} || {run}; }}'
        parts.append({"part": part["part"], "tool": part["tool"], "run": run})
    return setup.replace("{name}", named), parts


class Layout:
    """The projects of one tree: `projects`, sorted by name, each

        {name, folder, paths, profile, manager, setup, verify, parts, uses, workspace, member, type_check, entry}

    `folder` is where the project's commands run ("" for the repository's root, None for a project that an entry of
    [[projects]] declares and no manifest marks, whose commands run at the root). `parts` are the parts of the
    profile's verify, [] once an entry replaced it. `workspace` is its workspace's root folder, `member` its package
    name there. `entry`: a [[projects]] entry changed or declared it."""

    def __init__(self, tree, config):
        self.tree = tree
        skip = set(common().get("ignore") or [])
        other = (config.get("init") or {}).get("other_manifests") or []
        self.files = [p for p in tree.files if not skip.intersection(p.split("/")[:-1])]
        marks = {name: set() for name in languages()}
        for path in self.files:
            base = posixpath.basename(path)
            for name, profile in languages().items():
                if match_any(profile["manifests"], base) and not match_any(other, path):
                    marks[name].add(posixpath.dirname(path))
        tree.load([p for p in self.files if posixpath.basename(p) in (
            "pyproject.toml", "Cargo.toml", "package.json", "go.mod", "go.work", "pnpm-workspace.yaml")
            and not match_any(other, p)] + [p for p in self.files if COVERAGE.match(p)])
        self.workspaces = (_uv(tree, marks.get("python") or set()) + _pnpm(tree, marks.get("typescript") or set(), self.files)
                           + _cargo(tree, marks.get("rust") or set()) + _go_work(tree, marks.get("go") or set(), self.files))
        found = []
        for name, profile in languages().items():
            spaces = [w for w in self.workspaces if w["profile"] == name]
            member_of = {folder: w for w in spaces for folder in w["members"]}
            virtual = {w["root"] for w in spaces if w["virtual"]}
            chosen = []
            # A manifest inside another project's folder counts for that project, unless a workspace names it a member.
            for folder in sorted(marks[name] - virtual, key=lambda f: (f.count("/") + bool(f), f)):
                if folder in member_of or not any(above != folder and _under(above, folder) for above in chosen):
                    chosen.append(folder)
            for folder in chosen:
                space = member_of.get(folder)
                type_check = None
                if profile.get("type_check_file"):
                    type_check = any(posixpath.basename(p) == profile["type_check_file"] and _under(folder, p)
                                     for p in self.files)
                manager = _manager(profile, tree.names, folder, space["root"] if space else None)
                member = space["members"][folder] if space else None
                setup, parts = _commands(manager, member, type_check)
                found.append({"name": folder or ROOT, "folder": folder, "paths": [_join(folder, "**")], "profile": name,
                              "manager": manager["name"] if manager else None, "setup": setup,
                              "verify": " && ".join(part["run"] for part in parts), "parts": parts,
                              "uses": list(space["uses"].get(folder) or []) if space else [],
                              "workspace": space["root"] if space else None, "member": member,
                              "type_check": type_check, "entry": False})
        # Two languages' manifests in one folder give two projects there: each is named after the folder and its language.
        shared = {p["folder"] for p in found if sum(q["folder"] == p["folder"] for q in found) > 1}
        for p in found:
            if p["folder"] in shared:
                p["name"] = f"{p['folder'] or ROOT}-{p['profile']}"
        named = {(p["profile"], p["folder"]): p["name"] for p in found}
        for p in found:
            p["uses"] = sorted(named[(p["profile"], folder)] for folder in p["uses"] if (p["profile"], folder) in named)
        by_name = {p["name"]: p for p in found}
        for entry in config.get("projects") or []:
            p = by_name.get(entry["name"])
            if p is None:
                p = {"name": entry["name"], "folder": None, "paths": [], "profile": None, "manager": None, "setup": "",
                     "verify": "", "parts": [], "uses": [], "workspace": None, "member": None, "type_check": None}
                found.append(p)
                by_name[p["name"]] = p
            p["entry"] = True
            if "paths" in entry:
                p["paths"] = list(entry["paths"])
            if "setup" in entry:
                p["setup"] = entry["setup"]
            if "verify" in entry:
                p["verify"], p["parts"] = entry["verify"], []
            if "uses" in entry:
                p["uses"] = sorted(set(p["uses"]) | set(entry["uses"]))  # an entry adds to what the files show
        self.projects = sorted(found, key=lambda p: p["name"])
        self.by_name = {p["name"]: p for p in self.projects}
        self._own = {}

    def owners(self, path):
        """The projects a file is inside: those whose paths match it. Of the projects that hold their folder, such as
        a repository's root and a service below it, the file is inside the deepest one only."""
        hit = [p for p in self.projects if match_any(p["paths"], path)]
        whole = [p for p in hit if p["folder"] is not None and p["paths"] == [_join(p["folder"], "**")]]
        deepest = max((len(p["folder"]) for p in whole), default=0)
        return [p for p in hit if p not in whole or len(p["folder"]) == deepest]

    def workspace_of(self, path):
        """The workspace whose own file this is: a manifest, a lockfile or the workspace's file at its root. A change
        to one reaches the workspace's members and no project outside it."""
        folder, base = posixpath.dirname(path), posixpath.basename(path)
        for w in self.workspaces:
            profile = languages()[w["profile"]]
            names = [m["lockfile"] for m in profile.get("managers") or []]
            if profile.get("workspace"):
                names += [profile["workspace"], profile["workspace"] + ".sum"]
            if folder == w["root"] and (base in names or match_any(profile["manifests"], base)):
                return w
        return None

    def members(self, workspace):
        """The names of a workspace's projects."""
        return [p["name"] for p in self.projects if p["profile"] == workspace["profile"]
                and p["folder"] in workspace["members"]]

    def uncovered(self):
        """{folder: [file types]}: the tracked files inside no project, by folder and type. Left out: the files at
        the repository's root, the folders Rail and the host own, vendored, installed and built folders, and a
        workspace's own files. A file's folder here is the top-most one that holds no project's file; a file beside
        projects, such as services/README.md, counts for the folder it is in. A type is the file's extension, or its
        name where it has none."""
        loose, held = [], set()
        for path in self.files:
            if self.owners(path):
                parts = path.split("/")[:-1]
                held.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
            elif "/" in path and path.split("/")[0] not in OWNED and not self.workspace_of(path):
                loose.append(path)
        found = {}
        for path in loose:
            parts = path.split("/")[:-1]
            folder = next(("/".join(parts[:i]) for i in range(1, len(parts) + 1) if "/".join(parts[:i]) not in held),
                          "/".join(parts))
            found.setdefault(folder, set()).add(file_type(path))
        return {folder: sorted(types) for folder, types in sorted(found.items())}

    def loose(self, folder):
        """The files of one uncovered folder, as `uncovered` counts them."""
        return [p for p in self.files if _under(folder, p) and p != folder and not self.owners(p)
                and not self.workspace_of(p)]

    def answered(self):
        """What the tree's coverage files hold, as one: {folder: {types, answer, holds, ticket}}. Each ticket whose
        ship was answered about a folder has a file of its own, so two tickets never write the same one. Where
        several name a folder, the answer is the latest ticket's and the types are everyone's."""
        held = {}
        for path in sorted((p for p in self.files if COVERAGE.match(p)), key=_ticket_of):
            for folder, record in read_coverage(self.tree.text(path)).items():
                types = set((held.get(folder) or {}).get("types") or []) | set(record.get("types") or [])
                held[folder] = dict(record, types=sorted(types), ticket=posixpath.basename(path).split("-")[0])
        return held

    def unanswered(self):
        """The uncovered folders nothing has been answered about, and those that hold a file type the answer did not
        see: {folder: [file types]}."""
        held = self.answered()
        return {folder: types for folder, types in self.uncovered().items()
                if not set(types) <= set((held.get(folder) or {}).get("types") or [])}


def file_type(path):
    base = posixpath.basename(path)
    return posixpath.splitext(base)[1].lower() or base


def read_coverage(text):
    try:
        found = json.loads(text or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in found.items() if isinstance(v, dict)} if isinstance(found, dict) else {}


def write_coverage(held):
    return json.dumps({folder: held[folder] for folder in sorted(held)}, indent=1) + "\n"


def coverage_file(ticket):
    """The file a ticket's answers about uncovered folders go in. Only the engine writes it."""
    return f".rail/journal/{ticket}-coverage.json"


def _ticket_of(path):
    number = posixpath.basename(path).split("-")[0]
    return (int(number) if number.isdigit() else 0, path)


# --- what a change reaches ------------------------------------------------------------------------


def check(layout):
    """Refuse a [[projects]] entry whose `uses` names no project, one that declares a project and gives it no paths,
    and a cycle of `uses`."""
    for p in layout.projects:
        for used in p["uses"]:
            if used not in layout.by_name:
                close = [name for name in layout.by_name if name != p["name"]]
                raise RailError(f"config: the [[projects]] entry '{p['name']}' uses '{used}', which is no project."
                                f" The projects: {', '.join(close) or 'none'}")
        if p["folder"] is None and not p["paths"]:
            raise RailError(f"config: the [[projects]] entry '{p['name']}' names no project a tracked manifest marks,"
                            " so it declares one and needs `paths`")
    state = {}

    def walk(name, trail):
        if state.get(name) == "done":
            return
        if state.get(name) == "open":
            loop = trail[trail.index(name):] + [name]
            raise RailError(f"config: the projects' `uses` go in a circle: {' -> '.join(loop)}")
        state[name] = "open"
        for used in layout.by_name[name]["uses"]:
            walk(used, trail + [name])
        state[name] = "done"
    for p in layout.projects:
        walk(p["name"], [])


def reach(branch, base, files):
    """The names of the projects a change of these files reaches, in the order their checks run: a project before
    the projects that use it. A file reaches the projects it is inside, on the branch and on the base, and every
    project that uses one of them, through `uses` to the end. A workspace's own file reaches the workspace's members.
    A file inside no project reaches every project. The projects are the branch's: one the change removes has no
    checks left to run."""
    hit, everything = set(), False
    for path in files:
        for layout in (branch, base):
            hit.update(p["name"] for p in layout.owners(path))
            space = layout.workspace_of(path)
            if space:
                hit.update(layout.members(space))
        # Inside no project: judged on the branch where the file still is, and on the base where the change removed it.
        where = branch if path in branch.tree.names else base
        everything = everything or not (where.owners(path) or where.workspace_of(path))
    users = {}
    for layout in (base, branch):
        for p in layout.projects:
            for used in p["uses"]:
                users.setdefault(used, set()).add(p["name"])
    if everything:
        hit = set(branch.by_name)
    queue = list(hit)
    while queue:
        for user in users.get(queue.pop(), ()):
            if user not in hit:
                hit.add(user)
                queue.append(user)
    return in_order(branch, [name for name in hit if name in branch.by_name])


def in_order(layout, names):
    """The names, a project before the projects that use it, and by name among those."""
    left, done = sorted(names), []
    while left:
        ready = [n for n in left if not any(u in left and u != n for u in layout.by_name[n]["uses"])] or left[:1]
        done.append(ready[0])
        left.remove(ready[0])
    return done


# --- what a profile brings besides the commands ---------------------------------------------------


def _scoped(paths, glob):
    """A profile's glob, for each of a project's paths that names a whole folder: web/** and **/*.test.* give
    web/**/*.test.*."""
    return [(path[:-2] + glob) for path in paths if path == "**" or path.endswith("/**")]


def extras(layouts):
    """What the profiles of these layouts' projects bring besides the commands, each applied to the paths of the
    projects of that profile: {rules, tests, migration_paths, generated}. A rule carries `within`, the paths it
    applies to. Nothing of it is written into the config: it is added to what the config holds when that is read.
    `origins` says where each scoped glob came from: {glob: (the project's path, the profile's glob)}."""
    paths = {}
    for layout in layouts:
        for p in layout.projects:
            if p["profile"]:
                found = paths.setdefault(p["profile"], [])
                found += [path for path in p["paths"] if path not in found]
    out = {"rules": [], "tests": [], "migration_paths": [], "generated": [], "origins": {}}
    for name in sorted(paths):
        profile = languages()[name]
        out["rules"] += [dict(rule, within=list(paths[name])) for rule in profile.get("rules") or []]
        for key in ("tests", "migration_paths", "generated"):
            for glob in profile.get(key) or []:
                for path in paths[name]:
                    for scoped in _scoped([path], glob):
                        out["origins"].setdefault(scoped, (path, glob))
                        if scoped not in out[key]:
                            out[key].append(scoped)
    return out
