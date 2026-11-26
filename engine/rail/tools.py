"""Tools: what the work reaches outside the repository (rail docs tools).

A `[tools.NAME]` table declares a service with a key, a CLI or an MCP server: what it is for, the names of the
variables it needs (never their values), and a probe. The engine lists the tools in the briefs, stops before a
claim while a name is missing, and shows each tool in rail doctor.
"""

import json
import os
import re

from .util import RailError, cloud, could_not_run, run_shell, tail

KEYS = {"use": str, "env": list, "probe": str, "review": bool}
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROBE_SECS = 60
MARK = "<!-- rail-tool: {name} -->"  # on the issue the engine opens for a tool whose name is missing


def check(value):
    """The [tools] table of a config, checked. Returns {name: declaration}."""
    if not isinstance(value, dict):
        raise RailError("config: tools must be a table of tables ([tools.NAME])")
    for name, tool in value.items():
        if not isinstance(tool, dict):
            raise RailError(f"config: tools.{name} must be a table")
        for key, item in tool.items():
            if key not in KEYS:
                raise RailError(f"config: unknown key 'tools.{name}.{key}'")
            if not isinstance(item, KEYS[key]):
                raise RailError(f"config: tools.{name}.{key} must be {KEYS[key].__name__}")
        if not tool.get("use", "").strip():
            raise RailError(f"config: tools.{name} needs use: one line saying what the tool is for, which the agents read")
        for var in tool.get("env", []):
            # A value written where a name belongs would be committed: only a name is accepted.
            if not isinstance(var, str) or not NAME.match(var):
                raise RailError(f"config: tools.{name}.env lists the names of environment variables, never their"
                                " values; one of its entries is no name")
    return value


def _dotenv(root):
    """The names the project root's .env gives a value. Only names are read: a value never leaves the file."""
    names = set()
    try:
        with open(os.path.join(root, ".env"), encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\S)", line)
                if m:
                    names.add(m.group(1))
    except OSError:
        pass
    return names


def missing(project):
    """{tool: [the names it declares that are not set here]}. A name is set when the environment has it, or the
    project root's .env gives it a value."""
    tools = project.config["tools"]
    if not any(tool.get("env") for tool in tools.values()):
        return {}
    local = _dotenv(project.root)
    found = {}
    for name, tool in tools.items():
        gone = [var for var in tool.get("env", []) if not os.environ.get(var) and var not in local]
        if gone:
            found[name] = gone
    return found


def where():
    """Where a person sets a name, for the machine this runs on."""
    if cloud():
        return ("Set it in this cloud environment's settings, as an environment variable; a session started after"
                " that has it. A key the environment's network proxy adds to requests never shows up as a variable:"
                " a tool reached that way declares no env and relies on its probe.")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return "Set it as an Actions secret of the repository, and pass it in the env of the job that runs Rail."
    return ("Set it in the shell that starts the agent, or in the project's .env (which .worktreeinclude copies into"
            " each ticket's worktree).")


def lines(project, review=False):
    """The tools as the lines of a brief: every tool for the worker; only `review = true` ones for the reviewer,
    the refuter and consult."""
    tools = {n: t for n, t in project.config["tools"].items() if t.get("review") or not review}
    if not tools:
        return []
    head = ("Tools this project declares for a reviewer, to read with and never to change anything:" if review else
            "Tools this project declares, for what the work reaches outside the repository:")
    return [head, *[f"- {name}: {tool['use'].strip()}"
                    + (f" (reads {', '.join(tool['env'])})" if tool.get("env") else "") for name, tool in tools.items()]]


def wait_brief(nn, gone):
    """The brief of TOOL_MISSING, for one ticket or for several ("1, 2")."""
    listed = "; ".join(f"{name} needs {', '.join(names)}" for name, names in gone.items())
    return (f"Ticket{'s' if ',' in nn else ''} {nn} can't be claimed on this machine: a tool the project declares has no credential here"
            f" ({listed}). {where()} Nothing was tried, so no attempt is counted. Then run: rail next")


