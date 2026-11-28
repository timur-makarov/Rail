"""`[product] start`: start the server in the background and return."""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
shutil.rmtree(os.path.join(HERE, ".run"), ignore_errors=True)
subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], stdin=subprocess.DEVNULL)
print("start: the server is starting")
