"""The report: the numbers of PLAN section 5 per arm, on the situations every compared arm may be scored on.

What a run is left out for, each counted:
- to run again (a rate-limit or overload error): never graded;
- tainted: the taint search found something;
- unlocked: its network was not locked; such runs are reported apart, in a section of their own;
- an unadmitted situation, a held-out one (unless asked for), and, per arm, a situation closed before the training
  cutoff of that arm's newest model ([cutoffs] in bench/config.toml).
Then only the situations every compared arm has a scored run on are kept.

Ranges come from resampling whole situations within each project: each resample draws, per project, as many of its
situations as it has, with replacement, and computes the rate again. The 2.5th and 97.5th percentiles are the range.
The seed is stated, so the ranges can be computed again."""

import datetime
import json
import os
import random

from . import arms as armsmod
from . import runs, sealed, sets
from .driver import role_of

RATES = ("solved_alone", "solved_at_stop")


def load_results(store_root):
    """Every graded or to-run-again result under store/runs, with its run.toml."""
    folder = os.path.join(store_root, "runs")
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        r = runs.Run(os.path.join(folder, name))
        if r.result and not r.id.startswith("check."):
            out.append(dict(r.result, project_file=r.meta.get("project", "")))
    return out


def facts(store_root, results):
    """Per situation key: its kind, half, closed date and admission, read from the project files."""
    out = {}
    for path in sorted({r["project_file"] for r in results if r.get("project_file")}):
        try:
            project = sets.load(path)
        except Exception:
            continue
        for s in project.situations:
            admission = runs.read_toml(os.path.join(sealed.folder(store_root, s), "admission.toml"))
            out[(project.set, project.name, s.id)] = {"kind": s.kind, "half": s.half, "closed": s.closed,
                                                      "admitted": bool(admission.get("admitted"))}
    return out


def arm_models(arm_name):
    try:
        arm = armsmod.load(arm_name)
    except Exception:
        return []
    models = [arm.roles[r].get("model") for r in armsmod.ROLES]
    return [m for m in models if m]


def per_run(r):
    """What one graded run scores."""
    alone = bool(r.get("merged") and not r.get("person_acts") and r.get("right_merged"))
    return {"alone": alone, "stop": bool(r.get("right_stop")),
            "stand_in": bool(r.get("merged") and r.get("person_acts") and r.get("right_merged")),
            "merged_alone": bool(r.get("merged") and not r.get("person_acts")),
            "wrong_merge": bool(r.get("merged") and not r.get("person_acts") and not r.get("right_merged")),
            "person": bool(r.get("person_acts"))}


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def rate(by_situation, key):
    """Per situation, the share of its runs with `key`; averaged over situations."""
    return mean([mean([run[key] for run in rs]) for rs in by_situation.values() if rs])


def resample(by_situation, key, projects, seed, n):
    """(low, high): the 2.5th and 97.5th percentiles of the rate over n resamples of whole situations within each
    project."""
    rng = random.Random(seed)
    groups = {}
    for sk in by_situation:
        groups.setdefault(projects[sk], []).append(sk)
    values = []
    for _ in range(n):
        picked = {}
        for members in groups.values():
            for i in range(len(members)):
                sk = rng.choice(members)
                picked[(sk, len(picked))] = by_situation[sk]
        v = rate(picked, key)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def build(results, situation_facts, arms=None, cutoffs=None, held=False, seed=7, resamples=2000, any_situation=False):
    """The report as a dict. `results` are result dicts; `situation_facts` maps (set, project, id) to kind, half,
    closed and admitted; `cutoffs` maps a model to its training cutoff date."""
    cutoffs = cutoffs or {}
    arms = arms or sorted({r["arm"] for r in results})
    left_out = {"again": 0, "tainted": 0, "not admitted": 0, "held out": 0, "before cutoff": 0, "not on every arm": 0}
    scored = {"locked": {}, "unlocked": {}}
    for r in results:
        if r["arm"] not in arms:
            continue
        key = (r.get("set", ""), r.get("project", ""), r["situation"])
        f = situation_facts.get(key, {})
        if r.get("again"):
            left_out["again"] += 1
            continue
        if r.get("tainted"):
            left_out["tainted"] += 1
            continue
        if not any_situation and not f.get("admitted"):
            left_out["not admitted"] += 1
            continue
        if f.get("half") == "held" and not held or f.get("half") == "work" and held:
            left_out["held out"] += 1
            continue
        closed = f.get("closed")
        if closed and any(cutoffs.get(m) and closed < as_date(cutoffs[m]) for m in r.get("models", [])):
            left_out["before cutoff"] += 1
            continue
        section = "locked" if r.get("locked") else "unlocked"
        scored[section].setdefault(r["arm"], {}).setdefault(key, []).append(r)
    out = {"seed": seed, "resamples": resamples, "arms": arms, "left_out": left_out, "sections": {}}
    for section, per_arm in scored.items():
        common = None
        for arm in arms:
            keys = set(per_arm.get(arm, {}))
            common = keys if common is None else common & keys
        common = common or set()
        for arm in arms:
            dropped = sum(len(rs) for k, rs in per_arm.get(arm, {}).items() if k not in common)
            left_out["not on every arm"] += dropped
        if not common:
            continue
        projects = {k: (k[0], k[1]) for k in common}
        table = {}
        for arm in arms:
            runs_by = {k: per_arm[arm][k] for k in sorted(common)}
            scored_by = {k: [per_run(r) for r in rs] for k, rs in runs_by.items()}
            all_runs = [r for rs in runs_by.values() for r in rs]
            row = {"situations": len(runs_by), "runs": len(all_runs)}
            for key, name in (("alone", "solved_alone"), ("stop", "solved_at_stop")):
                row[name] = rate(scored_by, key)
                row[name + "_range"] = resample(scored_by, key, projects, seed, resamples)
            flat = [p for ps in scored_by.values() for p in ps]
            row["stand_in"] = {"count": sum(p["stand_in"] for p in flat), "runs": len(flat)}
            merged_alone = [p for p in flat if p["merged_alone"]]
            row["wrong_merges"] = {"share": mean([p["wrong_merge"] for p in merged_alone]),
                                   "count": sum(p["wrong_merge"] for p in merged_alone), "of": len(merged_alone)}
            acts = {}
            for r in all_runs:
                for act in r.get("person_acts", []):
                    acts[act] = acts.get(act, 0) + 1
            row["person"] = {"share": mean([p["person"] for p in flat]), "count": sum(p["person"] for p in flat),
                             "acts": acts}
            unsteady = [k for k, ps in scored_by.items() if len(ps) > 1 and len({p["alone"] for p in ps}) > 1]
            row["unsteady"] = {"share": len(unsteady) / len(scored_by), "count": len(unsteady), "of": len(scored_by)}
            row["cost"] = cost(all_runs)
            table[arm] = row
        out["sections"][section] = {"situations": len(common), "arms": table}
    return out


