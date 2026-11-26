#!/usr/bin/env python3
"""After admission and the hardness runs: per project, the hardness table and the choice of fifteen situations, twelve
to work with and three held out (PLAN section 4).

A situation is easy when plain Haiku 5.5 (arm plain-haiku) solved it in 3 of 3 scored runs (merged, that is said
DONE, and right: the report's "solved alone"); runs to run again and tainted runs are not scored, and a situation
with fewer than three scored runs is "not settled" and is not chosen. Of the admitted situations that are settled and
not easy, fifteen are drawn by a shuffle seeded with --seed, stratified by kind (each kind's share by largest
remainder); the last three drawn are held out.

  choose.py PROJECT_FILE ... [--seed 20261127] [--count 15] [--held 3] [--apply]

Admission is read from each situation's admission.toml in the store (bench admit writes it). Prints, per project, one
row per admitted situation (Haiku's solved runs, right at the stop, easy or not) and the choice. With --apply, writes
half = "held" for the held-out ones into the project file and bench/sets/SET/CHOSEN.toml with the lists; a project
with fewer than --count to choose from is reported and left unchanged."""

import argparse
import collections
import glob
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import runs, sealed, sets, tomlw  # noqa: E402
from bench.common import settings, store  # noqa: E402

ARM = os.environ.get("BENCH_HARDNESS_ARM", "plain-haiku")  # the suite and a dry run use a fake arm


def hardness(root, project):
    """{situation id: [result, ...]} of the hardness arm's scored runs."""
    out = collections.defaultdict(list)
    for folder in glob.glob(os.path.join(root, "runs", f"{project.name}.*.{ARM}.*")):
        r = runs.Run(folder).result
        if r and r.get("set") == project.set and r.get("project") == project.name and not r.get("again") \
                and not r.get("tainted"):
            out[r["situation"]].append(r)
    return out


def draw(items, count, seed):
    rng = random.Random(seed)
    groups = collections.defaultdict(list)
    for s in items:
        groups[s.kind].append(s)
    kinds = sorted(groups)
    for k in kinds:
        rng.shuffle(groups[k])
    exact = {k: count * len(groups[k]) / len(items) for k in kinds}
    take = {k: math.floor(v) for k, v in exact.items()}
    for k in sorted(kinds, key=lambda k: (-(exact[k] - take[k]), k))[:count - sum(take.values())]:
        take[k] += 1
    picked = [s for k in kinds for s in groups[k][:take[k]]]
    rng.shuffle(picked)
    return picked


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("projects", nargs="+")
    p.add_argument("--seed", type=int, default=20261127)
    p.add_argument("--count", type=int, default=15)
    p.add_argument("--held", type=int, default=3)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    root = store(settings())
    chosen_all = {}
    for path in a.projects:
        project = sets.load(path)
        hard = hardness(root, project)
        admitted = [s for s in project.situations
                    if runs.read_toml(os.path.join(sealed.folder(root, s), "admission.toml")).get("admitted")]
        print(f"## {project.name}: {len(admitted)} admitted of {len(project.situations)}")
        print("| Situation | Kind | Scored runs | Solved alone | Right at the stop | Verdict |")
        print("|---|---|---|---|---|---|")
        pool, easy, unsettled = [], [], []
        for s in admitted:
            rs = hard.get(s.id, [])
            alone = sum(1 for r in rs if r.get("merged") and r.get("right_merged"))
            stop = sum(1 for r in rs if r.get("right_stop"))
            if len(rs) < 3:
                verdict = "not settled"
                unsettled.append(s.id)
            elif alone == len(rs):
                verdict = "easy"
                easy.append(s.id)
            else:
                verdict = "kept"
                pool.append(s)
            print(f"| {s.id} | {s.kind} | {len(rs)} | {alone} | {stop} | {verdict} |")
        print(f"\nBefore the hardness filter: {len(admitted)}; easy (dropped): {len(easy)}; not settled: "
              f"{len(unsettled)}; left: {len(pool)}")
        if len(pool) < a.count:
            print(f"**{project.name} has {len(pool)} to choose from, fewer than {a.count}: nothing chosen.**\n")
            continue
        picked = draw(pool, a.count, a.seed)
        held = picked[len(picked) - a.held:]
        work = picked[:len(picked) - a.held]
        print(f"Chosen (seed {a.seed}): work {' '.join(s.id for s in work)}; held {' '.join(s.id for s in held)}\n")
        chosen_all[project.name] = {"file": os.path.relpath(path), "seed": a.seed, "admitted": len(admitted),
                                    "easy": easy, "not_settled": unsettled, "work": [s.id for s in work],
                                    "held": [s.id for s in held]}
        if a.apply:
            with open(path) as f:
                text = f.read()
            for s in held:
                pattern = re.compile(rf'(^id = "{re.escape(s.id)}"\n(?:(?!^\[\[situation\]\]).*\n)*?)^half = "work"$',
                                     re.M)
                text, n = pattern.subn(r'\1half = "held"', text, count=1)
                if n != 1:
                    raise SystemExit(f"{path}: could not set half for {s.id}")
            with open(path, "w") as f:
                f.write(text)
            sets.load(path)
    if a.apply and chosen_all:
        folder = os.path.dirname(os.path.abspath(a.projects[0]))
        out = os.path.join(folder, "CHOSEN.toml")
        old = {}
        if os.path.exists(out):
            import tomllib
            with open(out, "rb") as f:
                old = tomllib.load(f)
        old.update(chosen_all)
        with open(out, "w") as f:
            f.write("# The fifteen situations per project, chosen by bench/cloud/choose.py after admission and the "
                    "hardness runs.\n" + tomlw.dumps(old))
        print(f"wrote {out}")
    print(json.dumps({k: {"work": v["work"], "held": v["held"]} for k, v in chosen_all.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
