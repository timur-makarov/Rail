"""`rail init`: set a project up. It never overwrites a file of the project's."""

import json
import os
import re
import shutil
import stat
import tomllib

from . import gitx, layout
from .util import RailError

# The framework this engine came from: engine/rail/init.py -> the framework's root.
FRAMEWORK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

LAUNCHER = '''#!/usr/bin/env python3
"""This project's rail launcher: it runs the engine in ../engine. The SessionStart hook puts this folder on PATH."""
import os
import sys

if sys.version_info < (3, 11):
    sys.stderr.write("rail needs Python 3.11 or newer (found %d.%d). On macOS: brew install python\\n" % sys.version_info[:2])
    sys.exit(2)

# Compiled engine files go to the home folder: no __pycache__ under .rail/engine to commit by mistake, and the
# engine isn't compiled again on every call.
sys.pycache_prefix = os.path.join(os.path.expanduser("~"), ".cache", "rail", "pycache")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "engine"))
from rail.cli import main  # noqa: E402

sys.exit(main())
'''

# Not tested with a model run: the clause "so a person merges it" in step 3 of both tasks below, which said before
# that a person also approves the contract; and step 1 of both, which said before that rail init wrote each
# language's commands into [commands].
INIT_TASK = """Rail is installed, and this project isn't set up for it yet: .rail/config.toml isn't on {base}.
{projects}Read the repository to learn its stack, then propose each of these to the person and make the changes they confirm:
1. The checks. Rail works the repository's projects out from its tracked manifests each time it needs them, and for
   the projects a change reaches it runs each one's `setup` and `verify` in the project's folder: `rail doctor`
   prints the projects with their commands. Nothing is written for them. Change .rail/config.toml only where that
   is not right:
   - a [[projects]] entry with a derived project's `name` puts the repository's own `setup` or `verify` in the
     default's place. Do that where a Makefile target, a package.json script or a CI step already runs a part
     (tests, lint, types, format), because it holds what the project knows;
   - an entry with a new `name` declares a part of the repository that no manifest marks: its `paths`, and the
     `setup` and `verify` that check it. `uses` names the projects it depends on where no import shows that, such
     as a frontend that calls a backend's API: a change in a used project runs the user's checks too;
   - [commands] `setup` and `verify` hold only what belongs to the whole repository, and run after the projects'
     own: a secret scan over the branch's commits ($RAIL_BASE..HEAD; RAIL_BASE is set for every command). When no
     scanner is installed, ask the person which to install, or leave it out and say so.
   Every tool a command names has to be on the machine that runs it. `provision` in [commands] is the command that
   installs those tools, as root, on a cloud session's machine and on a CI runner. It never runs on the person's
   own computer, where installing is theirs.
2. ARCHITECTURE.md with a `## Areas` table: | Area | Paths | Holds |, one row per area. Paths are globs, separated
   by commas; Holds says what lives there in a bug reporter's words. Cover every directory at depth {depth}; hidden
   directories such as .rail and .claude need no row, and neither do files at the root. At most 150 lines.
3. [kinds] in .rail/config.toml: a person is asked only about changes a revert doesn't undo. Keep the defaults,
   and for each kind id list the paths that hold it in this project: schemas (data-shape), auth (access),
   infrastructure code (infrastructure), payment code (money), code that emails or pays real people
   (external-effect), and the files that set an agent's permissions, tools or spend (controls). A ticket that touches
   one is PERSON, so a person merges it. Every other ticket is AUTO and gets the reviewer
   before the engine merges it. [review] skip_paths lists paths whose changes need no reviewer, such as docs; leave
   it empty when unsure.
4. The [[rules]] in .rail/config.toml: keep, drop or add structure rules for this project.
5. .worktreeinclude at the root: one glob per line for local files a ticket worktree needs that git doesn't
   track, such as .env. Leave it out when there are none.
6. [tools.NAME] in .rail/config.toml: one table for each thing the work reaches outside the repository (a service
   with a key, a CLI that signs in, an MCP server): `use`, one line the agents read; `env`, the names of the
   variables it needs, never a value; `probe`, a fast command that changes nothing and fails when the tool is out
   of reach; `ci = true` only for a test or dev key that a pull request's run may be given, with its line in
   .github/workflows/rail.yml.{tools} Leave it out when the work reaches nothing.
If the project already has its own agent workflow, hooks, guards, CI gates or repo map, list them and ask the
person whether to keep, merge or retire each one; until they decide, both run, and a hook of theirs may block a
step below. Then ask the person to make that commit.
Then commit what rail init added together with these changes to {base}. With a remote, push a branch and open a
pull request with `gh api` (gh pr doesn't work in cloud sessions); the person merges it.
Finally run `rail doctor` and make the one-time settings it lists."""