def probe(project, name):
    """Run a tool's probe. Returns (passed, detail); (None, ...) when it has none."""
    command = project.config["tools"][name].get("probe", "").strip()
    if not command:
        return None, "no probe"
    code, output, _ = run_shell(command, project.root, {"RAIL_BASE": project.base_ref}, PROBE_SECS)
    if code == 0:
        return True, "its probe passed"
    said = "timed out" if code is None else could_not_run(code) or f"exit {code}"
    last = tail(output, 3, 300).strip()
    return False, f"its probe failed ({said})" + (f": {last}" if last else "")


def doctor(project):
    """One line per tool for rail doctor: each name present or missing, where to set it, and the probe's result."""
    found, gone = [], missing(project)
    for name, tool in project.config["tools"].items():
        if name in gone:
            found.append((f"tool {name}", False, f"{', '.join(gone[name])} not set here, so its probe was not run."
                                                   f" {where()}"))
            continue
        passed, detail = probe(project, name)
        names = f"{', '.join(tool['env'])} set; " if tool.get("env") else ""
        found.append((f"tool {name}", passed is not False, f"{names}{detail}"))
    return found


def candidates(root):
    """What in the repository looks like a tool, for the init task: MCP servers in .mcp.json, names in .env.example,
    and secrets the workflows read."""
    found = {"mcp": [], "env": [], "secrets": []}
    try:
        with open(os.path.join(root, ".mcp.json"), encoding="utf-8") as f:
            servers = json.load(f).get("mcpServers")
        found["mcp"] = sorted(servers) if isinstance(servers, dict) else []
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with open(os.path.join(root, ".env.example"), encoding="utf-8", errors="replace") as f:
            found["env"] = sorted({m.group(1) for m in map(re.compile(
                r"^\s*#?\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=").match, f) if m})
    except OSError:
        pass
    workflows = os.path.join(root, ".github", "workflows")
    names = set()
    for name in sorted(os.listdir(workflows)) if os.path.isdir(workflows) else []:
        if name.endswith((".yml", ".yaml")):
            try:
                with open(os.path.join(workflows, name), encoding="utf-8", errors="replace") as f:
                    names |= set(re.findall(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)", f.read()))
            except OSError:
                pass
    found["secrets"] = sorted(names - {"GITHUB_TOKEN"})
    return found


def found_line(root):
    """The init task's sentence on what looks like a tool; "" when nothing does."""
    found = candidates(root)
    parts = [f"{what}: {', '.join(found[key])}" for key, what in (
        ("mcp", "MCP servers in .mcp.json"), ("env", "names in .env.example"),
        ("secrets", "secrets the workflows in .github/workflows read")) if found[key]]
    return f" rail init found what may be tools ({'; '.join(parts)}): declare the ones the work uses." if parts else ""


def sync_issues(project, gone):
    """In a cloud session nobody is there to read the answer: one open issue per tool whose name is missing, labelled
    rail:needs-you, and closed once the name is there. Never one per ticket."""
    from .forge import ForgeError

    forge = project.forge
    if not cloud() or not forge or not forge.ok or not any(t.get("env") for t in project.config["tools"].values()):
        return
    try:
        open_ = {name: issue for issue in forge.issues(label="rail:needs-you")
                 for name in project.config["tools"] if MARK.format(name=name) in (issue.get("body") or "")}
        for name, names in gone.items():
            if name not in open_:
                forge.open_issue(
                    f"Rail needs {', '.join(names)} for the tool {name}",
                    f"The project declares the tool `{name}` ({project.config['tools'][name]['use'].strip()}), and a"
                    f" cloud session found {', '.join(f'`{n}`' for n in names)} not set. No ticket is claimed there"
                    f" until it is. {where()}\n\nRail closes this issue once a session finds the name set."
                    f"\n\n{MARK.format(name=name)}", ["rail:needs-you"])
        for name, issue in open_.items():
            if name not in gone:
                forge.close_issue(issue["number"])
    except ForgeError:
        pass  # the wait is in the answer too; the issue is opened by the next run that reaches GitHub
