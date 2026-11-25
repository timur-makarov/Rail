"""The bench's third part: the cost proxy against a fake upstream, the network lock's relay, and the report on fixture
results."""

import http.client
import http.server
import json
import os
import socket
import threading
import unittest
import urllib.request

import benchtest  # noqa: F401  (puts the repository on sys.path)

from bench import netlock, proxy, report


class Upstream:
    """A fake model API: /v1/messages answers a server-sent event stream with usage, /v1/count a JSON body with usage,
    /v1/limited a 429. It records the headers it got."""

    def __init__(self):
        self.seen = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "body": body})
                if self.path.startswith("/v1/limited"):
                    data = b'{"type":"error","error":{"type":"rate_limit_error"}}'
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path.startswith("/v1/count"):
                    data = json.dumps({"usage": {"input_tokens": 7, "output_tokens": 3}}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                events = [
                    {"type": "message_start", "message": {"usage": {"input_tokens": 2, "cache_creation_input_tokens": 100,
                                                                    "cache_read_input_tokens": 900, "output_tokens": 1}}},
                    {"type": "content_block_delta", "delta": {"text": "ok"}},
                    {"type": "message_delta", "usage": {"output_tokens": 12}},
                    {"type": "message_stop"}]
                data = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Proxy(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="bench-proxy-")
        self.up = Upstream()
        self.proxies = proxy.start(("worker", "review"), self.tmp, upstream=self.up.url)

    def tearDown(self):
        for p in self.proxies.values():
            p.close()
        self.up.close()

    def post(self, role, path, headers=None):
        req = urllib.request.Request(self.proxies[role].url + path, data=b'{"model":"m","secret":"body"}',
                                     headers={"x-api-key": "sk-secret", "Authorization": "Bearer tok",
                                              **(headers or {})}, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def log(self, role):
        with open(os.path.join(self.tmp, f"proxy-{role}.jsonl")) as f:
            return [json.loads(line) for line in f]

    def test_it_passes_requests_through_and_logs_only_path_status_and_usage(self):
        status, body = self.post("worker", "/v1/messages?beta=true")
        self.assertEqual(status, 200)
        self.assertIn(b"message_delta", body)
        got = self.up.seen[0]
        self.assertEqual(got["headers"]["x-api-key"], "sk-secret")  # the child's sign-in passes unchanged
        self.assertEqual(got["body"], b'{"model":"m","secret":"body"}')
        self.assertEqual(got["path"], "/v1/messages?beta=true")
        entry = self.log("worker")
        self.assertEqual(entry, [{"role": "worker", "path": "/v1/messages", "status": 200,
                                  "usage": {"input": 2, "output": 12, "cache_write": 100, "cache_read": 900}}])
        with open(os.path.join(self.tmp, "proxy-worker.jsonl")) as f:
            text = f.read()
        for secret in ("sk-secret", "tok", "body", "beta"):
            self.assertNotIn(secret, text)

    def test_one_port_per_role_and_a_json_body_and_an_error_are_logged(self):
        self.post("review", "/v1/count")
        status, _ = self.post("review", "/v1/limited")
        self.assertEqual(status, 429)
        self.assertEqual(self.log("review"), [
            {"role": "review", "path": "/v1/count", "status": 200, "usage": {"input": 7, "output": 3, "cache_write": 0,
                                                                             "cache_read": 0}},
            {"role": "review", "path": "/v1/limited", "status": 429}])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "proxy-worker.jsonl")))
        self.assertNotEqual(self.proxies["worker"].port, self.proxies["review"].port)
        summed = proxy.usage(self.tmp, ("worker", "review"))
        self.assertEqual(summed["review"]["requests"], 2)
        self.assertEqual(summed["review"]["errors"], 1)
        self.assertEqual(summed["review"]["statuses"], {"200": 1, "429": 1})

    def test_it_refuses_the_agent_proxy_websocket(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.proxies["worker"].port)
        conn.request("GET", "/v1/code/agent-proxy/ws", headers={"Upgrade": "websocket", "Connection": "Upgrade"})
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()
        status, _ = self.post("worker", "/v1/code/agent-proxy/ws")
        self.assertEqual(status, 403)
        self.assertEqual(self.up.seen, [])
        self.assertEqual([e["status"] for e in self.log("worker")], [403, 403])


