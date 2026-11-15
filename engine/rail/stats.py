"""`rail stats`: what the journals of merged tickets say about the work and about the reviewer.

Everything is read from the events and the review runs, which merge with the code. Nothing is stored, so the
numbers can be checked against the journal they come from.
"""

import datetime
import statistics
from collections import Counter

from . import gitx
from .review import Ledger, load_doc
from .state import SHIP_STEPS
from .ticket import TIERS
from .util import RailError, parse_iso

REVIEW_STEPS = ("review", "security", "refuter", "sweep")
STEP_ORDER = ("setup", "rebase", "ticket-lint", "assumptions", "scope", "rules", "migration", "size", "doc-lint",
              "verify", "checks", *REVIEW_STEPS, "merge")
NO_MODEL = "(not reported)"
NO_RUNS = {"runs": 0, "cost_usd": 0.0, "blocking": 0, "fixed": 0}


def _since(text):
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        raise RailError(f"--since takes a date like 2026-01-31, not '{text}'")


def _merge_times(project, tickets):
    """{ticket id: when its squash commit landed on the base branch, in seconds since the epoch}."""
    shas = {t.merged: nn for nn, t in tickets.items() if t.merged}
    if not shas:
        return {}
    lines = gitx.out(["show", "--no-patch", "--format=%H %ct", *shas], project.root).splitlines()
    return {shas[sha]: int(at) for sha, at in (line.split() for line in lines if line.strip()) if sha in shas}


def _ended(severity, last):
    """How a finding ended. Only a refuter or a person can decline a blocking one: the author's decline disputes it."""
    if severity == "blocking" and last.get("outcome") == "declined":
        return "dismissed" if last.get("by") == "refuter" else "declined_by_person"
    return last.get("outcome")