# In a cloud session the machine is nobody's own, and the person is usually away: the agent sets everything up and
# the person confirms it once, by merging the pull request.
INIT_TASK_CLOUD = """Rail is installed, and this project isn't set up for it yet: .rail/config.toml isn't on {base}.
This is a cloud session: the machine is yours to change. Set the project up yourself; the person confirms it all at
once by reading and merging one pull request. {projects}Read the repository to learn its stack, then:
1. The checks. Rail works the repository's projects out from its tracked manifests each time it needs them, and for
   the projects a change reaches it runs each one's `setup` and `verify` in the project's folder: `rail doctor`
   prints the projects with their commands. Nothing is written for them. Change .rail/config.toml only where that
   is not right:
   - a [[projects]] entry with a derived project's `name` puts the repository's own `setup` or `verify` in the
     default's place. Do that where a Makefile target, a package.json script or a CI step already runs a part
     (tests, lint, types, format), because it holds what the project knows;
   - an entry with a new `name` declares a part of the repository that no manifest marks: its `paths`, and the
     `setup` and `verify` that check it. `uses` names the projects it depends on where no import shows that, such
     as a frontend that calls a backend's API: a change in a used project runs the user's checks too;
   - [commands] `setup` and `verify` hold only what belongs to the whole repository, and run after the projects'
     own: a secret scan over the branch's commits ($RAIL_BASE..HEAD; RAIL_BASE is set for every command);
   - [commands] `provision` installs, as root, what those commands need that this machine lacks: scanners, CLIs,
     services. It runs once per cloud machine and on each CI runner. Install the tools now with the command you
     write there, and run each project's commands until they pass.
2. ARCHITECTURE.md with a `## Areas` table: | Area | Paths | Holds |, one row per area. Paths are globs, separated
   by commas; Holds says what lives there in a bug reporter's words. Cover every directory at depth {depth}; hidden
   directories such as .rail and .claude need no row, and neither do files at the root. At most 150 lines.
3. [kinds] in .rail/config.toml: a person is asked only about changes a revert doesn't undo. Keep the defaults,
   and for each kind id list the paths that hold it in this project: schemas (data-shape), auth (access),
   infrastructure code (infrastructure), payment code (money), code that emails or pays real people
   (external-effect), and the files that set an agent's permissions, tools or spend (controls). A ticket that touches
   one is PERSON, so a person merges it. Every other ticket is AUTO and gets the reviewer
   before the engine merges it. [review] skip_paths lists paths whose changes need no reviewer, such as docs; leave
   it empty when unsure.
4. The [[rules]] in .rail/config.toml: keep, drop or add structure rules for this project.
5. [tools.NAME] in .rail/config.toml: one table for each thing the work reaches outside the repository (a service
   with a key, a CLI that signs in, an MCP server): `use`, one line the agents read; `env`, the names of the
   variables it needs, never a value; `probe`, a fast command that changes nothing and fails when the tool is out
   of reach; `ci = true` only for a test or dev key that a pull request's run may be given, with its line in
   .github/workflows/rail.yml.{tools} Leave it out when the work reaches nothing.
If the project already has its own agent workflow, hooks, guards, CI gates or repo map, leave them running and list
them in the pull request for the person to decide: keep, merge or retire.
Then commit what rail init added together with these changes to a new branch, push it, and open a pull request with
`gh api` (gh pr doesn't work in cloud sessions). In its description say what you chose and why, and list what only
the person can do, because a cloud session can't change a repository's settings:
- merge this pull request;
- import .rail/ruleset.json at Settings > Rules > Rulesets > New ruleset > Import a ruleset: it requires the
  rail check and a pull request on {base}, and allows squash merges only;
- in Settings > General > Pull Requests: allow squash merging with "Pull request title and description" as the
  default message, and turn on "Automatically delete head branches".
Finally run `rail doctor`. It prints the lines for the cloud environment's setup script: propose them with your
environment tool, so the person approves them once and every later session starts ready."""


INCLUDE = re.compile(r"^<!-- include (.+?) -->$", re.M)


def include(text):
    """A seed file's `<!-- include PAGE[#Heading...] -->` lines, replaced by that text of the framework's page: a
    skill carries what it would otherwise tell the agent to go and read. A heading is written as it stands, spaces
    and all."""
    from .docs import read_part

    def page(m):
        found = read_part(m.group(1), FRAMEWORK)
        if found is None:
            raise RailError(f"the seed includes {m.group(1)}, which isn't there")
        return found
    return INCLUDE.sub(page, text)


