"""`[product] ready`: exit 0 once the service answers. It changes nothing."""

import os
import sys

from run import RUN, call

try:
    status, _ = call("GET")
    sys.exit(0 if status == 200 else 1)
except Exception as error:
    print("ready: no answer yet:", error)
    try:
        with open(os.path.join(RUN, "log")) as f:
            print(f.read()[-2000:])
    except OSError:
        pass
    sys.exit(1)
