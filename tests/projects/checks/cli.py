#!/usr/bin/env python3
"""The driving check of the `cli` surface: run the built command as a person would, and write down what it printed."""

import os
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run import planted, settings

evidence = os.environ["RAIL_EVIDENCE"]
notes, seen, printed = os.path.join(evidence, "notes.txt"), [], ""
for words in (["add", "write the report"], ["add", "send it"], ["done", "1"], ["list"]):
    done = subprocess.run(["bash", "-c", settings()["cli"] + " " + " ".join(shlex.quote(w) for w in [notes, *words])],
                          capture_output=True, text=True, env=planted())
    seen.append(f"$ notes {' '.join(words)}\nexit {done.returncode}\n{done.stdout}{done.stderr}")
    printed = done.stdout
with open(os.path.join(evidence, "commands.txt"), "w") as f:
    f.write("\n".join(seen))
want = "[x] write the report\n[ ] send it\n"
if printed != want:
    print(f"cli: the list printed {printed!r}, wanted {want!r}")
    sys.exit(1)
print("cli: two notes were added, one finished, and both listed")