def collect(project, tickets, since=None):
    """The numbers, for tickets merged on or after `since` (YYYY-MM-DD), or for every merged ticket."""
    start = _since(since) if since else None
    merged_at = _merge_times(project, tickets)
    tiers = {tier: {"merged": 0, "reviewed": 0, "no_person": 0, "first_try": 0, "minutes": []} for tier in TIERS}
    raised, consults, steps, roles, models = Counter(), 0, {}, {}, {}
    blocking, advisory, parked, disputes = Counter(), Counter(), 0, Counter()
    for nn, t in tickets.items():
        ships = [e for e in t.events if e.get("event") == "shipped"]
        tier = (ships[-1] if ships else t.last("accepted") or {}).get("tier")
        if nn not in merged_at or tier not in tiers or (start is not None and merged_at[nn] < start):
            continue
        doc = load_doc(t.review_text, nn)
        ledger = Ledger(t.events, doc)
        row = tiers[tier]
        row["merged"] += 1
        row["reviewed"] += bool(ledger.runs("review"))
        person = any(e.get("event") == "continued" or (e.get("event") == "accepted" and e.get("by") == "person")
                     or (e.get("event") == "finding" and e.get("by") == "owner") for e in t.events)
        row["no_person"] += tier == "AUTO" and not person
        before_ship = t.events[:t.events.index(ships[0])] if ships else t.events
        row["first_try"] += not any(e.get("event") == "step" and e.get("result") == "fail" and e.get("counted", True)
                                    and e.get("step") in SHIP_STEPS for e in before_ship)
        claims = [e["at"] for e in t.events if e.get("event") == "claimed" and e.get("at")]
        if claims:
            row["minutes"].append(max(0.0, (merged_at[nn] - parse_iso(claims[0]).timestamp()) / 60))
        for e in t.events:
            if e.get("event") == "tier_raised":
                raised[e.get("reason") or "?"] += 1
            elif e.get("event") == "consulted":
                consults += 1
            elif e.get("event") == "step" and e.get("status") in ("ran", "could_not_run"):
                step = steps.setdefault(e.get("step"), {"runs": 0, "failed": 0, "could_not_run": 0})
                step["runs"] += 1
                step["could_not_run" if e["status"] == "could_not_run" else "failed"] += e.get("result") == "fail"
                if e.get("step") in REVIEW_STEPS:
                    role = roles.setdefault(e["step"], {"runs": 0, "cost_usd": 0.0, "minutes": 0.0})
                    role["runs"] += 1
                    role["cost_usd"] += e.get("cost_usd") or 0
                    role["minutes"] += (e.get("duration_ms") or 0) / 60000
        first_run = {}  # finding id -> the run that first reported it
        for run in doc["runs"]:
            model = models.setdefault(run.get("model") or NO_MODEL, dict(NO_RUNS))
            model["runs"] += 1
            model["cost_usd"] += run.get("cost_usd") or 0
            found = run.get("findings") or []
            if run.get("role") == "refuter":
                disputes["dismissed" if not found else "parked" if found[0].get("severity") == "parked" else "upheld"] += 1
            for finding in found:
                first_run.setdefault(finding.get("id"), run)
        for fid, finding in ledger.findings.items():
            severity = finding.get("severity")
            if finding.get("role") not in ("review", "security"):
                continue  # a sweep's findings become tickets, not ledger entries
            if severity == "parked":
                parked += 1
            elif severity == "blocking":
                ended = _ended(severity, ledger.last(fid))
                blocking[ended] += 1
                model = models.setdefault(first_run.get(fid, {}).get("model") or NO_MODEL, dict(NO_RUNS))
                model["blocking"] += 1
                model["fixed"] += ended == "fixed"
            elif severity == "advisory":
                advisory[ledger.last(fid).get("outcome")] += 1
    for row in tiers.values():
        minutes = row.pop("minutes")
        row["median_minutes"] = round(statistics.median(minutes), 1) if minutes else None
    decided = sum(blocking.values()) - blocking["open"]
    merged = sum(row["merged"] for row in tiers.values())
    return {
        "since": since, "merged": merged, "left_out": len(tickets) - merged, "tiers": tiers, "raised": dict(raised),
        "consults": consults, "steps": {name: steps[name] for name in sorted(steps, key=_step_rank)},
        "review": {
            "roles": {name: _rounded(roles[name]) for name in REVIEW_STEPS if name in roles},
            "models": {name: _rounded(models[name]) for name in sorted(models)},
            "cost_usd": round(sum(role["cost_usd"] for role in roles.values()), 4),
            "blocking": {"total": sum(blocking.values()), **dict(blocking)},
            "advisory": {"total": sum(advisory.values()), **dict(advisory)},
            "parked": parked, "disputes": dict(disputes),
            # Of the blocking findings that were decided, the share that ended in a fix.
            "hit_rate": round(blocking["fixed"] / decided, 3) if decided else None,
        },
    }


def _step_rank(name):
    return STEP_ORDER.index(name) if name in STEP_ORDER else len(STEP_ORDER)


def _rounded(row):
    return {key: round(value, 4) if isinstance(value, float) else value for key, value in row.items()}


def _span(minutes):
    if minutes is None:
        return "-"
    minutes = int(round(minutes))
    if minutes < 60:
        return f"{minutes}m"
    if minutes < 1440:
        return f"{minutes // 60}h{minutes % 60:02d}m"
    return f"{minutes // 1440}d{minutes % 1440 // 60}h"


def _table(head, rows):
    """Lines of a table: the first column left-aligned, the rest right-aligned under their headings."""
    widths = [max(len(str(row[i])) for row in [head, *rows]) for i in range(len(head))]
    return ["  ".join(str(cell).ljust(widths[i]) if i == 0 else str(cell).rjust(widths[i]) for i, cell in enumerate(row))
            .rstrip() for row in [head, *rows]]


def _listed(counts, names):
    """'Fixed 6, dismissed by the refuter 2': the outcomes that happened, in a fixed order."""
    parts = [f"{label} {counts[key]}" for key, label in names if counts.get(key)]
    return (", ".join(parts)[:1].upper() + ", ".join(parts)[1:] + ".") if parts else ""


