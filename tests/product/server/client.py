"""What the scripts and the driving check share: where the started server listens, and one request to it."""

import json
import os
import urllib.request

RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".run")


def get(path):
    with open(os.path.join(RUN, "port")) as f:
        port = f.read().strip()
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return json.load(response)