class Relay(unittest.TestCase):
    def test_the_relay_joins_a_port_to_the_proxys_unix_socket(self):
        import tempfile
        tmp = tempfile.mkdtemp(prefix="br-", dir="/tmp")
        up = Upstream()
        proxies = proxy.start(("worker",), tmp, upstream=up.url, unix=True)
        try:
            port = proxy.free_port()
            listener = netlock.listen(port, proxies["worker"].sock)
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/messages", data=b"{}", method="POST")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
            listener.close()
            with open(os.path.join(tmp, "proxy-worker.jsonl")) as f:
                self.assertEqual(json.loads(f.readline())["usage"]["output"], 12)
        finally:
            proxies["worker"].close()
            up.close()

    def test_wrap_runs_the_command_under_unshare_with_its_relays(self):
        argv = netlock.wrap(["claude", "-p"], {8901: "/run/w.sock"})
        self.assertEqual(argv[:2], ["unshare", "-n"])
        self.assertEqual(argv[-4:], ["8901=/run/w.sock", "--", "claude", "-p"])

    @unittest.skipUnless(netlock.available(), "needs Linux, root and unshare")
    def test_inside_the_lock_only_the_relay_answers(self):
        import subprocess
        import sys
        code = ("import socket,sys\ns=socket.socket();s.settimeout(3)\n"
                "try:\n s.connect(('1.1.1.1',443));print('open')\nexcept OSError:\n print('closed')")
        done = subprocess.run(netlock.wrap([sys.executable, "-c", code], {}), capture_output=True, text=True)
        self.assertEqual(done.stdout.strip(), "closed")


def result(arm, sid, n, alone=True, stop=True, merged=True, acts=(), tainted=False, again=False, locked=True,
           project="calc", cost=0.5):
    r = {"run": f"{project}.{sid}.{arm}.{n}", "arm": arm, "situation": sid, "set": "fixture", "project": project,
         "merged": merged, "right_stop": stop, "person_acts": list(acts), "tainted": tainted, "again": again,
         "locked": locked, "minutes": 2.0, "cost_usd": cost,
         "worked": [{"code": "TICKET_LINT", "cost_usd": 0.1, "turns": 3}, {"code": "IMPLEMENT", "cost_usd": cost,
                                                                          "turns": 10}],
         "usage": {"worker": {"input": 10, "output": 5, "cache_write": 1, "cache_read": 100, "requests": 4}}}
    if merged:
        r["right_merged"] = alone
    return r


def facts_for(*sids, project="calc", half="work"):
    import datetime
    return {("fixture", project, s): {"kind": "crash", "half": half, "closed": datetime.date(2026, 12, 1),
                                      "admitted": True} for s in sids}


