"""`[product] stop`: stop what start started."""

import os
import signal

from run import RUN

try:
    with open(os.path.join(RUN, "pid")) as f:
        os.kill(int(f.read()), signal.SIGTERM)
    print("stop: stopped the service")
except (OSError, ValueError):
    print("stop: no service was running")
