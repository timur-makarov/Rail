"""The sweep: it reviews what shipped without a review, reads the areas the merged tickets changed, gathers what
those tickets left behind, and its output is tickets, never edits.

A sweep is itself an AUTO ticket that changes no product file, so it merges with no reviewer of its own. Its squash
commit carries a `Sweep:` trailer, which marks where the next one starts.
"""

import json
import re
from collections import defaultdict

from . import doclint, flakes, gitx, stats, triage
from .product import bar_key
from .project import events_path, parse_events, ticket_path
from .util import globmatch, match_any

SWEEP_UNREVIEWED = "This is a sweep: these changes merged without a review. Look for:"
# Not tested with a model run: the wording of the two openings below, which the reviewer reads.
SWEEP_AREAS = ("This is a sweep. Each ticket named above was reviewed alone, as one change, and nothing has read them"
               " together. Read the code of those areas as it is now, in this directory. Look for:")
SWEEP_BOTH = ("This is a sweep. The changes above merged without a review. Each ticket named under the areas was"
              " reviewed alone, as one change, and nothing has read them together. Read the changes, and the code of"
              " those areas as it is now, in this directory. Look for:")
SWEEP_LOOK_FOR = """\
- duplication across tickets;
- logic in the wrong area;
- weak checks;
- security (the checklist below);
- stale docs.
Each finding becomes a ticket, so report only what is worth one. The earlier parked findings and the checks
reviewers proposed are below: report a parked one again when it is real, and group the proposed checks by kind."""


NOTHING = "nothing to file"  # the detail of a harvest step that found nothing: the ticket merges with no task
PATTERN_TICKETS = 3  # the same dead end in the worker runs of this many merged tickets is a pattern
FLAKE_TICKETS = 2    # the same command flaky in this many merged tickets gets a ticket
FLAKE_RUNS = 20      # how often in a row that ticket's check runs the command
REPEAT_TICKETS = 2   # the same failure signature in this many merged tickets is a repeated failure
MARKER = re.compile(r"\b(TODO|FIXME)\((\d+)\)")  # work left for later, and the ticket that will do it
# What a worker run counts (rail docs journal, the `worked` event), as the summary says it.
DEAD_ENDS = {"failed": "`{key}` failed before it first passed", "not_found": "`{key}` wasn't on the machine",
             "denied": "a call was denied (`{key}`)", "reread": "`{key}` was read more than twice in a run"}


def landed(project):
    """(start, [(sha, ticket id or None, reviewed)]): what landed on base since the last Sweep: commit, oldest
    first. A ticket whose trailer says `Review: none` (every file it changed is in [review] skip_paths) and a commit
    with no ticket had no review."""
    base = project.base_ref
    # --first-parent: what landed on the base branch, one entry each. A merge commit counts once, as the change it
    # brought, and the commits inside it are not counted again.
    log = gitx.out(["log", "--first-parent", base, "--format=%H%x1f%B%x1e"], project.root)
    found, start = [], None
    for entry in log.split("\x1e"):
        if "\x1f" not in entry:
            continue
        sha, body = entry.strip().split("\x1f", 1)
        if re.search(r"^Sweep: ", body, re.M):
            start = sha
            break
        ticket = re.search(r"^Ticket: (\d+)", body, re.M)
        reviewed = bool(ticket) and bool(re.search(r"^Review: (?!none\b)\S", body, re.M))
        found.append((sha, ticket.group(1) if ticket else None, reviewed))
    if start is None:
        # The first sweep starts where Rail was set up: work from before then was never on the rail.
        setup = gitx.out(["log", "--first-parent", base, "--diff-filter=A", "--format=%H", "--", ".rail/config.toml"],
                         project.root).splitlines()
        start = setup[-1] if setup else ""
        shas = [sha for sha, _, _ in found]
        found = found[:shas.index(start)] if start in shas else found
    found.reverse()
    return start, found


def since_last(project):
    """(start, commits, merged): `commits` are what landed with no review, as (sha, ticket id or None). `merged` are
    the ids of every ticket that merged, reviewed or not."""
    start, found = landed(project)
    return (start, [(sha, nn) for sha, nn, reviewed in found if not reviewed],
            [nn for _, nn, _ in found if nn])


