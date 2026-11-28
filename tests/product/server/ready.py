"""`[product] ready`: exit 0 once the server answers. It changes nothing."""

import sys

from client import get

try:
    sys.exit(0 if get("/health")["ok"] else 1)
except Exception as e:
    print("ready: no answer yet:", e)
    sys.exit(1)
