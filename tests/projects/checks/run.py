"""What the product's scripts and the driving checks share: how the product is started (product.json, beside this
file), where one run keeps its files, and one request to the started service. The folder of a run is outside the
checkout, so that nothing a run leaves is ever committed."""

import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(tempfile.gettempdir(), "rail-notes-" + hashlib.sha256(os.getcwd().encode()).hexdigest()[:12])
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the service is on this machine


def settings():
    """{"start": a shell command with {port} and {run}, "path": the path of the notes API, "cli": a command}."""
    with open(os.path.join(HERE, "product.json")) as f:
        return json.load(f)


def call(method, path="", body=None):
    """One request to the started service. Returns (status, the JSON it answered)."""
    with open(os.path.join(RUN, "port")) as f:
        url = f"http://127.0.0.1:{f.read().strip()}{settings()['path']}{path}"
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with DIRECT.open(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def planted():
    """The environment the product runs in. Each sample has a fault that NOTES_FAULT switches on; Rail's tests ask
    for it with RAIL_TEST_PLANT, a name the samples do not read, so that a sample's own tests never run with it."""
    return {**os.environ, **({"NOTES_FAULT": "1"} if os.environ.get("RAIL_TEST_PLANT") else {})}