def changed_areas(project):
    """([(row, ticket ids)], [file]): each row of `## Areas` in the base branch's ARCHITECTURE.md that a ticket
    merged since the last sweep changed a file of, with those tickets; and the files those tickets changed that are
    in no row. What a ticket changed under .rail/ is its own record and counts for no area."""
    from .areas import parse_areas

    shas = {sha: nn for sha, nn, _ in landed(project)[1] if nn}
    if not shas:
        return [], []
    log = gitx.out(["log", "--no-walk", "--name-only", "--no-color", "--diff-merges=first-parent",
                    "--format=%x1e%H%x1f", *shas], project.root)
    files = defaultdict(list)  # file: the tickets that changed it
    for entry in log.split("\x1e"):
        if "\x1f" in entry:
            sha, names = entry.split("\x1f", 1)
            for name in names.split("\n"):
                if name.strip() and not name.startswith(".rail/") and shas[sha.strip()] not in files[name.strip()]:
                    files[name.strip()].append(shas[sha.strip()])
    rows = parse_areas(gitx.read_blobs([f"{project.base_ref}:ARCHITECTURE.md"], project.root)
                       [f"{project.base_ref}:ARCHITECTURE.md"])
    found, held = [], set()
    for row in rows:
        mine = [name for name in files if match_any(row["paths"], name)]
        held.update(mine)
        if mine:
            found.append((row, sorted({nn for name in mine for nn in files[name]}, key=int)))
    return found, sorted(set(files) - held)


def due(project):
    """Due once [sweep] after changes merged with no review, or [sweep] every tickets merged (0 switches that off)."""
    start, commits, merged = since_last(project)
    config = project.config["sweep"]
    return (len(commits) >= config["after"] or 0 < config["every"] <= len(merged)), start, commits, merged


def ticket_text(start, unreviewed, merged):
    return "\n".join([
        "+++", f'title = "Sweep the work merged since {start[:12]}"', 'tier = "AUTO"',
        'scope_paths = [".rail/journal/**"]', f'external_id = "sweep#{start[:12]}"', "+++", "",
        "## Why", f"Since the last sweep {merged} tickets merged, and {unreviewed} changes merged without a review"
                  " (tickets whose every changed file is in [review] skip_paths, and commits with no ticket). The"
                  " sweep reviews those changes, when there are any, reads the areas the merged tickets changed, and"
                  " gathers what every merged ticket left behind, so each item can become a ticket.", "",
        "## Done Contract", "- Check: `test -s .rail/journal/$RAIL_TICKET-summary.md`", ""])


def free_part(project):
    """What needs no model: doc-lint on base, and each structure rule counted over the whole tree."""
    problems = doclint.lint(project, project.base_ref)
    files = [f for f in gitx.git(["ls-tree", "-r", "-z", "--name-only", project.base_ref], project.root)
             .stdout.split("\0") if f]
    counts = {}
    for rule in project.config["rules"]:
        hits = 0
        paths = [f for f in files if globmatch(rule.get("files", "**"), f) and not match_any(rule.get("allow", []), f)
                 and (not rule.get("within") or match_any(rule["within"], f))]
        blobs = gitx.read_blobs([f"{project.base_ref}:{p}" for p in paths], project.root)
        for text in blobs.values():
            for line in (text or "").splitlines():
                if any(word in line for word in rule.get("forbid", [])):
                    hits += 1
        counts[rule["id"]] = hits
    return problems, counts


def kind_paths(project, merged):
    """[(kind, file, ticket id)]: each file a reviewer named a kind on, in a ticket merged since the last sweep, that
    the base still has and that no path of that kind in the config matches. A file under a folder whose coverage
    ticket is open is left out: that ticket adds the path (rail docs languages)."""
    from .project import review_path
    from .review import load_doc
    from .state import kind_paths as config_paths

    ids = sorted(set(merged), key=int)
    blobs = gitx.read_blobs([f"{project.base_ref}:{review_path(nn)}" for nn in ids], project.root)
    globs = {}
    for kind, paths, _ in config_paths(project.config):
        globs.setdefault(kind, []).extend(paths)
    held = project.layout(project.base_ref).tree.names
    covering = [(t.ticket.get("external_id") or "")[len("coverage:"):] for t in project.tickets().values()
                if t.ticket and (t.ticket.get("external_id") or "").startswith("coverage:") and not t.merged
                and not t.last("dropped") and not t.dropped_mark]
    found = []
    for nn in ids:
        for run in load_doc(blobs.get(f"{project.base_ref}:{review_path(nn)}"), nn)["runs"]:
            for k in run.get("kinds") or []:
                kind, path = k.get("kind"), k.get("file")
                if (path in held and not match_any(globs.get(kind) or [], path)
                        and not any(path.startswith(folder + "/") for folder in covering)
                        and (kind, path) not in [(a, b) for a, b, _ in found]):
                    found.append((kind, path, nn))
    return found