def _write(path, text, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    if mode:
        os.chmod(path, mode)


def _merge(project_value, ours):
    """Add our settings to the project's. Existing values win; lists gain the items they lack."""
    for key, value in ours.items():
        if key not in project_value:
            project_value[key] = value
        elif isinstance(project_value[key], dict) and isinstance(value, dict):
            _merge(project_value[key], value)
        elif isinstance(project_value[key], list) and isinstance(value, list):
            project_value[key] += [item for item in value if item not in project_value[key]]
    return project_value


def found(root, config=None):
    """The projects of the files a checkout tracks, as the engine derives them on every call (rail docs languages).
    `config` is the project's config where one is there: its [[projects]] entries and [init] other_manifests."""
    return layout.Layout(layout.checkout(root), config or {}).projects


def toml_string(value):
    """A command as a TOML string: literal where it can be, so the command reads as it runs."""
    return f"'{value}'" if "'" not in value and "\n" not in value else json.dumps(value)


def _set_string(text, table, key, value):
    """The seed config's text with an empty string's value filled in, the line's comment kept."""
    start = text.index(f"\n[{table}]")
    found = re.compile(rf'^{key} = ""', re.M).search(text, start)
    if not found:
        raise RailError(f"the seed config has no empty {key} to fill in under [{table}]")
    return text[:found.start()] + f"{key} = {toml_string(value)}" + text[found.end():]


def _set_list(text, table, key, values):
    """The seed config's text with a list's value replaced, the line's comment kept. table None: a top-level key."""
    start = 0 if table is None else text.index(f"\n[{table}]")
    found = re.compile(rf"^{key} = \[[^\]]*\]", re.M).search(text, start)
    if not found:
        raise RailError(f"the seed config has no {key} to fill in" + (f" under [{table}]" if table else ""))
    return text[:found.start()] + f"{key} = {json.dumps(values)}" + text[found.end():]


def with_secrets(text, projects):
    """The seed config's text with the one command rail init writes for a repository that holds a project: the
    secret scan over the branch's commits, as [commands] verify, which runs after the projects' own checks. The
    projects themselves get no line: they are derived from the tracked manifests each time."""
    secrets = layout.common().get("secrets")
    if not projects or not secrets or tomllib.loads(text)["commands"]["verify"]:
        return text
    return _set_string(text, "commands", "verify", secrets["run"])


def describe(projects):
    """The projects in one line: each with its language and package manager, or with what its entry declares."""
    words = []
    for p in projects:
        if p["profile"]:
            said = ", ".join(filter(None, [p["profile"], p["manager"]]))
            off = layout.languages()[p["profile"]].get("type_check_file") if p["type_check"] is False else None
            words.append(f"{p['name']} ({said}{f', no {off}: type checking off' if off else ''})")
        else:
            words.append(f"{p['name']} (declared in [[projects]])")
    return ", ".join(words)


FOUND = ("Rail finds these projects from the tracked manifests: {found}. ")


def found_line(projects):
    """The init task's sentence on the projects the tree holds; "" when it holds none."""
    return FOUND.format(found=describe(projects)) if projects else ""


def _base_branch(root):
    """The remote's default branch; with no remote, the branch init runs on."""
    head = gitx.git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], root, check=False).stdout.strip()
    if head:
        return head.split("/", 1)[1]
    # A clone made without origin/HEAD (cloud sessions make them): ask the remote, so a setup branch isn't taken for the base.
    asked = gitx.git(["ls-remote", "--symref", "origin", "HEAD"], root, check=False).stdout
    for line in asked.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            return line[len("ref: refs/heads/"):-len("\tHEAD")]
    current = gitx.git(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False).stdout.strip()
    return current or "main"


SKILL_DIR = ".claude/skills"


def skill_dirs(root, asked=None):
    """The folders the skills are written to: `asked` (rail init --skills), else [init] skill_dirs of the project's
    config, else the default. Each is a path from the repository root."""
    dirs = list(asked or [])
    if not dirs:
        try:
            with open(os.path.join(root, ".rail", "config.toml"), "rb") as f:
                dirs = (tomllib.load(f).get("init") or {}).get("skill_dirs") or []
        except (OSError, tomllib.TOMLDecodeError):
            dirs = []
    dirs = [d.strip().strip("/") for d in dirs if isinstance(d, str) and d.strip().strip("/")] or [SKILL_DIR]
    bad = next((d for d in dirs if os.path.isabs(d) or d.startswith("/") or ".." in d.split("/")), None)
    if bad:
        raise RailError(f"a skill folder is a path inside the repository, from its root; got '{bad}'")
    return list(dict.fromkeys(dirs))


