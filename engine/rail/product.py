"""The product step: start the product, drive each surface the change reaches, stop it, and keep what the checks saw.

`[product]` says how the product is started, and each `[[surfaces]]` entry is one way users reach it, with the script
that drives it (rail docs product). The step is the last of the checks ship and CI share.
"""

import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time

from . import config as configmod
from . import gitx
from .util import could_not_run, run_shell, shell, tail

KINDS = ("web", "api", "cli", "agent", "data", "integration", "mobile")
NEEDS_IDENTITY = ("web", "api", "agent", "mobile")  # kinds a user signs in to: they need a seeded test identity
NEEDS_NO_START = ("cli", "data")                    # kinds whose check may run the built program itself
FILE_BYTES, SURFACE_BYTES = 64 * 1024, 256 * 1024   # text evidence kept: for each file, and for a surface in all
BRIEF_BYTES = 16 * 1024                             # of a surface's evidence, what a reviewer's brief carries
POLL_SECS = 0.5                                     # between two runs of `ready`
CUT = "\n[cut here: the file is longer]\n"


def evidence_path(nn):
    return f".rail/journal/{nn}-evidence.json"


def check_path(surface):
    """The path of a surface's driving check, as the config writes it."""
    return os.path.normpath(surface["check"]) if surface.get("check", "").strip() else ""


def touched(project, ref, changed):
    """The surfaces a change of these files reaches: those with a project among the projects the change reaches
    (rail docs languages), and those that name no project, which every change reaches."""
    surfaces = project.config["surfaces"]
    if not surfaces or not changed:
        return []
    from .steps import reached
    names = {p["name"] for p in reached(project, ref, changed)}
    return [s for s in surfaces if "projects" not in s or names & set(s["projects"])]


def _env(project, nn):
    return {"RAIL_TICKET": nn, "RAIL_BASE": project.base_ref}


