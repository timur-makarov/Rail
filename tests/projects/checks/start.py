"""`[product] start`: start the service on a free port, in the background, and return."""

import os
import shutil
import socket
import subprocess

from run import RUN, planted, settings

shutil.rmtree(RUN, ignore_errors=True)
os.makedirs(RUN)
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
command = settings()["start"].format(port=port, run=RUN)
with open(os.path.join(RUN, "log"), "w") as log:
    started = subprocess.Popen(["bash", "-c", command], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               env=planted())
for name, value in (("port", port), ("pid", started.pid)):
    with open(os.path.join(RUN, name), "w") as f:
        f.write(f"{value}\n")
print(f"start: the service is starting on port {port}")
