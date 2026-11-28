#!/usr/bin/env python3
"""The driving check of the `api` surface: use the started server as a client would, and write down what it did."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import get

evidence = os.environ["RAIL_EVIDENCE"]
seen, failed = [], []
for path, want in (("/whoami", {"user": "test-user"}), ("/add?a=2&b=3", {"sum": 5})):
    got = get(path)
    seen.append(f"GET {path}\n{json.dumps(got)}\n")
    if any(got.get(key) != value for key, value in want.items()):
        failed.append(f"GET {path}: wanted {want}, got {got}")
with open(os.path.join(evidence, "requests.txt"), "w") as f:
    f.write("\n".join(seen))
with open(os.path.join(evidence, "screen.png"), "wb") as f:
    f.write(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")  # stands in for a screenshot: never text
print("\n".join(failed) or "api: every request answered as expected")
sys.exit(1 if failed else 0)
