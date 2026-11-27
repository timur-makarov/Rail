"""The HTTP API: GET /notes, POST /notes, POST /notes/ID/done."""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from notes.store import Store

DONE = re.compile(r"^/notes/(\d+)/done$")
# A fault to switch on from outside, for a check that drives the running service:
# the list comes back empty.
FAULT = "NOTES_FAULT"


def handler(store: Store) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def answer(self, status: int, body: object) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/notes":
                self.answer(200, [] if os.environ.get(FAULT) else store.all())
            else:
                self.answer(404, {"error": "not found"})

        def do_POST(self) -> None:
            done = DONE.match(self.path)
            if done:
                found = store.finish(int(done.group(1)))
                self.answer(200 if found else 404, {"done": found})
            elif self.path == "/notes":
                self.create()
            else:
                self.answer(404, {"error": "not found"})

        def create(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                title = json.loads(self.rfile.read(length) or b"{}").get("title", "")
                self.answer(201, store.add(title))
            except (ValueError, AttributeError) as error:
                self.answer(400, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            pass  # the tests read the answers, not a log

    return Handler


def serve(store: Store, port: int = 0) -> ThreadingHTTPServer:
    """A server bound to the port (0: any free one); the caller runs serve_forever."""
    return ThreadingHTTPServer(("127.0.0.1", port), handler(store))
