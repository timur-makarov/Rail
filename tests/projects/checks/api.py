#!/usr/bin/env python3
"""The driving check of the `api` surface: use the started service as a client would, and write down what it did."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run import call

seen = []


def request(method, path="", body=None):
    status, answered = call(method, path, body)
    seen.append(f"{method} {path or '/'} {json.dumps(body) if body is not None else ''}\n{status} {json.dumps(answered)}\n")
    return status, answered


created, note = request("POST", body={"title": "write the report"})
finished, _ = request("POST", f"/{note.get('id')}/done")
listed, notes = request("GET")
got = [(n.get("title"), n.get("done")) for n in notes] if isinstance(notes, list) else notes
want = [("seeded", False), ("write the report", True)]
with open(os.path.join(os.environ["RAIL_EVIDENCE"], "requests.txt"), "w") as f:
    f.write("\n".join(seen))
if (created, finished, listed, got) != (201, 200, 200, want):
    print(f"api: the list holds {got}, wanted {want} (statuses {created}, {finished}, {listed})")
    sys.exit(1)
print("api: a note was added, finished and listed beside the seeded one")
