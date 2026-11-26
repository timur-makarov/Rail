"""The API driven over a real socket, as a client would use it."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from notes.api import serve
from notes.store import Store


@pytest.fixture
def url():
    server = serve(Store())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(url, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_a_created_note_is_listed(url):
    status, note = call(url + "/notes", "POST", {"title": "write the report"})
    assert (status, note) == (201, {"id": 1, "title": "write the report", "done": False})
    assert call(url + "/notes") == (200, [note])


def test_a_note_with_no_title_is_a_400(url):
    status, body = call(url + "/notes", "POST", {})
    assert (status, body) == (400, {"error": "a note needs a title"})


def test_a_note_is_finished_once_and_an_unknown_one_is_a_404(url):
    call(url + "/notes", "POST", {"title": "write the report"})
    assert call(url + "/notes/1/done", "POST") == (200, {"done": True})
    assert call(url + "/notes/7/done", "POST") == (404, {"done": False})
    assert call(url + "/nowhere") == (404, {"error": "not found"})
