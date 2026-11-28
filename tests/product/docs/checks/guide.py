#!/usr/bin/env python3
"""The driving check of the `guide` surface: read the guide as a user would, and write down what it says."""

import os
import sys

guide = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guide.md")
with open(guide) as f:
    text = f.read()
with open(os.path.join(os.environ["RAIL_EVIDENCE"], "guide.txt"), "w") as f:
    f.write(text)
if "calculator" not in text:
    print("guide: the guide does not say what the product is")
    sys.exit(1)
print("guide: it says what the product is")