def render(data):
    when = f" since {data['since']}" if data["since"] else ""
    if not data["merged"]:
        return f"No ticket has merged{when}, so there is nothing to count yet."
    tiers, review = data["tiers"], data["review"]
    head = f"Rail stats: {data['merged']} merged ticket{'' if data['merged'] == 1 else 's'}{when}."
    if data["left_out"]:
        head += f" Not counted: {data['left_out']} {'merged earlier or not merged' if data['since'] else 'not merged'}."
    lines = [head, ""]
    lines += _table(["TICKETS", *tiers], [
        ["merged", *[row["merged"] for row in tiers.values()]],
        ["the reviewer read it", *[row["reviewed"] for row in tiers.values()]],
        ["merged with no review", *[row["merged"] - row["reviewed"] for row in tiers.values()]],
        ["no person acted", *[row["no_person"] for row in tiers.values()]],
        ["shipped on the first try", *[row["first_try"] for row in tiers.values()]],
        ["median claim to merge", *[_span(row["median_minutes"]) for row in tiers.values()]]])
    if data["raised"]:
        reasons = ", ".join(f"{reason} {n}" for reason, n in sorted(data["raised"].items()))
        lines.append(f"Became PERSON at ship: {sum(data['raised'].values())} ({reasons}).")
    failed = [[name, s["runs"], s["failed"], s["could_not_run"]] for name, s in data["steps"].items()
              if s["failed"] or s["could_not_run"]]
    lines.append("")
    if failed:
        lines += _table(["STEPS THAT FAILED", "runs", "failed", "could not run"], failed)
    else:
        lines.append("No step failed.")
    if data["consults"]:
        lines.append(f"Consult ran {data['consults']} times.")
    if not review["roles"]:
        return "\n".join(lines + ["", "No review ran."])
    roles = review["roles"]
    total = ["total", sum(r["runs"] for r in roles.values()), f"${review['cost_usd']:.2f}",
             _span(sum(r["minutes"] for r in roles.values()))]
    lines += ["", *_table(["REVIEW", "runs", "cost", "time"], [
        *[[name, r["runs"], f"${r['cost_usd']:.2f}", _span(r["minutes"])] for name, r in roles.items()], total])]
    reviewed = sum(row["reviewed"] for row in tiers.values())
    if reviewed:
        lines.append(f"${review['cost_usd'] / reviewed:.2f} for each ticket the reviewer read.")
    lines += ["", *_table(["BY MODEL", "runs", "cost", "blocking", "fixed"], [
        [name, m["runs"], f"${m['cost_usd']:.2f}", m["blocking"], m["fixed"]] for name, m in review["models"].items()])]
    blocking, advisory = review["blocking"], review["advisory"]
    lines += ["", f"Blocking findings: {blocking['total']}. " + _listed(blocking, (
        ("fixed", "fixed"), ("dismissed", "dismissed by the refuter"), ("declined_by_person", "declined by a person"),
        ("parked", "parked"), ("open", "still open")))]
    if review["hit_rate"] is not None:
        lines.append(f"Hit rate: {review['hit_rate']:.0%} of the decided ones ended in a fix. A finding the author fixed"
                     " without disputing it counts as a hit, so read this as an upper bound.")
    lines.append(f"Advisory findings: {advisory['total']}. " + _listed(advisory, (
        ("fixed", "fixed"), ("declined", "declined"), ("parked", "parked"), ("open", "still open"))))
    if review["parked"]:
        lines.append(f"Parked by the reviewer: {review['parked']}.")
    if review["disputes"]:
        lines.append(f"Disputes: {sum(review['disputes'].values())}. " + _listed(review["disputes"], (
            ("dismissed", "the refuter dismissed"), ("parked", "parked"), ("upheld", "upheld"))))
    return "\n".join(line.rstrip() for line in lines)