def history(project, merged):
    """(parked, checks, declined): the parked findings, the advisory findings left open, the proposed checks of
    fixed findings, and the findings an author declined, from the journals of every ticket merged since the last
    sweep, reviewed or not: a reviewed ticket is where a reviewer parks a finding. `declined` is
    {claim: (the first author's reason, ['NN/F1', ...])}, one entry for each claim, spacing and case aside, as the
    checks are grouped."""
    ids = sorted(set(merged), key=int)
    blobs = gitx.read_blobs([f"{project.base_ref}:{events_path(nn)}" for nn in ids], project.root)
    parked, checks, declined, said = [], defaultdict(list), defaultdict(list), {}
    for nn in ids:
        events = parse_events(blobs.get(f"{project.base_ref}:{events_path(nn)}"))
        first = {e["id"]: e for e in events if e.get("event") == "finding" and "severity" in e}
        last = {}
        for e in events:
            if e.get("event") == "finding":
                last[e["id"]] = e
        for fid, e in last.items():
            claim = first.get(fid, {}).get("claim", "")
            if e.get("outcome") == "parked":
                parked.append((nn, fid, claim))
            elif e.get("outcome") == "open" and first.get(fid, {}).get("severity") == "advisory":
                parked.append((nn, f"{fid} (advisory, left open)", claim))
            elif e.get("outcome") == "fixed" and first.get(fid, {}).get("check"):
                checks[" ".join(first[fid]["check"].lower().split())].append(f"{nn}/{fid}")
            elif e.get("outcome") == "declined" and e.get("by") == "author" and claim:
                key = " ".join(claim.lower().split())
                declined[key].append(f"{nn}/{fid}")
                said.setdefault(key, (claim, e.get("reason") or ""))
    seen, unique = set(), []
    for nn, fid, claim in parked:
        key = " ".join(claim.lower().split())
        if key not in seen:
            seen.add(key)
            unique.append((nn, fid, claim))
    return unique, dict(checks), {said[key][0]: (said[key][1], where) for key, where in declined.items()}


def left_behind(project, merged):
    """(noticed, words, repeated): what the tickets merged since the last sweep wrote down and nothing else reads.
    `noticed`: [(ticket id, 'Noticed' or 'not tested', text)], the lines a worker wrote in the ticket for a problem
    outside it and for what it did not test. `words`: [(ticket id, note)], every note a person gave with
    `rail accept`. `repeated`: [(step, detail, ticket ids)], each failure signature that REPEAT_TICKETS tickets or
    more share, the most tickets first. A failed review run is left out: every one has the same signature."""
    from .steps import REVIEW_STEPS
    from .ticket import Ticket

    ids = sorted(set(merged), key=int)
    specs = [f"{project.base_ref}:{path(nn)}" for nn in ids for path in (events_path, ticket_path)]
    blobs = gitx.read_blobs(specs, project.root)
    noticed, words, seen, shown = [], [], defaultdict(list), {}
    for nn in ids:
        t = Ticket(blobs.get(f"{project.base_ref}:{ticket_path(nn)}") or "")
        if not t.errors:
            noticed += [(nn, "Noticed", row) for row in t.noticed()] + [(nn, "not tested", row) for row in t.not_tested()]
        for e in parse_events(blobs.get(f"{project.base_ref}:{events_path(nn)}")):
            person = e.get("event") == "accepted" and e.get("by") == "person" or \
                e.get("event") == "continued" and e.get("via") == "accept"
            if person and (e.get("note") or "").strip():
                words.append((nn, " ".join(e["note"].split())))
            if (e.get("event") == "step" and e.get("result") == "fail" and e.get("status") == "ran"
                    and e.get("signature") and e.get("step") not in REVIEW_STEPS):
                if nn not in seen[e["signature"]]:
                    seen[e["signature"]].append(nn)
                shown.setdefault(e["signature"], (e["step"], " ".join((e.get("detail") or "").split())[:200]))
    repeated = [(*shown[sig], where) for sig, where in sorted(seen.items(), key=lambda x: (-len(x[1]), x[0]))
                if len(where) >= REPEAT_TICKETS]
    return noticed, words, repeated


