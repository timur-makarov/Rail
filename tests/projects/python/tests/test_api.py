"""The API driven over a real socket, as a client would use it."""

import json
import threading
import unittest
import urllib.error
import urllib.request

from notes.api import serve
from notes.store import Store


def call(url: str, method: str = "GET", body: object = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class ApiTest(unittest.TestCase):
    def served(self) -> str:
        """The address of a server with an empty store, stopped when the test ends."""
        server = serve(Store())
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def test_a_created_note_is_listed(self) -> None:
        url = self.served()
        status, note = call(url + "/notes", "POST", {"title": "write the report"})
        self.assertEqual(
            (status, note), (201, {"id": 1, "title": "write the report", "done": False})
        )
        self.assertEqual(call(url + "/notes"), (200, [note]))

    def test_a_note_with_no_title_is_a_400(self) -> None:
        status, body = call(self.served() + "/notes", "POST", {})
        self.assertEqual((status, body), (400, {"error": "a note needs a title"}))

    def test_a_note_is_finished_once_and_an_unknown_one_is_a_404(self) -> None:
        url = self.served()
        call(url + "/notes", "POST", {"title": "write the report"})
        self.assertEqual(call(url + "/notes/1/done", "POST"), (200, {"done": True}))
        self.assertEqual(call(url + "/notes/7/done", "POST"), (404, {"done": False}))
        self.assertEqual(call(url + "/nowhere"), (404, {"error": "not found"}))