class Report(unittest.TestCase):
    def test_the_numbers_per_arm_on_situations_every_arm_has(self):
        results = [result("a", "s1", 1), result("a", "s1", 2), result("a", "s1", 3, alone=False, stop=False),
                   result("a", "s2", 1, merged=False, stop=False),
                   result("a", "s3", 1, acts=["APPROVE_CONTRACT", "MERGE_BY_PERSON"]),
                   result("b", "s1", 1, alone=False), result("b", "s2", 1), result("b", "s3", 1),
                   result("b", "s4", 1)]  # s4 has no run of arm a: left out
        facts = facts_for("s1", "s2", "s3", "s4")
        rep = report.build(results, facts, arms=["a", "b"], seed=3, resamples=200)
        sec = rep["sections"]["locked"]
        self.assertEqual(sec["situations"], 3)
        a = sec["arms"]["a"]
        # s1: 2 of 3 alone, s2: 0, s3: 0 (a person stood in) -> (2/3) / 3
        self.assertAlmostEqual(a["solved_alone"], (2 / 3) / 3)
        self.assertAlmostEqual(a["solved_at_stop"], (2 / 3 + 0 + 1) / 3)
        self.assertEqual(a["stand_in"], {"count": 1, "runs": 5})
        self.assertEqual(a["wrong_merges"]["count"], 1)
        self.assertEqual(a["wrong_merges"]["of"], 3)
        self.assertEqual(a["person"]["acts"], {"APPROVE_CONTRACT": 1, "MERGE_BY_PERSON": 1})
        self.assertEqual(a["unsteady"], {"share": 1 / 3, "count": 1, "of": 3})
        self.assertEqual((a["situations"], a["runs"]), (3, 5))
        self.assertEqual(rep["left_out"]["not on every arm"], 1)
        self.assertAlmostEqual(a["cost"]["worker"]["cost_usd"], 0.5)
        self.assertAlmostEqual(a["cost"]["contract"]["cost_usd"], 0.1)
        self.assertEqual(a["cost"]["worker"]["cache_read"], 100)
        text = report.render(rep)
        self.assertIn("seed 3", text)
        self.assertIn("| a | 22%", text)

    def test_tainted_again_and_unlocked_runs_are_left_out_or_apart_and_counted(self):
        results = [result("a", "s1", 1), result("a", "s1", 2, tainted=True), result("a", "s1", 3, again=True),
                   result("b", "s1", 1), result("a", "s2", 1, locked=False), result("b", "s2", 1, locked=False)]
        rep = report.build(results, facts_for("s1", "s2"), arms=["a", "b"], resamples=50)
        self.assertEqual(rep["left_out"]["tainted"], 1)
        self.assertEqual(rep["left_out"]["again"], 1)
        self.assertEqual(rep["sections"]["locked"]["arms"]["a"]["runs"], 1)
        self.assertEqual(rep["sections"]["unlocked"]["situations"], 1)
        self.assertIn("Unlocked runs", report.render(rep))

    def test_unadmitted_held_out_and_before_cutoff_are_left_out(self):
        import datetime
        facts = facts_for("s1", "s2", "s3")
        facts[("fixture", "calc", "s2")]["admitted"] = False
        facts[("fixture", "calc", "s3")]["half"] = "held"
        results = [result("a", s, 1) for s in ("s1", "s2", "s3")]
        for r in results:
            r["models"] = ["m-new"]
        rep = report.build(results, facts, arms=["a"], resamples=10)
        self.assertEqual(rep["left_out"]["not admitted"], 1)
        self.assertEqual(rep["left_out"]["held out"], 1)
        self.assertEqual(rep["sections"]["locked"]["situations"], 1)
        rep = report.build(results, facts, arms=["a"], cutoffs={"m-new": datetime.date(2027, 1, 1)}, resamples=10)
        self.assertEqual(rep["left_out"]["before cutoff"], 1)
        self.assertNotIn("locked", rep["sections"])

    def test_the_ranges_come_again_from_the_same_seed_and_resample_within_each_project(self):
        results = []
        facts = {}
        for project in ("p1", "p2"):
            for i in range(6):
                sid = f"s{i}"
                facts.update(facts_for(sid, project=project))
                for n in range(3):
                    results.append(result("a", sid, n, project=project, alone=(i + n) % 2 == 0))
        one = report.build(results, facts, arms=["a"], seed=11, resamples=300)
        two = report.build(results, facts, arms=["a"], seed=11, resamples=300)
        other = report.build(results, facts, arms=["a"], seed=12, resamples=300)
        r1 = one["sections"]["locked"]["arms"]["a"]["solved_alone_range"]
        self.assertEqual(r1, two["sections"]["locked"]["arms"]["a"]["solved_alone_range"])
        self.assertNotEqual(r1, other["sections"]["locked"]["arms"]["a"]["solved_alone_range"])
        low, high = r1
        self.assertLessEqual(low, one["sections"]["locked"]["arms"]["a"]["solved_alone"])
        self.assertGreaterEqual(high, one["sections"]["locked"]["arms"]["a"]["solved_alone"])
        # within each project: a project whose situations all agree gives no spread
        flat = [result("a", f"s{i}", 0, project="p1") for i in range(5)]
        rep = report.build(flat, {k: v for i in range(5) for k, v in facts_for(f"s{i}", project="p1").items()},
                           arms=["a"], resamples=100)
        self.assertEqual(rep["sections"]["locked"]["arms"]["a"]["solved_alone_range"], (1.0, 1.0))


