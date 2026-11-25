#!/usr/bin/env python3
"""Compare the tokens a run's cost proxies logged with the totals the CLI itself reported, per role.

The CLI's totals are the `modelUsage` of each stream's last result line (every model the run used, subagents and
helper calls included), summed over the role's streams (streams/NNN-ROLE.jsonl). Review and consult runs write no
stream, so only the proxy counts them. Tokens: input, output, cache write, cache read.

  proxy_vs_cli.py RUN_DIR [RUN_DIR ...]"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import proxy  # noqa: E402
from bench.driver import ROLES, read_stream  # noqa: E402

CLI_KEYS = {"input": "inputTokens", "output": "outputTokens", "cache_write": "cacheCreationInputTokens",
            "cache_read": "cacheReadInputTokens"}


def cli_totals(run_dir):
    out = {}
    folder = os.path.join(run_dir, "streams")
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        role = name.rsplit("-", 1)[-1].replace(".jsonl", "")
        result = read_stream(os.path.join(folder, name)) or {}
        total = out.setdefault(role, {k: 0 for k in CLI_KEYS} | {"cost_usd": 0.0, "streams": 0})
        total["streams"] += 1
        for usage in (result.get("modelUsage") or {}).values():
            for key, cli in CLI_KEYS.items():
                total[key] += int(usage.get(cli) or 0)
        total["cost_usd"] += float(result.get("total_cost_usd") or 0)
    return out


def main(dirs):
    for run_dir in dirs:
        print(f"== {os.path.basename(os.path.normpath(run_dir))}")
        cli = cli_totals(run_dir)
        logged = proxy.usage(run_dir, ROLES)
        for role in ROLES:
            c, p = cli.get(role), logged.get(role)
            if not c and not p:
                continue
            parts = []
            for key in CLI_KEYS:
                a = (c or {}).get(key)
                b = (p or {}).get(key)
                if a is None:
                    parts.append(f"{key} proxy {b} (no stream)")
                else:
                    diff = (b or 0) - a
                    pct = f"{100 * diff / a:+.1f}%" if a else "n/a"
                    parts.append(f"{key} cli {a} proxy {b} ({pct})")
            extra = f"; cli cost {c['cost_usd']:.4f} USD over {c['streams']} streams" if c else ""
            extra += f"; proxy requests {p['requests']} statuses {p.get('statuses')}" if p else ""
            print(f"  {role}: " + ", ".join(parts) + extra)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