class Started:
    """The product as one run of the step started it. `start` runs with its output in a file, not a pipe, so a
    product it leaves running in the background does not hold the step: the step waits for `start` itself only."""

    def __init__(self, project, cwd, nn, log):
        self.project, self.cwd, self.env, self.log = project, cwd, _env(project, nn), log
        self.config = project.config["product"]
        self.group = None

    def _said(self):
        try:
            with open(self.log, errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def start(self):
        """Run start, ready until it exits 0, and seed. Returns (passed, could not run, detail, output, ms)."""
        began = time.monotonic()

        def ended(passed, missing, detail, output):
            return passed, missing, detail, output, int((time.monotonic() - began) * 1000)

        limit = self.project.config["commands"]["timeout_secs"]
        if self.config["start"]:
            with open(self.log, "w") as out:
                proc = subprocess.Popen(shell(self.config["start"]), cwd=self.cwd, env={**os.environ, **self.env},
                                        stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            self.group = proc.pid
            try:
                code = proc.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                code = None
            if code != 0:
                missing = could_not_run(code)
                said = missing or ("timeout: start has to return once the product is starting" if code is None
                                   else f"exit {code}")
                return ended(False, bool(missing), f"start: {said}", f"$ {self.config['start']}\n{tail(self._said())}")
        if self.config["ready"]:
            until = time.monotonic() + self.config["ready_secs"]
            while True:
                code, output, _ = run_shell(self.config["ready"], self.cwd, self.env,
                                            max(1, min(limit, until - time.monotonic())))
                if code == 0:
                    break
                if could_not_run(code) or time.monotonic() >= until:
                    missing = could_not_run(code)
                    said = missing or f"not ready after {self.config['ready_secs']}s"
                    return ended(False, bool(missing), f"ready: {said}",
                                 f"$ {self.config['ready']}\n{tail(output)}\n\nWhat start printed:\n{tail(self._said(), 30)}")
                time.sleep(POLL_SECS)
        if self.config["seed"]:
            code, output, _ = run_shell(self.config["seed"], self.cwd, self.env, limit)
            if code != 0:
                missing = could_not_run(code)
                said = missing or ("timeout" if code is None else f"exit {code}")
                return ended(False, bool(missing), f"seed: {said}", f"$ {self.config['seed']}\n{tail(output)}")
        return ended(True, False, None, "")

    def stop(self):
        """Run stop, then end whatever `start` left running. Returns stop's failure as text, or None."""
        failed = None
        if self.config["stop"]:
            code, output, _ = run_shell(self.config["stop"], self.cwd, self.env,
                                        self.project.config["commands"]["timeout_secs"])
            if code != 0:
                failed = f"$ {self.config['stop']}\n{tail(output)}"
        if self.group:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.group, sig)
                except (ProcessLookupError, PermissionError):
                    break
                time.sleep(0.2)
        return failed


def drive(project, cwd, nn, surface, folder):
    """Run one surface's driving check with RAIL_EVIDENCE set to `folder`, which is emptied first. Returns
    (exit code or None on timeout, output, ms)."""
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    path = check_path(surface)
    if not path:
        return 127, f"surface {surface['name']} has no check in .rail/config.toml", 0
    return run_shell("./" + shlex.quote(path), cwd, {**_env(project, nn), "RAIL_EVIDENCE": folder, "RAIL_SURFACE": surface["name"]},
                     project.config["commands"]["timeout_secs"])


def secrets(project, cwd):
    """{value: name} for what evidence must not hold: the value of each environment name a `[tools.NAME]` declares,
    and of each entry of a `.env` file in the checkout. The longest value first, so one inside another goes whole."""
    found = {}
    for tool in project.config["tools"].values():
        for name in tool.get("env", []):
            if os.environ.get(name):
                found[os.environ[name]] = name
    try:
        with open(os.path.join(cwd, ".env"), errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name, eq, value = line.partition("=")
        value = value.strip().strip("'\"")
        if eq and name.strip() and not name.startswith("#") and len(value) >= 4:
            found.setdefault(value, name.strip())
    return dict(sorted(found.items(), key=lambda x: -len(x[0])))


def collect(folder, hidden):
    """What one driving check left in its evidence folder: {'files': {name: text}, 'cut': [names], 'left': [names]}.
    A text file is kept up to FILE_BYTES, and a surface up to SURFACE_BYTES in all, with each value in `hidden`
    replaced by its name first. Anything else (a screenshot, a trace, a recording) is named in `left` and stays on
    the machine: it is never committed."""
    files, cut, left, room = {}, [], [], SURFACE_BYTES
    names = sorted(os.path.relpath(os.path.join(base, name), folder)
                   for base, _, found in os.walk(folder) for name in found)
    for name in names:
        try:
            with open(os.path.join(folder, name), "rb") as f:
                raw = f.read(FILE_BYTES * 4 + 1)
        except OSError:
            continue
        if b"\0" in raw:
            left.append(name)
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore") if len(raw) > FILE_BYTES else None
        if text is None:
            left.append(name)
            continue
        for value, label in hidden.items():
            text = text.replace(value, f"[{label}]")
        limit = min(FILE_BYTES, room)
        if len(text.encode()) > limit:
            text = text.encode()[:limit].decode("utf-8", errors="ignore") + CUT
            cut.append(name)
        room = max(0, room - len(text.encode()))
        files[name] = text
    return {"files": files, **({"cut": cut} if cut else {}), **({"left": left} if left else {})}


def said(found):
    """One line for a surface's evidence, for the step's detail and the pull request's Evidence table."""
    n, left = len(found["files"]), len(found.get("left") or [])
    if not n and not left:
        return "no evidence written"
    return f"{n} evidence file{'s' if n != 1 else ''}" + (f", {left} more left on the machine" if left else "")


def evidence_root(project, nn):
    """Where the evidence folders of a run are: $RAIL_EVIDENCE when the caller set one (the rail workflow does, and
    uploads it), or else the local cache, by ticket. A folder of a surface stays until that surface is driven again,
    so what was not committed can still be looked at."""
    asked = os.environ.get("RAIL_EVIDENCE")
    return asked if asked else os.path.join(project.common, "rail", "cache", "evidence", nn or "none")


def step(project, nn, ref, cwd, run, patch_id, changed):
    """The `product` step: with a surface the change reaches, start the product (step `product`), run each such
    surface's driving check (step `product:NAME`), and stop it, whatever happened. Returns whether it passed. The
    text the checks left as evidence goes into `run.files`, to be committed with the step's events."""
    mine = touched(project, ref, changed)
    if not mine:
        run.not_run("product")  # no receipt at all in a project with no surface
        return True
    root = evidence_root(project, nn)
    os.makedirs(root, exist_ok=True)
    began = Started(project, cwd, nn, os.path.join(root, "start.log"))
    hidden = secrets(project, cwd)
    kept, passed = {}, True
    try:
        ok, missing, detail, output, ms = began.start()
        if not run.record("product", ok, patch_id, detail, ms, output=output,
                          status="could_not_run" if missing else "ran"):
            run.not_run(*[f"product:{s['name']}" for s in mine])
            return False
        for n, surface in enumerate(mine):
            name = f"product:{surface['name']}"
            folder = os.path.join(root, surface["name"])
            code, output, ms = drive(project, cwd, nn, surface, folder)
            shown = f"$ {check_path(surface)}\n{tail(output)}"
            missing = could_not_run(code)
            found = kept[surface["name"]] = collect(folder, hidden)
            status = missing or ("timeout" if code is None else f"exit {code}")
            if not run.record(name, code == 0, patch_id, said(found) if code == 0 else f"{status}; {said(found)}", ms,
                              output=shown, status="could_not_run" if missing else "ran"):
                run.not_run(*[f"product:{s['name']}" for s in mine[n + 1:]])
                passed = False
                break
    finally:
        failed = began.stop()
    if passed and failed:
        passed = run.record("product", False, patch_id, "stop failed", output=failed)
    if kept:
        run.files[evidence_path(nn)] = json.dumps({patch_id or "": kept}, indent=1, sort_keys=True) + "\n"
    return passed


def base_fails(project):
    """Start the product once on the base branch, in a scratch worktree, and stop it. Returns what it printed when
    it does not start there either. A start that the shell could not run proves nothing about the base."""
    from .steps import scratch
    with scratch(project, gitx.rev(project.base_ref, project.root)) as path:
        setup = project.config["commands"]["setup"]
        if setup:
            run_shell(setup, path, _env(project, ""), configmod.timeout(project.config, "setup"))
        with tempfile.TemporaryDirectory(prefix="rail-product-") as held:
            began = Started(project, path, "", os.path.join(held, "start.log"))
            try:
                ok, missing, detail, output, _ = began.start()
            finally:
                began.stop()
    if ok or missing or (detail or "").startswith("seed"):
        return None
    return f"{detail}\n{output}".strip()


def evidence_of(project, ref, nn, patch_id):
    """{surface: {'files': ..., 'cut': ..., 'left': ...}} that the ticket's journal holds for this patch, or {}."""
    text = gitx.read_blobs([f"{ref}:{evidence_path(nn)}"], project.root).get(f"{ref}:{evidence_path(nn)}")
    try:
        doc = json.loads(text) if text else {}
    except ValueError:
        return {}
    found = doc.get(patch_id or "") if isinstance(doc, dict) else None
    return found if isinstance(found, dict) else {}


def brief_lines(found):
    """The evidence of a patch as lines of a reviewer's brief: each surface's files, up to BRIEF_BYTES a surface."""
    lines = []
    for surface in sorted(found):
        room = BRIEF_BYTES
        for name, text in sorted((found[surface].get("files") or {}).items()):
            if room <= 0:
                lines.append(f"- `{surface}` / `{name}`: left out here for length")
                continue
            shown = text if len(text) <= room else text[:room] + CUT
            room -= len(shown)
            lines += [f"`{surface}` / `{name}`:", "```", shown.rstrip("\n"), "```"]
        for name in found[surface].get("left") or []:
            lines.append(f"- `{surface}` / `{name}`: not text, so it was not kept in the journal")
    return lines
