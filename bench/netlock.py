"""The network lock: on Linux as root, a child runs in a network namespace of its own (`unshare -n`), where nothing
but loopback exists. Inside, this relay brings loopback up and listens on 127.0.0.1:PORT for each role, forwarding
every connection to that role's proxy over a Unix socket, which crosses the namespace. So the child reaches the
model API through the cost proxy and nothing else: no registry, no forge, no web (CLOUD-CHECK-RESULT.md, probe 10).

Where it is not available (macOS, not root, no unshare) the run goes on unlocked, and every result of that run is
marked `locked = false`; the report shows such runs apart.

  python3 netlock.py PORT=SOCKET ... -- COMMAND ...   (run under unshare -n)"""

import fcntl
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1
HERE = os.path.abspath(__file__)


def available():
    """Whether this machine can lock a child's network: Linux, root, and unshare on PATH."""
    return sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0 and bool(
        shutil.which("unshare"))


def wrap(argv, ports):
    """The argv that runs `argv` locked, with {port: unix socket} relayed inside."""
    maps = [f"{port}={sock}" for port, sock in sorted(ports.items())]
    return ["unshare", "-n", sys.executable, HERE, *maps, "--", *argv]


def loopback_up():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ifr = struct.pack("16sH", b"lo", 0)
        flags = struct.unpack("16sH", fcntl.ioctl(s.fileno(), SIOCGIFFLAGS, ifr)[:18])[1]
        fcntl.ioctl(s.fileno(), SIOCSIFFLAGS, struct.pack("16sH", b"lo", flags | IFF_UP))
    finally:
        s.close()


def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def relay(listener, sock_path):
    """Accept on `listener` and join each connection to the Unix socket at sock_path, for as long as it runs."""
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            upstream.connect(sock_path)
        except OSError:
            client.close()
            upstream.close()
            continue
        for a, b in ((client, upstream), (upstream, client)):
            threading.Thread(target=pipe, args=(a, b), daemon=True).start()


def listen(port, sock_path):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(64)
    threading.Thread(target=relay, args=(listener, sock_path), daemon=True).start()
    return listener


def main(argv):
    if "--" not in argv:
        print("usage: netlock.py PORT=SOCKET ... -- COMMAND ...", file=sys.stderr)
        return 2
    cut = argv.index("--")
    maps, command = argv[:cut], argv[cut + 1:]
    loopback_up()
    for item in maps:
        port, sock = item.split("=", 1)
        listen(int(port), sock)
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