def stale_markers(project):
    """[(ticket id, how it ended, ['path:line: text', ...])]: the TODO(NN) and FIXME(NN) comments standing on the
    base branch whose ticket NN merged or was dropped, so no ticket will do the work they name. A ticket whose
    removal ticket (external_id `todo#NN`) is open is left out."""
    from .project import PRODUCT_SPEC

    out = gitx.git(["grep", "-n", "-I", "--no-color", "-E", r"(TODO|FIXME)\([0-9]+\)", project.base_ref,
                    *PRODUCT_SPEC], project.root, check=False).stdout
    found = defaultdict(list)
    for line in out.splitlines():
        parts = line.split(":", 3)  # ref:path:line:text; refs/remotes/origin/main holds no colon
        if len(parts) == 4:
            for nn in dict.fromkeys(m.group(2) for m in MARKER.finditer(parts[3])):
                found[str(int(nn))].append(f"{parts[1]}:{parts[2]}: {parts[3].strip()[:160]}")
    if not found:
        return []
    tickets = project.tickets()
    filed = {(t.ticket.get("external_id") or "")[len("todo#"):] for t in tickets.values()
             if t.ticket and (t.ticket.get("external_id") or "").startswith("todo#") and not t.merged
             and not t.last("dropped") and not t.dropped_mark}
    stale = []
    for nn in sorted(found, key=int):
        t = tickets.get(nn)
        ended = t and ("merged" if t.merged else "was dropped" if t.last("dropped") or t.dropped_mark else None)
        if ended and nn not in filed:
            stale.append((nn, ended, found[nn]))
    return stale


def patterns(project, merged):
    """The dead ends that recur in the worker runs of the tickets merged since the last sweep: a command that failed
    before it first passed, one the machine doesn't have, a denied call or a file read again and again, in
    PATTERN_TICKETS tickets or more. Each is something the project could have told the worker. Returns
    [(kind, key, ticket ids)], the most tickets first. Read from the `worked` events, which keep a short key per
    item, so the run logs (never committed) aren't needed."""
    ids = sorted(set(merged), key=int)
    blobs = gitx.read_blobs([f"{project.base_ref}:{events_path(nn)}" for nn in ids], project.root)
    seen = defaultdict(list)
    for nn in ids:
        keys = set()
        for e in parse_events(blobs.get(f"{project.base_ref}:{events_path(nn)}")):
            if e.get("event") == "worked" and isinstance(e.get("keys"), dict):
                keys.update((kind, key) for kind, found in e["keys"].items() if kind in DEAD_ENDS for key in found)
        for item in keys:
            seen[item].append(nn)
    found = [(kind, key, where) for (kind, key), where in seen.items() if len(where) >= PATTERN_TICKETS]
    return sorted(found, key=lambda x: (-len(x[2]), x[0], x[1]))


def flaky(project, merged):
    """The commands that were flaky (rail docs retries) in FLAKE_TICKETS or more of the tickets merged since the last
    sweep, as [(command, ticket ids)]. The command is matched as the failure signatures are: lower-cased, with
    numbers, hashes and paths left out, so a temp path in it doesn't make it two commands."""
    from .steps import normalise

    ids = sorted(set(merged), key=int)
    blobs = gitx.read_blobs([f"{project.base_ref}:{events_path(nn)}" for nn in ids], project.root)
    seen, shown = defaultdict(list), {}
    for nn in ids:
        for key in dict.fromkeys(flakes.name(x) for x in flakes.of(parse_events(blobs.get(f"{project.base_ref}:{events_path(nn)}")))):
            seen[normalise(key)].append(nn)
            shown.setdefault(normalise(key), key)
    commands = {"verify": project.config["commands"]["verify"],
                **{f"verify:{p['name']}": p["verify"] for p in project.layout(project.base_ref).projects}}
    return [(commands.get(shown[key]) or shown[key], where)
            for key, where in sorted(seen.items(), key=lambda x: (-len(x[1]), x[0])) if len(where) >= FLAKE_TICKETS]