class Network(benchtest.BenchTest):
    """A run through the proxies: each role's calls are counted on its own port, and a run that is not locked says so."""

    def setUp(self):
        super().setUp()
        self.up = Upstream()
        self.write_config(upstream=self.up.url)

    def tearDown(self):
        self.up.close()
        super().tearDown()

    def fix(self):
        from bench import sealed
        s = self.situation()
        sealed.build(self.store, s)
        return sealed.fix_diff(self.store, s)

    def test_each_role_is_counted_on_its_own_port_and_an_unlocked_run_is_marked(self):
        plan = self.plan(work=[{"patch": self.fix(), "request": "/v1/messages"}],
                         review=[{"summary": "Read it.", "findings": [], "request": "/v1/count"}])
        res = self.run_fake(plan=plan).result
        self.assertEqual((res["end"], res["right_merged"]), ("MERGED", True))
        self.assertEqual(res["usage"]["worker"]["requests"], 1)
        self.assertEqual(res["usage"]["worker"]["output"], 12)
        self.assertEqual(res["usage"]["review"]["requests"], 1)
        self.assertEqual(res["usage"]["review"]["input"], 7)
        self.assertNotIn("consult", res["usage"])
        self.assertEqual(res["locked"], netlock.available())
        self.assertEqual([s["path"] for s in self.up.seen], ["/v1/messages", "/v1/count"])

    def test_a_run_whose_last_call_was_rate_limited_is_set_aside_and_runs_again(self):
        limited = self.plan(plain={"patch": self.fix(), "request": "/v1/limited", "say": "NOT DONE: rate limited"})
        r = self.run_fake(arm="fake-plain", plan=limited)
        self.assertEqual((r.result["end"], r.result["again"]), ("AGAIN", True))
        self.assertIn("429", r.result["detail"])
        r = self.run_fake(arm="fake-plain", plan=self.plan(plain={"patch": self.fix()}))
        self.assertEqual((r.result["end"], r.result["again"]), ("DONE", False))
        self.assertTrue(os.path.exists(r.path + ".again-1"))


class ReportCommand(benchtest.BenchTest):
    def test_bench_report_reads_the_stores_results_and_states_its_seed(self):
        from bench import tomlw
        fixture_results = [result("a", "calc-01", 1), result("a", "calc-01", 2, tainted=True),
                           result("a", "calc-02", 1, alone=False, stop=False), result("b", "calc-01", 1),
                           result("b", "calc-02", 1)]
        for r in fixture_results:
            folder = os.path.join(self.store, "runs", r["run"])
            os.makedirs(folder)
            with open(os.path.join(folder, "run.toml"), "w") as f:
                f.write(tomlw.dumps({"id": r["run"], "project": self.project_file}))
            with open(os.path.join(folder, "result.toml"), "w") as f:
                f.write(tomlw.dumps(r))
        out = self.bench("report", "--any-situation", "--seed", "5", "--resamples", "100", "--json")
        rep = json.loads(out)
        self.assertEqual(rep["seed"], 5)
        self.assertEqual(rep["left_out"]["tainted"], 1)
        self.assertEqual(rep["sections"]["locked"]["situations"], 2)
        self.assertEqual(rep["sections"]["locked"]["arms"]["a"]["solved_alone"], 0.5)
        self.assertEqual(out, self.bench("report", "--any-situation", "--seed", "5", "--resamples", "100", "--json"))
        self.assertIn("seed 5", self.bench("report", "--any-situation", "--seed", "5", "--resamples", "100"))
        # without --any-situation the fixture's situations, never admitted, are left out and counted
        rep = json.loads(self.bench("report", "--json"))
        self.assertEqual(rep["left_out"]["not admitted"], 4)
