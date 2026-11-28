#!/usr/bin/env python3
"""The driving check of the `cli` surface: run the program as a user would, and write down what it printed."""

import os
import subprocess
import sys

calc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calc.py")
ran = subprocess.run([sys.executable, calc, "add", "2", "3"], capture_output=True, text=True)
with open(os.path.join(os.environ["RAIL_EVIDENCE"], "run.txt"), "w") as f:
    f.write(f"$ calc.py add 2 3\n{ran.stdout}{ran.stderr}exit {ran.returncode}\n")
if ran.returncode != 0 or ran.stdout.strip() != "5":
    print(f"cli: calc.py add 2 3 printed {ran.stdout.strip()!r}, wanted '5'")
    sys.exit(1)
print("cli: add works")