LACKS = "What the machine lacks to drive the product"  # the summary section the next sweep reads back


def lacking(project, start):
    """([(name, detail)], [name]): the pieces the machine can build that the project lacks before the product can be
    started and driven with no person (rail docs product), read on the base branch. First the new ones, then the
    names an earlier sweep listed already: a piece is listed for a ticket once. A piece is new when the summary of
    the sweep before this one does not name it and no open ticket carries its `bar#` id. Nothing is listed for a
    project whose config names no surface."""
    from . import product

    if not project.config["surfaces"]:
        return [], []  # a project that names no surface is asked nothing: not every repository holds a product
    lines = product.bar(project, set(project.layout(project.base_ref).tree.names))
    failing = [(name, detail) for name, passed, detail, kind in lines if passed is False and kind == "ticket"]
    if not failing:
        return [], []
    before = set()
    last = re.search(r"^Ticket: (\d+)", gitx.out(["log", "-1", "--format=%B", start], project.root), re.M) if start else None
    if last:
        path = f"{project.base_ref}:.rail/journal/{last.group(1)}-summary.md"
        text = gitx.read_blobs([path], project.root).get(path) or ""
        if f"## {LACKS}\n" in text:
            section = text.split(f"## {LACKS}\n", 1)[1].split("\n## ", 1)[0]
            before = set(re.findall(r"^- `([^`]+)`", section, re.M))
    filed = {(t.ticket.get("external_id") or "") for t in project.tickets().values()
             if t.ticket and not t.merged and not t.last("dropped") and not t.dropped_mark}
    old = [name for name, _ in failing if name in before or product.bar_key(name) in filed]
    return [(name, detail) for name, detail in failing if name not in old], old


def brief(project, commits, parked, checks, merged=(), areas=(), loose=()):
    from .review import DO_NOT_REPORT, SECURITY, project_conventions

    diffs = []
    for sha, nn in commits:
        diffs.append(gitx.out(["show", "--no-color", "--diff-merges=first-parent", "--format=commit %h %s", sha, "--",
                               ".", ":(exclude).rail/tickets", ":(exclude).rail/journal"], project.root))
    ids = sorted(set(merged), key=int)
    job = ("sweep the changes below, which merged without a review." if commits and not areas else
           "sweep the areas below, which the tickets merged since the last sweep changed." if not commits else
           "sweep the changes below, which merged without a review, and the areas the tickets merged since the last"
           " sweep changed.")
    parts = [
        "# Sweep brief", "", f"This run's job: {job}", "",
        *(["## The changes", "```diff", "\n\n".join(diffs), "```", ""] if commits else []),
        # Not tested with a model run: the wording of this section.
        *(["## Areas the merged tickets changed",
           f"Tickets merged since the last sweep: {', '.join(ids)}. A ticket's contract is in .rail/tickets/, under"
           " its number.", "",
           "| Area | Paths | Holds | Changed by tickets |", "|---|---|---|---|",
           *[f"| {row['area']} | {', '.join(row['paths'])} | {row['holds']} | {', '.join(where)} |"
             for row, where in areas],
           *(["", "Changed files in no area: " + ", ".join(loose)] if loose else []), ""] if areas else []),
        "## The project's conventions (from AGENTS.md)", project_conventions(project, project.base_ref) or "(none)", "",
        "## What to look for",
        (SWEEP_UNREVIEWED if not areas else SWEEP_BOTH if commits else SWEEP_AREAS) + "\n" + SWEEP_LOOK_FOR, "",
        SECURITY, "", DO_NOT_REPORT, "",
        "## Parked and open advisory findings from the tickets merged since the last sweep",
        *([f"- ticket {nn} {fid}: {claim}" for nn, fid, claim in parked] or ["(none)"]), "",
        "## Checks reviewers proposed for findings that were fixed",
        *([f"- {check} ({', '.join(where)})" for check, where in checks.items()] or ["(none)"]),
    ]
    return "\n".join(parts) + "\n"


