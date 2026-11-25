#!/usr/bin/env python3
"""List the failed or odd runs in the store for reading by hand, each with why it is odd and the paths of its streams.

Odd, in this order: to run again (rate limit, overload, sign-in); tainted; merged but wrong; unlocked; a proxy that
refused a tunnel or saw errors; a run with no tokens at the proxy; ended neither merged nor done; right at the stop but
not merged; the slowest and the dearest of the rest.

  odd_runs.py [--limit 10] [--arms A,B]"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import runs  # noqa: E402
from bench.common import settings, store  # noqa: E402


def reasons(r):
    out = []
    if r.get("again"):
        out.append(f"to run again: {r.get('detail', r.get('end'))}")
    if r.get("tainted"):
        out.append("tainted: " + ", ".join(sorted({h['term'] for h in r.get('taint', [])})))
    if r.get("merged") and not r.get("right_merged") and not r.get("again"):
        out.append(f"merged but wrong: {r.get('grade_why', '')[:200]}")
    if not r.get("locked"):
        out.append("unlocked")
    usage = r.get("usage") or {}
    refused = sum(u.get("refused", 0) for u in usage.values())
    errors = sum(u.get("errors", 0) for u in usage.values())
    if refused or errors:
        out.append(f"proxy: {refused} refused, {errors} errors")
    if not r.get("again") and not any(u.get("output") for u in usage.values()):
        out.append("no tokens at the proxy")
    if r.get("end") not in ("MERGED", "DONE"):
        out.append(f"ended {r.get('end')}" + (f": {r.get('detail', '')[:200]}" if r.get("detail") else ""))
    if r.get("right_stop") and not r.get("merged"):
        out.append("right at the stop but not merged")
    return out


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--arms")
    a = p.parse_args(argv)
    root = store(settings())
    arms = set(a.arms.split(",")) if a.arms else None
    found = []
    for folder in sorted(glob.glob(os.path.join(root, "runs", "*"))):
        run_ = runs.Run(folder)
        r = run_.result
        if not r or (arms and r.get("arm") not in arms):
            continue
        why = reasons(r)
        streams = [os.path.join(run_.streams, f) for f in run_.stream_files()]
        found.append((why, r, folder, streams))
    odd = [x for x in found if x[0]]
    rest = sorted((x for x in found if not x[0]), key=lambda x: -(x[1].get("cost_usd") or 0))
    picked = odd[:a.limit]
    for x in rest[:max(0, a.limit - len(picked))]:
        picked.append((["dearest of the rest: " + f"{x[1].get('cost_usd')} USD, {x[1].get('minutes')} min"],) + x[1:])
    for why, r, folder, streams in picked:
        print(f"{os.path.basename(folder)} ({r.get('arm')}, {r.get('situation')}): " + "; ".join(why))
        for s in streams or ["(no stream)"]:
            print(f"    stream: {s}")
        print(f"    log: {os.path.join(folder, 'log.jsonl')}")
    print(f"{len(odd)} odd of {len(found)} runs with a result")
    return 0


if __name__ == "__main__":
    sys.exit(main())
