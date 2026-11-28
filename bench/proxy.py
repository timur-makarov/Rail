"""A pass-through cost proxy: each role's children are pointed at their own port with ANTHROPIC_BASE_URL, and every
request goes on to the real API unchanged. The proxy logs only the path, the status and the usage (input, output,
cache write, cache read tokens), never a header or a body, one JSON line per request.

It refuses /v1/code/agent-proxy/ws: Claude Code opens that WebSocket at its base URL to carry its Bash tool's HTTPS,
so a proxy that passed it would give a network-locked child its network back (CLOUD-CHECK-RESULT.md, probes 8 and
10).

Run alone: python3 -m bench.proxy LOG --role worker [--upstream URL]"""

import http.client
import http.server
import json
import os
import socket
import socketserver
import sys
import threading
import urllib.parse

REFUSED = ("/v1/code/agent-proxy/ws",)
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding",
       "upgrade", "host", "accept-encoding", "content-length"}
USAGE_KEYS = (("input", "input_tokens"), ("output", "output_tokens"), ("cache_write", "cache_creation_input_tokens"),
              ("cache_read", "cache_read_input_tokens"))


def default_upstream():
    return os.environ.get("BENCH_UPSTREAM") or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"


def last_statuses(folder, roles):
    """{role: the status of its last logged request}."""
    out = {}
    for role in roles:
        path = os.path.join(folder, f"proxy-{role}.jsonl")
        if os.path.exists(path):
            with open(path) as f:
                lines = [line for line in f if line.strip()]
            if lines:
                try:
                    out[role] = json.loads(lines[-1]).get("status")
                except ValueError:
                    pass
    return out


class Usage:
    """Usage read from a response as it passes: a JSON body, or the message_start and message_delta events of a
    server-sent event stream."""

    def __init__(self):
        self.found = {k: 0 for k, _ in USAGE_KEYS}
        self.buffer = b""
        self.seen = False

    def add(self, usage, delta=False):
        if not isinstance(usage, dict):
            return
        self.seen = True
        for key, name in USAGE_KEYS:
            value = usage.get(name)
            if isinstance(value, int):
                # message_delta repeats the running output count: keep the last, add nothing twice
                self.found[key] = value if delta or key == "output" else self.found[key] + value

    def feed(self, chunk):
        self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            try:
                data = json.loads(line[5:].strip())
            except ValueError:
                continue
            if data.get("type") == "message_start":
                self.add((data.get("message") or {}).get("usage"))
            elif data.get("type") == "message_delta":
                self.add(data.get("usage"), delta=True)

    def body(self, raw):
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if isinstance(data, dict):
            self.add(data.get("usage"))


def handler_for(upstream, log_path, role, lock):
    target = urllib.parse.urlsplit(upstream)

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # no request lines on stderr: they hold paths with query strings
            pass

        def record(self, status, usage=None):
            entry = {"role": role, "path": urllib.parse.urlsplit(self.path).path, "status": status}
            if usage is not None and usage.seen:
                entry["usage"] = usage.found
            with lock:
                with open(log_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")

        def refuse(self, status, why, read_body=True):
            self.record(status)
            if read_body:  # read what was sent, so the child gets the answer and not a reset connection
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    self.rfile.read(length)
            body = json.dumps({"error": why}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def forward(self):
            path = urllib.parse.urlsplit(self.path).path
            if any(path.rstrip("/").endswith(r) for r in REFUSED) or self.headers.get("Upgrade"):
                return self.refuse(403, "refused by the bench's proxy: no tunnels")
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            headers["Host"] = target.netloc
            conn_class = http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
            conn = conn_class(target.netloc, timeout=900)
            try:
                conn.request(self.command, (target.path.rstrip("/") + self.path) or "/", body=body, headers=headers)
                resp = conn.getresponse()
            except OSError as e:
                conn.close()
                return self.refuse(502, f"upstream: {e.__class__.__name__}", read_body=False)
            usage = Usage()
            streaming = "text/event-stream" in (resp.getheader("Content-Type") or "")
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            raw = b""
            try:
                while True:
                    chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                    if not chunk:
                        break
                    if streaming:
                        usage.feed(chunk)
                    elif len(raw) < 4_000_000:
                        raw += chunk
                    self.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                if not streaming:
                    usage.body(raw)
                self.record(resp.status, usage)  # before the last chunk: once a child has its answer, it is logged
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                self.record(resp.status, usage)
            finally:
                conn.close()

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = forward

    return Handler


class TCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    """The same proxy on a Unix socket, which a child in its own network namespace reaches through netlock's relay."""
    daemon_threads = True

    def get_request(self):
        request, _ = super().get_request()
        return request, ("unix", 0)


class Proxy:
    """One role's proxy: a TCP port on 127.0.0.1, and with `sock` a Unix socket too."""

    def __init__(self, role, log_path, upstream=None, sock=None):
        self.role, self.log_path = role, log_path
        lock = threading.Lock()
        handler = handler_for(upstream or default_upstream(), log_path, role, lock)
        self.tcp = TCPServer(("127.0.0.1", 0), handler)
        self.port = self.tcp.server_address[1]
        self.unix = None
        self.sock = sock
        if sock:
            if os.path.exists(sock):
                os.unlink(sock)
            self.unix = UnixServer(sock, handler)
        self.threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (self.tcp, self.unix) if s]
        for t in self.threads:
            t.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        for s in (self.tcp, self.unix):
            if s:
                s.shutdown()
                s.server_close()
        if self.sock and os.path.exists(self.sock):
            os.unlink(self.sock)


def start(roles, folder, upstream=None, unix=False):
    """A proxy per role, logging to FOLDER/proxy-ROLE.jsonl. Returns {role: Proxy}."""
    out = {}
    for role in roles:
        sock = os.path.join(folder, f"proxy-{role}.sock") if unix else None
        out[role] = Proxy(role, os.path.join(folder, f"proxy-{role}.jsonl"), upstream, sock)
    return out


def usage(folder, roles):
    """What the proxies logged, summed per role: requests, statuses and tokens."""
    out = {}
    for role in roles:
        path = os.path.join(folder, f"proxy-{role}.jsonl")
        total = {"requests": 0, "refused": 0, "errors": 0, **{k: 0 for k, _ in USAGE_KEYS}}
        statuses = {}
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    total["requests"] += 1
                    statuses[str(entry.get("status"))] = statuses.get(str(entry.get("status")), 0) + 1
                    if entry.get("status") == 403:
                        total["refused"] += 1
                    elif isinstance(entry.get("status"), int) and entry["status"] >= 400:
                        total["errors"] += 1
                    for key, _ in USAGE_KEYS:
                        total[key] += (entry.get("usage") or {}).get(key, 0)
        if total["requests"]:
            total["statuses"] = statuses
            out[role] = total
    return out


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    import argparse
    import time

    p = argparse.ArgumentParser()
    p.add_argument("log")
    p.add_argument("--role", default="worker")
    p.add_argument("--upstream")
    a = p.parse_args()
    proxy = Proxy(a.role, a.log, a.upstream)
    print(proxy.url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        proxy.close()
        sys.exit(0)