def summary(nn, start, commits, merged, problems, counts, entry, parked, checks, recurring=(), flaked=(),
            settled=(), refused=(), kinds=(), areas=(), declined=None, noticed=(), words=(), repeated=(), stale=(),
            lacks=((), ())):
    review = (entry["summary"] if entry else "(the review run failed)") if commits or areas else \
        "(no review run: nothing merged without a review, and the areas the merged tickets changed are read once" \
        " [sweep] every tickets merged)"
    if areas and entry:
        review = "Read: " + "; ".join(f"{row['area']} (tickets {', '.join(where)})" for row, where in areas) + \
            ".\n" + review
    lines = [f"# Sweep {nn}", "", f"Since {start[:12]}: {len(merged)} tickets merged; {len(commits)} commits merged"
                                  " without a review.", "",
             "## Free part", *([f"- doc-lint: {p}" for p in problems] or ["- doc-lint: clean"]),
             *[f"- rule {rid}: {n} lines in the tree" for rid, n in counts.items()], "",
             "## Review", review, ""]
    for f in (entry or {}).get("findings", []):
        where = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
        lines.append(f"- {f['id']} ({f['severity']}) {where}: {f['claim']}" + (f" Check: {f['check']}" if f.get("check") else ""))
    lines += ["", "## Parked and open advisory findings", *([f"- ticket {n} {fid}: {c}" for n, fid, c in parked] or ["(none)"]),
              "", "## Proposed checks, by kind", *([f"- {c} ({', '.join(w)})" for c, w in checks.items()] or ["(none)"]),
              # Not tested with a model run: the wording of the five sections below, which the agent that files
              # the sweep's tickets reads.
              "", "## Findings an author declined, by kind",
              *(["A kind is one claim, however many tickets it was made in. Open one ticket for a kind when the"
                 " problem is real. When the reason holds and the kind was declined in more than one ticket, open one"
                 " ticket that adds a line to REVIEW.md, so reviewers stop reporting it. The rest get no ticket.",
                 *[f"- {claim} ({', '.join(where)}). The author's reason: {reason or '(none given)'}"
                   for claim, (reason, where) in (declined or {}).items()]] if declined else ["(none)"]),
              "", "## Problems workers saw outside their tickets, and what they did not test",
              *(["Each line is a candidate. Open a ticket for one that names something wrong, or a behaviour worth a"
                 " test. The rest get no ticket.",
                 *[f"- ticket {n}, {kind}: {text}" for n, kind, text in noticed]] if noticed else ["(none)"]),
              "", "## What a person said with rail accept",
              *(["A note that holds for later tickets too is a standing rule: open one ticket that makes it a line in"
                 " the project's part of AGENTS.md, a check or a structure rule. A note about its own ticket gets no"
                 " ticket.",
                 *[f"- ticket {n}: {note}" for n, note in words]] if words else ["(none)"]),
              "", "## Failures that recur across tickets",
              *(["Open one ticket for each: a check that catches the cause before a ship, or a line in the project's"
                 " part of AGENTS.md that tells a worker how to avoid it.",
                 *[f"- step `{step}` failed the same way in {len(where)} tickets ({', '.join(where)})"
                   + (f": {detail}" if detail else "") for step, detail, where in repeated]] if repeated else ["(none)"]),
              "", "## Work left for later whose ticket ended",
              *([line for n, ended, where in stale for line in (
                  f"- ticket {n} {ended}, and {len(where)} comment{'s' if len(where) != 1 else ''} still name{'' if len(where) != 1 else 's'} it."
                  f" Open one ticket with `external_id = \"todo#{n}\"` that does what is left or removes"
                  f" {'them' if len(where) != 1 else 'it'}."
                  f" Check: `! git grep -n -E '(TODO|FIXME)\\({n}\\)' -- . ':(exclude).rail'`",
                  *[f"    - {w}" for w in where])] or ["(none)"]),
              "", "## Patterns in the worker runs",
              *([f"- {DEAD_ENDS[kind].format(key=key)}, in {len(where)} tickets ({', '.join(where)})"
                 for kind, key, where in recurring] or ["(none)"]),
              "", "## Flaky checks",
              *([f"- `{command}` both failed and passed on the same code, in {len(where)} tickets"
                 f" ({', '.join(where)}). Check: `for i in $(seq {FLAKE_RUNS}); do {command} || exit 1; done`"
                 for command, where in flaked] or ["(none)"]),
              # Not tested with a model run: the wording of the line below, which the agent that files the sweep's
              # tickets reads.
              "", "## Question types with one answer",
              *([f"- `{name}` was answered `{answer}` in {times} of its last {triage.LAST} questions. An answer that"
                 f" does not vary is a rule the engine can apply with no run: open one ticket that makes it a rule or"
                 f" removes the type."
                 for name, answer, times in settled] or ["(none)"]),
              # Not tested with a model run: the wording of the line below, as above.
              "", "## Kinds a person refuses at the merge",
              *([f"- `{kind}`: a person closed {times} of the last {stats.REFUSED_LAST} PERSON tickets without a merge,"
                 f" and they were of this kind. Each was built before the person saw it. Open one ticket that puts"
                 f" `{kind}` into `approve_contract` in `.rail/config.toml`, so that a person approves such a contract"
                 f" before the build."
                 for kind, times in refused] or ["(none)"]),
              # Not tested with a model run: the wording of the line below, as above.
              "", "## Kind paths reviewers found",
              *([f"- `{kind}`: a reviewer named this kind on `{path}` (ticket {where}), and no path of that kind in"
                 f" `.rail/config.toml` matches the file, so a later change to it is `{kind}` only if a reviewer says"
                 f" so again. Open one ticket that adds its path under `[kinds]` `{kind}`."
                 for kind, path, where in kinds] or ["(none)"]),
              # Not tested with a model run: the wording of the lines below, as above.
              "", f"## {LACKS}",
              *([f"- `{name}`: {detail}. Open that ticket, with `external_id = \"{bar_key(name)}\"`."
                 for name, detail in lacks[0]]
                + [f"- `{name}`: listed by an earlier sweep, and still lacking. No ticket." for name in lacks[1]]
                or ["(none)"])]
    return "\n".join(lines) + "\n"


