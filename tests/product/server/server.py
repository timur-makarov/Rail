"""The fixture product's server: a calculator over HTTP, with one seeded user."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, ".run")
OFFSET = int(os.environ.get("CALC_FAULT", "0"))  # the planted fault: with 1 here, every sum is one too high


class Handler(BaseHTTPRequestHandler):
    def log_message(self, form, *args):
        print("server:", form % args, flush=True)

    def answer(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/health":
            return self.answer(200, {"ok": True})
        if url.path == "/add":
            return self.answer(200, {"sum": int(query["a"][0]) + int(query["b"][0]) + OFFSET})
        if url.path == "/whoami":
            try:
                with open(os.path.join(RUN, "seed.json")) as f:
                    return self.answer(200, json.load(f))
            except OSError:
                return self.answer(404, {"error": "no user: the product was not seeded"})
        return self.answer(404, {"error": "not found"})


if __name__ == "__main__":
    os.makedirs(RUN, exist_ok=True)
    server = HTTPServer(("127.0.0.1", 0), Handler)  # any free port, so two tickets never meet on one
    with open(os.path.join(RUN, "port"), "w") as f:
        f.write(str(server.server_address[1]))
    with open(os.path.join(RUN, "pid"), "w") as f:
        f.write(str(os.getpid()))
    print("server: listening on", server.server_address[1], flush=True)
    try:
        server.serve_forever()
    finally:
        sys.exit(0)