def with_skill_dirs(text, dirs):
    """The seed config's text for skill folders other than the default: [init] skill_dirs names them, and the
    [guides] pages that are skills are read from the first."""
    if dirs == [SKILL_DIR]:
        return text
    text = _set_list(text, "init", "skill_dirs", dirs)
    start = text.index("\n[guides]")
    end = text.find("\n[", start + 1)
    end = len(text) if end < 0 else end
    return text[:start] + text[start:end].replace(f'"{SKILL_DIR}/', f'"{dirs[0]}/') + text[end:]


def init(cwd, skills_to=None):
    """Returns the receipts: one step per thing init adds, `not_run` when the project already has it."""
    seed = os.path.join(FRAMEWORK, "seed")
    if not os.path.isdir(seed):
        raise RailError("rail init runs from the framework: use the rail that install put on PATH")
    top = gitx.git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd, check=False)
    if top.returncode != 0:
        raise RailError("not inside a git repository: run git init first", code="NOT_A_PROJECT")
    common = top.stdout.strip()
    root = os.path.dirname(common) if os.path.basename(common) == ".git" else gitx.out(["rev-parse", "--show-toplevel"], cwd)
    receipts = []

    def step(name, done, detail):
        receipt = {"step": name, "status": "ran" if done else "not_run", "detail": detail}
        if done:
            receipt["result"] = "pass"
        receipts.append(receipt)

    rail_dir = os.path.join(root, ".rail")
    engine = os.path.join(rail_dir, "engine")
    if os.path.exists(engine):
        step("engine", False, ".rail/engine is there already; it is the project's")
    else:
        shutil.copytree(os.path.join(FRAMEWORK, "engine"), engine, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        step("engine", True, "copied to .rail/engine")

    launcher = os.path.join(rail_dir, "bin", "rail")
    if os.path.exists(launcher):
        step("launcher", False, ".rail/bin/rail is there already")
    else:
        _write(launcher, LAUNCHER, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        step("launcher", True, "wrote .rail/bin/rail")

    source = os.path.join(rail_dir, "SOURCE")
    if os.path.exists(source):
        step("source", False, ".rail/SOURCE is there already")
    else:
        url = gitx.git(["remote", "get-url", "origin"], FRAMEWORK, check=False).stdout.strip() or FRAMEWORK
        commit = gitx.git(["rev-parse", "HEAD"], FRAMEWORK, check=False).stdout.strip()
        _write(source, f'url = "{url}"\ncommit = "{commit}"\n')
        step("source", True, f"framework {url} at {commit[:12]}")

    try:
        with open(os.path.join(rail_dir, "config.toml"), "rb") as f:
            held = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        held = None
    projects = found(root, held)
    if not projects:
        step("projects", False, "no tracked Python, TypeScript, Rust or Go manifest marks a project. Declare the"
                                " repository's parts in [[projects]] of .rail/config.toml, each with the commands"
                                " that check it")
    else:
        step("projects", held is None, f"found {describe(projects)}. Each is set up and checked with its commands, for the"
                               " changes that reach it; rail doctor prints them. Nothing is written for a project: they"
                               " are worked out from the tracked manifests each time")

    copies = {
        "config.toml": ".rail/config.toml",
        "tickets/TEMPLATE.md": ".rail/tickets/TEMPLATE.md",
        "rail.yml": ".github/workflows/rail.yml",
        "sources/weekly-review.md": ".rail/sources/weekly-review.md",  # a source: the week's merges read together
        "ruleset.json": ".rail/ruleset.json",  # for the person to import in GitHub: a session can't set it. It
                                               # names the default branch, so one file fits every repository
    }
    # The skills a person's session starts, as Claude Code skills. The engine's own pages for the briefs stay in
    # .rail/engine/guides; [guides] names both kinds.
    skills = os.path.join(seed, "skills")
    folders = skill_dirs(root, skills_to)
    skill_copies = [(f"skills/{name}/SKILL.md", f"{folder}/{name}/SKILL.md") for folder in folders
                    for name in sorted(os.listdir(skills)) if os.path.isfile(os.path.join(skills, name, "SKILL.md"))]
    packs = os.path.join(FRAMEWORK, "packs")
    for name in sorted(os.listdir(packs)) if os.path.isdir(packs) else []:
        dest = os.path.join(rail_dir, "packs", name)
        if os.path.exists(dest):
            step(f"pack {name}", False, f".rail/packs/{name} is there already")
        else:
            shutil.copytree(os.path.join(packs, name), dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            step(f"pack {name}", True, f"copied to .rail/packs/{name}")
    for src, dest in [*copies.items(), *skill_copies]:
        target = os.path.join(root, dest)
        if os.path.exists(target):
            step(dest, False, "the project has it already")
            continue
        with open(os.path.join(seed, src)) as f:
            text = f.read()
        if src == "config.toml":
            text = text.replace('base_branch = "main"', f'base_branch = "{_base_branch(root)}"', 1)
            text = with_skill_dirs(with_secrets(text, projects), folders)
        text = include(text)
        _write(target, text)
        step(dest, True, "added")

    # GitHub folds a file marked linguist-generated in a pull request's diff, so a person reads what was written.
    from .rules import LOCKFILES
    try:
        with open(os.path.join(rail_dir, "config.toml"), "rb") as f:
            generated = [g for g in (tomllib.load(f).get("size") or {}).get("exclude") or [] if isinstance(g, str)]
    except (OSError, tomllib.TOMLDecodeError):
        generated = []
    # The profiles of the projects found name their languages' generated files; they are in no config.
    generated += [g for g in layout.extras([layout.Layout(layout.checkout(root), held or {})])["generated"]
                  if g not in generated]
    attributes = os.path.join(root, ".gitattributes")
    had = open(attributes).read() if os.path.exists(attributes) else ""
    # A glob with braces has no spelling in .gitattributes; a lockfile stays in sight, since it says what is installed.
    new = [g for g in generated if "{" not in g and " " not in g and os.path.basename(g) not in LOCKFILES
           and not any(line.split()[:1] == [g] for line in had.splitlines())]
    if new:
        _write(attributes, (had.rstrip("\n") + "\n" if had.strip() else "")
               + "".join(f"{g} linguist-generated\n" for g in new))
        step(".gitattributes", True, f"marked as generated, so GitHub folds them in a diff: {', '.join(new)}")
    else:
        step(".gitattributes", False, "no generated file to mark: [size] exclude is empty and no project's profile names one" if not generated
             else "the generated files are marked already")

    agents = os.path.join(root, "AGENTS.md")
    existing = open(agents).read() if os.path.exists(agents) else ""
    if any(line.strip() == "## Rail" for line in existing.splitlines()):
        step("AGENTS.md", False, "it has a ## Rail section already")
    else:
        with open(os.path.join(seed, "AGENTS.md")) as f:
            section = f.read()
        _write(agents, (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + section)
        step("AGENTS.md", True, "added the ## Rail section")

    claude_md = os.path.join(root, "CLAUDE.md")
    if not os.path.exists(claude_md):
        step("CLAUDE.md", False, "the project has none, and Rail never creates one")
    else:
        text = open(claude_md).read()
        if "@AGENTS.md" in text:
            step("CLAUDE.md", False, "it imports AGENTS.md already")
        else:
            _write(claude_md, text.rstrip("\n") + "\n\n@AGENTS.md\n")
            step("CLAUDE.md", True, "added @AGENTS.md, so Claude Code reads AGENTS.md too")

    settings = os.path.join(root, ".claude", "settings.json")
    with open(os.path.join(seed, "settings.json")) as f:
        ours = json.load(f)
    # The package registries of the languages found, for the agent's own installs.
    domains = list(dict.fromkeys(d for p in projects if p["profile"]
                                 for d in layout.languages()[p["profile"]].get("domains") or []))
    ours["sandbox"]["network"]["allowedDomains"] += domains
    try:
        theirs = json.load(open(settings)) if os.path.exists(settings) else {}
    except ValueError:
        theirs = None
    if theirs is None:
        step(".claude/settings.json", False, "not valid JSON, so left alone; merge seed/settings.json by hand")
    else:
        merged = _merge(json.loads(json.dumps(theirs)), ours)
        if merged == theirs:
            step(".claude/settings.json", False, "it has Rail's settings already")
        else:
            _write(settings, json.dumps(merged, indent=2) + "\n")
            step(".claude/settings.json", True, "merged hooks, permissions, sandbox and Bash timeouts"
                 + (f"; the sandbox allows {', '.join(domains)}" if domains else ""))

    gitignore = os.path.join(root, ".gitignore")
    lines = open(gitignore).read().splitlines() if os.path.exists(gitignore) else []
    with open(os.path.join(seed, "gitignore")) as f:
        missing = [l for l in f.read().splitlines() if l and l not in lines]
    if missing:
        _write(gitignore, "\n".join(lines + missing) + "\n")
        step(".gitignore", True, f"added {', '.join(missing)}")
    else:
        step(".gitignore", False, "it has Rail's lines already")
    return root, receipts