def run(project, f, receipt):
    """The free part, what the merged tickets left behind, and one review pass with the sweep brief: over what merged
    without a review, and, once [sweep] every tickets merged, over the areas those tickets changed. With neither
    there is no model run. A passed `harvest` step says what was gathered when no pass ran, and after a pass that
    found nothing its detail says so. Writes NN-summary.md into `receipt`."""
    from . import review

    start, commits, merged = since_last(project)
    problems, counts = free_part(project)
    kinds = kind_paths(project, merged)
    parked, checks, declined = history(project, merged)
    noticed, words, repeated = left_behind(project, merged)
    stale = stale_markers(project)
    lacks = lacking(project, start)
    recurring, flaked = patterns(project, merged), flaky(project, merged)
    settled = triage.settled(project)
    refused = stats.refused_kinds(project, project.tickets())
    areas, loose = changed_areas(project) if 0 < project.config["sweep"]["every"] <= len(merged) else ([], [])
    gathered = (problems or parked or checks or recurring or flaked or settled or refused or kinds or declined
                or noticed or words or repeated or stale or lacks[0])
    entry = None
    if commits or areas:
        entry = review.run(project, f, "sweep", receipt,
                           prompt=brief(project, commits, parked, checks, merged, areas, loose))
        if entry and not entry["findings"] and not gathered:
            receipt.record("harvest", True, f.patch_id, NOTHING)
    else:
        more = ((len(settled), "question types with one answer"), (len(refused), "kinds a person refuses at the merge"),
                (len(kinds), "kind paths reviewers found"), (len(declined), "kinds of declined findings"),
                (len(noticed), "lines workers left"), (len(words), "notes a person gave"),
                (len(repeated), "repeated failures"), (len(stale), "tickets with comments left behind"),
                (len(lacks[0]), "pieces the machine lacks to drive the product"))
        receipt.record("harvest", True, f.patch_id, NOTHING if not gathered
                       else f"no review run: {len(parked)} parked findings, {len(checks)} proposed checks,"
                            f" {len(recurring)} patterns in the worker runs, {len(flaked)} flaky checks"
                            + "".join(f", {n} {what}" for n, what in more if n))
    receipt.files[f".rail/journal/{f.id}-summary.md"] = summary(
        f.id, start, commits, merged, problems, counts, entry, parked, checks, recurring, flaked, settled, refused,
        kinds, areas, declined, noticed, words, repeated, stale, lacks)
    return entry
