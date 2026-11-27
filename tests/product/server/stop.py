"""`[product] stop`: stop what start started."""

import os
import signal

RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".run")
try:
    with open(os.path.join(RUN, "pid")) as f:
        os.kill(int(f.read()), signal.SIGTERM)
    print("stop: stopped the server")
except (OSError, ValueError):
    print("stop: no server was running")
os.makedirs(RUN, exist_ok=True)
with open(os.path.join(RUN, "stopped"), "w") as f:
    f.write("yes\n")