def as_date(value):
    return value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value))


def cost(results):
    """Per role: runs, cost (where the CLI reports one), tokens, turns and minutes, as means per run."""
    n = len(results) or 1
    roles = {}
    for r in results:
        for w in r.get("worked", []):
            role = w.get("role") or role_of(w.get("code"))  # a result written before the driver recorded the role
            d = roles.setdefault(role, {"cost_usd": 0.0, "turns": 0, "minutes": 0.0})
            d["cost_usd"] += w.get("cost_usd") or w.get("total_cost_usd") or 0
            d["turns"] += w.get("turns") or w.get("num_turns") or 0
            d["minutes"] += w.get("minutes") or 0
        for role, cost_usd in (r.get("role_cost") or {}).items():
            roles.setdefault(role, {"cost_usd": 0.0, "turns": 0, "minutes": 0.0})["cost_usd"] += cost_usd
        for role, u in (r.get("usage") or {}).items():
            d = roles.setdefault(role, {"cost_usd": 0.0, "turns": 0, "minutes": 0.0})
            for key in ("input", "output", "cache_write", "cache_read", "requests"):
                d[key] = d.get(key, 0) + u.get(key, 0)
    out = {role: {k: round(v / n, 4) for k, v in d.items()} for role, d in roles.items()}
    out["run"] = {"minutes": round(sum(r.get("minutes", 0) for r in results) / n, 2),
                  "cost_usd": round(sum(r.get("cost_usd", 0) for r in results) / n, 4)}
    return out


def pct(x):
    return "-" if x is None else f"{100 * x:.0f}%"


def render(report):
    lines = [f"Resampled {report['resamples']} times with seed {report['seed']}, whole situations within each project.",
             "Left out: " + ", ".join(f"{k} {v}" for k, v in report["left_out"].items()) + "."]
    for section in ("locked", "unlocked"):
        if section not in report["sections"]:
            continue
        s = report["sections"][section]
        lines += ["", f"## {section.capitalize()} runs: {s['situations']} situations on every arm"
                  + ("" if section == "locked" else " (the network was not locked: read apart)"), "",
                  "| Arm | Solved alone | Solved at the stop | With a stand-in | Wrong merges | Person | Unsteady |"
                  " Cost per run |", "|---|---|---|---|---|---|---|---|"]
        for arm, row in s["arms"].items():
            def ranged(name):
                rng = row[name + "_range"]
                return f"{pct(row[name])} ({pct(rng[0])}-{pct(rng[1])})" if rng else pct(row[name])
            lines.append(
                f"| {arm} | {ranged('solved_alone')}, {row['situations']} sit., {row['runs']} runs"
                f" | {ranged('solved_at_stop')} | {row['stand_in']['count']} of {row['stand_in']['runs']}"
                f" | {pct(row['wrong_merges']['share'])} ({row['wrong_merges']['count']} of {row['wrong_merges']['of']})"
                f" | {pct(row['person']['share'])} ({row['person']['count']}) | {row['unsteady']['count']} of"
                f" {row['unsteady']['of']} | ${row['cost']['run']['cost_usd']:.2f}, {row['cost']['run']['minutes']} min |")
        lines += ["", "Per role, mean per run:"]
        for arm, row in s["arms"].items():
            for role, d in row["cost"].items():
                if role != "run":
                    lines.append(f"- {arm} {role}: " + ", ".join(f"{k} {v}" for k, v in d.items()))
    return "\n".join(lines) + "\n"


def cutoffs_from(conf):
    return conf.get("cutoffs", {})


def from_store(store_root, conf, arms=None, held=False, seed=7, resamples=2000, any_situation=False):
    results = load_results(store_root)
    for r in results:
        r.setdefault("models", arm_models(r["arm"]))
    return build(results, facts(store_root, results), arms, cutoffs_from(conf), held, seed, resamples, any_situation)


def dumps(report):
    return json.dumps(report, default=str, indent=1)
