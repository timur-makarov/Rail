"""Admission with no model (PLAN 4a, step 3): a situation is admitted when
- null: on the start commit the hidden tests fail;
- oracle: with the fix applied the hidden tests pass `oracle_runs` times in a row, and the packages the fix touches
  pass, tests red on the start commit left out;
- Rail's setup and verify for the project pass on the start commit, or Rail would rest at a red base while a plain arm
  works on;
- the request holds no link to the fix: not its commit, not its pull request.
The written rules a person applies (the issue understood alone, the tests use what existed, the fix not trivial) are
not checked here."""

import os
import re
import tempfile

from . import grade, rail_install, sealed, tomlw
from .common import BenchError, now_iso, run, write


def request_leaks(situation, fix_sha):
    """What in the request points at the fix."""
    found = []
    text = situation.request
    for n in range(7, 41):
        if fix_sha[:n] in text:
            found.append(f"the fix's commit {fix_sha[:n]}")
            break
    if situation.pull and re.search(rf"(?:pull|pulls)/{situation.pull}\b", text):
        found.append(f"the fix's pull request {situation.pull}")
    if situation.project.slug and re.search(rf"{re.escape(situation.project.slug)}/(?:pull|commit)/", text):
        found.append("a link to a pull request or commit")
    return found


def admit(store_root, situation, conf, log=print):
    """Admit one situation. Returns (admitted, reasons, record); the record is kept as admission.toml in the sealed
    folder."""
    project = situation.project
    reasons = []
    record = {"situation": situation.id, "checked": now_iso()}
    try:
        sealed.build(store_root, situation, log=log)
    except BenchError as e:
        record.update(admitted=False, reasons=[f"build: {e}"])
        return False, record["reasons"], record
    meta = sealed.meta(store_root, situation)
    env = sealed.project_env(project, store_root)
    timeout = project.timeout
    reasons += [f"request: holds {x}" for x in request_leaks(situation, meta["fix"])]

    # null: the hidden tests on the start commit, as it is
    with tempfile.TemporaryDirectory(dir=grade.scratch(store_root)) as tmp:
        root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
        sealed.put_hidden(store_root, situation, root)
        code, out = run(project.test_files_command(situation.hidden_tests), root, env, timeout)
        record["null"] = {"exit": code, "failing": project.failing(out)}
        if code == 0:
            reasons.append("null: the hidden tests pass on the start commit, so they can't tell done from not done")

    # oracle: the fix applied, the hidden tests oracle_runs times, the touched packages once
    with open(sealed.fix_diff(store_root, situation), "rb") as f:
        fix = f.read()
    graded = grade.grade(store_root, situation, fix, rounds=1, hidden_runs=conf["oracle_runs"])
    passes = sum(1 for h in graded["rounds"][0]["hidden"] if h["exit"] == 0) if graded["rounds"] else 0
    record["oracle"] = {"applied": graded["applied"], "hidden_passed": passes, "hidden_runs": conf["oracle_runs"],
                        "packages": {p: r["passed"] for p, r in (graded["rounds"][0]["packages"].items()
                                                                  if graded["rounds"] else [])}}
    if not graded["applied"]:
        reasons.append(f"oracle: {graded['why']}")
    else:
        if passes < conf["oracle_runs"]:
            reasons.append(f"oracle: the hidden tests passed {passes} of {conf['oracle_runs']} times with the fix"
                           + (" (flaky)" if passes else ""))
        for p, r in graded["rounds"][0]["packages"].items():
            if not r["passed"]:
                reasons.append(f"oracle: package {p} {r['why']} with the fix")

    # Rail's setup and verify on the start commit
    commands = project.rail_config.get("commands", {})
    with tempfile.TemporaryDirectory(dir=grade.scratch(store_root)) as tmp:
        root = sealed.fresh(store_root, situation, os.path.join(tmp, "copy"))
        try:
            rail_install.install(root, project, env=env)
            rail = {}
            for step in ("setup", "verify"):
                command = commands.get(step, "")
                if not command:
                    rail[step] = "empty"
                    continue
                code, out = run(command, root, dict(env, RAIL_BASE="refs/heads/main"), timeout)
                rail[step] = "pass" if code == 0 else ("timeout" if code is None else f"exit {code}")
                if code != 0:
                    reasons.append(f"rail: {step} fails on the start commit ({rail[step]}): {out.strip()[-300:]}")
            if not commands.get("verify"):
                reasons.append("rail: [rail.config.commands] verify is empty")
            record["rail"] = rail
        except BenchError as e:
            reasons.append(f"rail: {e}")
    record.update(admitted=not reasons, reasons=reasons)
    write(os.path.join(sealed.folder(store_root, situation), "admission.toml"), tomlw.dumps(record))
    return not reasons, reasons, record
