#!/usr/bin/env python3
"""The admission results as Markdown: per project a table (one row per situation: admitted or refused, the first
reason, minutes, the sealed folder's size, free disk after), the reasons counted, and the admitted ids.

  admission_table.py OUTDIR [OUTDIR ...]    (the folders admit_one.py wrote ID.json into)"""

import collections
import glob
import json
import os
import re
import sys


def short(reason):
    """A reason's kind, for counting: its words before the first colon or parenthesis."""
    return re.split(r"[:(]", reason, maxsplit=1)[0].strip()


def main(folders):
    records = []
    for folder in folders:
        for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
            with open(path) as f:
                records.append(json.load(f))
    by_project = collections.defaultdict(list)
    for r in records:
        by_project[r["project"]].append(r)
    out = []
    for project in sorted(by_project):
        rows = sorted(by_project[project], key=lambda r: r["situation"])
        admitted = [r["situation"] for r in rows if r["admitted"]]
        out += [f"## {project}: {len(admitted)} admitted of {len(rows)} tried", "",
                "| Situation | Result | First reason | Minutes | Sealed MB | Free GB after |", "|---|---|---|---|---|---|"]
        for r in rows:
            first = (r["reasons"][0] if r["reasons"] else "").replace("|", "/").replace("\n", " ")[:160]
            minutes = round(sum(r.get("seconds", {}).values()) / 60, 1)
            out.append(f"| {r['situation']} | {'admitted' if r['admitted'] else 'refused'} | {first} | {minutes} | "
                       f"{r.get('sizes_mb', {}).get('sealed', '')}{' (pruned)' if r.get('pruned') else ''} | "
                       f"{r.get('free_gb', '')} |")
        counts = collections.Counter(short(x) for r in rows for x in r["reasons"])
        out += ["", "Reasons (a situation can have several): "
                + (", ".join(f"{k} {v}" for k, v in counts.most_common()) or "none"), "",
                "Admitted: " + (" ".join(admitted) or "none"), ""]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
