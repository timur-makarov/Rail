#!/usr/bin/env python3
"""How near the account's usage limit the runs are, from the rate-limit events the CLI writes into each stream (a
child's stream-json carries them; the session's own limit is the same account's, CLOUD-CHECK-RESULT.md probe 14).

  usage_check.py [--hours 6] [--stop-at 0.9]

Reads every stream under STORE/runs/*/streams/ and STORE/check/ changed in the last --hours, finds each object with a
`utilization` (and its `status`, `rateLimitType`), and prints the newest and highest per limit type and every status
seen. Exit 3 when the newest event of a type has a status not starting with "allowed" (allowed_warning passes), or
its utilization is at or above --stop-at; 0 otherwise (also when no event was found, which it says)."""

import argparse
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench.common import settings, store  # noqa: E402


def events(obj):
    if isinstance(obj, dict):
        if "utilization" in obj:
            yield obj
        for v in obj.values():
            yield from events(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from events(v)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=float, default=6)
    p.add_argument("--stop-at", type=float, default=0.9)
    a = p.parse_args(argv)
    root = store(settings())
    since = time.time() - a.hours * 3600
    paths = glob.glob(os.path.join(root, "runs", "*", "streams", "*.jsonl")) + \
        glob.glob(os.path.join(root, "check", "**", "*.jsonl"), recursive=True)
    newest, highest, statuses = {}, {}, {}
    for path in paths:
        mtime = os.path.getmtime(path)
        if mtime < since:
            continue
        with open(path, errors="replace") as f:
            for line in f:
                if '"utilization"' not in line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                for e in events(data):
                    kind = str(e.get("rateLimitType") or e.get("type") or "unknown")
                    try:
                        u = float(e.get("utilization"))
                    except (TypeError, ValueError):
                        continue
                    status = str(e.get("status", ""))
                    statuses.setdefault(kind, set()).add(status)
                    highest[kind] = max(highest.get(kind, 0.0), u)
                    if kind not in newest or mtime >= newest[kind][0]:
                        newest[kind] = (mtime, u, status)
    if not newest:
        print(f"no rate-limit event in the streams of the last {a.hours} hours")
        return 0
    stop = False
    for kind in sorted(newest):
        _, u, status = newest[kind]
        bad = not status.startswith("allowed") or u >= a.stop_at
        stop = stop or bad
        print(f"{kind}: newest utilization {u:.2f} ({status}), highest {highest[kind]:.2f}, statuses seen "
              f"{sorted(statuses[kind])}{'  <- STOP' if bad else ''}")
    return 3 if stop else 0


if __name__ == "__main__":
    sys.exit(main())
