"""Driving the real product: `[product]` says how it is started and each `[[surfaces]]` entry is one way users reach
it, with the script that drives it. Ship and CI start the product, drive each surface the change reaches, stop it,
and keep what the checks saw (rail docs product).

The fixture in tests/product is a calculator with two surfaces: an HTTP server and a command line, both in Python's
standard library. A ticket plants a fault by changing one line."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import FAKE, RailTest, engine

PRODUCT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "product")
BASE = f"""\
[[projects]]
name = "server"
paths = ["server/**"]

[[projects]]
name = "cli"
paths = ["cli/**"]

[[projects]]
name = "docs"
paths = ["docs/**"]

[commands]
timeout_secs = 60

[review]
command = "python3 {FAKE}"

[consult]
command = "python3 {FAKE} --consult"
"""
STARTS = """
[product]
start = "python3 server/start.py"
ready = "python3 server/ready.py"
seed = "python3 server/seed.py"
stop = "python3 server/stop.py"
ready_secs = 20
"""
SURFACES = """
[[surfaces]]
name = "api"
kind = "api"
projects = ["server"]
check = "server/checks/api.py"

[[surfaces]]
name = "cli"
kind = "cli"
projects = ["cli"]
check = "cli/checks/cli.py"
"""
CONFIG = BASE + STARTS + SURFACES
CLEAN = {"summary": "Clean.", "findings": []}


def card(title, scope, check="test -f README.md"):
    scopes = ", ".join(f'"{s}"' for s in scope)
    return "\n".join(["+++", f'title = "{title}"', 'tier = "AUTO"', f"scope_paths = [{scopes}]", "+++", "",
                      "## Why", "The calculator needs it.", "", "## Done Contract", f"- Check: `{check}`", ""])


def steps(answer):
    """The steps of the product step in an answer: (name, 'pass', 'fail' or how it did not run, detail)."""
    return [(s["step"], s["result"] if s["status"] == "ran" else s["status"], s.get("detail")) for s in answer["steps"]
            if s["step"].split(":")[0] == "product"]


def events(p, nn):
    with open(os.path.join(p.worktree(nn), ".rail", "journal", f"{nn}-events.jsonl")) as f:
        return [json.loads(line) for line in f if line.strip()]


def alive(pid):
    """Whether a process still runs. One that ended and that nothing has collected yet does not."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


class ProductTest(RailTest):
    def product(self, name="p", config=CONFIG, files=None):
        return self.fixture(name, config=config, tree=PRODUCT, files=files)

    def change(self, p, title, path, old, new, scope=None):
        """A ticket whose work replaces `old` by `new` in one file. Returns its id."""
        nn = p.add(card(title, scope or (path.split("/")[0] + "/**",)))["ticket"]
        p.rail("next", "--ticket", nn)
        full = os.path.join(p.worktree(nn), path)
        with open(full) as f:
            text = f.read()
        self.assertIn(old, text)
        with open(full, "w") as f:
            f.write(text.replace(old, new))
        return nn

    def run_dir(self, p, nn):
        return os.path.join(p.worktree(nn), "server", ".run")


class Config(ProductTest):
    def test_the_product_and_its_surfaces_load_and_a_driving_check_counts_as_a_test(self):
        p = self.product()
        engine()
        from rail import config
        loaded = config.load(p.root)
        self.assertEqual(loaded["product"]["ready_secs"], 20)
        self.assertEqual([(s["name"], s["kind"], s["projects"]) for s in loaded["surfaces"]],
                         [("api", "api", ["server"]), ("cli", "cli", ["cli"])])
        # Nothing is written into [tests] paths: a check's path counts for as long as its surface names it.
        self.assertEqual(loaded["tests"]["paths"], ["server/checks/api.py", "cli/checks/cli.py"])
        # A project with neither works as before: no step, and no line about one.
        q = self.product("plain", config=BASE)
        self.assertEqual(config.load(q.root)["surfaces"], [])

    def test_an_unknown_kind_or_key_is_refused(self):
        p = self.product()
        for bad, said in (
                (SURFACES.replace('kind = "cli"', 'kind = "desktop"'),
                 "config: surfaces[1].kind is 'desktop', which is no kind of surface. The kinds: web, api, cli, agent,"
                 " data, integration, mobile"),
                (SURFACES.replace('kind = "api"', 'kind = "apis"'), "(did you mean 'api'?)"),
                (SURFACES + "preview = true\n", "config: unknown key 'surfaces[1].preview'"),
                (SURFACES.replace('name = "cli"', 'name = "api"'), "config: surfaces[1] needs a name no other surface has"),
                (SURFACES.replace('check = "cli/checks/cli.py"', 'check = "/usr/bin/true"'),
                 "config: surfaces[1].check is the path of a script in the repository"),
                (SURFACES.replace('kind = "cli"\n', ""), "config: surfaces[1].kind is ''"),
                (SURFACES + '\n[product]\nurl = "http://localhost"\n', "config: unknown key 'product.url'")):
            p.write(".rail/config.toml", BASE + (STARTS if "[product]" not in bad else "") + bad)
            self.assertIn(said, p.rail("status", expect=2)["reason"]["message"], bad)


class Step(ProductTest):
    def test_a_change_that_reaches_a_surface_starts_the_product_drives_that_surface_and_stops_it(self):
        p = self.product()
        nn = self.change(p, "Say more at startup", "server/server.py", '"server: listening on"', '"server: now listening on"')
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", nn)
        self.assertEqual(steps(shipped), [("product", "pass", None),
                                          ("product:api", "pass", "1 evidence file, 1 more left on the machine")])
        self.assertEqual(shipped["state"], "merge-ready")
        # Started, seeded (the check asks who the user is), and stopped: the server is gone.
        run = self.run_dir(p, nn)
        self.assertTrue(os.path.exists(os.path.join(run, "stopped")))
        with open(os.path.join(run, "pid")) as f:
            self.assertFalse(alive(int(f.read())))
        body = p.rail("advance", nn)
        self.assertEqual(body["state"], "merged")
        message = p.git("log", "-1", "--format=%b", "main")
        self.assertIn("| product | ran, pass |\n| product:api | ran, pass: 1 evidence file, 1 more left on the machine |",
                      message)

    def test_only_the_surfaces_the_change_reaches_are_driven_and_a_change_that_reaches_none_drives_nothing(self):
        p = self.product()
        nn = self.change(p, "Name the usage", "cli/calc.py", "usage: calc.py add A B", "usage: calc.py add A B (integers)")
        self.assertEqual(steps(p.rail("advance", nn)), [("product", "pass", None), ("product:cli", "pass", "1 evidence file")])
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        # The guide is a project of its own, and no surface names it.
        other = self.change(p, "Say what it is", "docs/guide.md", "A calculator", "A small calculator")
        shipped = p.rail("advance", other)
        self.assertEqual(steps(shipped), [("product", "not_run", None)])
        self.assertEqual(shipped["state"], "merge-ready")
        self.assertFalse(os.path.exists(self.run_dir(p, other)))

    def test_a_planted_fault_fails_the_surfaces_check_counts_as_an_attempt_and_the_product_is_still_stopped(self):
        p = self.product()
        nn = self.change(p, "Round up", "server/server.py", 'os.environ.get("CALC_FAULT", "0")', 'os.environ.get("CALC_FAULT", "1")')
        failed = p.rail("advance", nn, expect=3)
        self.assertEqual(steps(failed), [("product", "pass", None),
                                         ("product:api", "fail", "exit 1; 1 evidence file, 1 more left on the machine")])
        self.assertEqual(failed["reason"]["code"], "STEP_FAILED")
        self.assertIn("GET /add?a=2&b=3: wanted {'sum': 5}, got {'sum': 6}", failed["action"]["brief"])
        self.assertIn('write one line under "## Tried"', failed["action"]["brief"])
        self.assertTrue(os.path.exists(os.path.join(self.run_dir(p, nn), "stopped")))
        event = [e for e in events(p, nn) if e.get("step") == "product:api"][-1]
        self.assertEqual((event["result"], event.get("counted", True)), ("fail", True))
        self.assertTrue(event["signature"].startswith("product:api:"))
        # With the fault taken out, the same step passes.
        path = os.path.join(p.worktree(nn), "server", "server.py")
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(text.replace('"CALC_FAULT", "1"', '"CALC_FAULT", "0"') + "# as before\n")
        p.queue_reviews(CLEAN)
        self.assertEqual(steps(p.rail("advance", nn))[-1][:2], ("product:api", "pass"))

    def test_rail_ci_drives_the_product_too(self):
        p = self.product()
        nn = self.change(p, "Say more at startup", "server/server.py", '"server: listening on"', '"server: now listening on"')
        p.queue_reviews(CLEAN)
        p.rail("advance", nn)
        branch = p.git("branch", "--list", f"{nn}-*", "--format=%(refname:short)").strip()
        ci = os.path.join(self.tmp, "ci")  # what the workflow does: a clone, the pull request's head checked out
        subprocess.run(["git", "clone", "--quiet", p.root, ci], check=True)
        subprocess.run(["git", "checkout", "--quiet", "--detach", p.git("rev-parse", branch).strip()], cwd=ci, check=True)
        kept = os.path.join(self.tmp, "evidence")  # the workflow sets it, and uploads the folder afterwards
        passed = p.rail("ci", cwd=ci, env_extra={"RAIL_BRANCH": branch, "RAIL_EVIDENCE": kept})
        self.assertEqual(passed["reason"]["code"], "CI_PASS")
        self.assertEqual(steps(passed), [("product", "pass", None),
                                         ("product:api", "pass", "1 evidence file, 1 more left on the machine")])
        self.assertEqual(sorted(os.listdir(os.path.join(kept, "api"))), ["requests.txt", "screen.png"])
        with open(os.path.join(kept, "start.log")) as f:
            self.assertIn("server: now listening on", f.read())  # what the product printed, for the upload
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=ci, capture_output=True, text=True).stdout, "")

        # With the planted fault switched on for the run, the same check fails there.
        failed = p.rail("ci", cwd=ci, expect=3, env_extra={"RAIL_BRANCH": branch, "RAIL_EVIDENCE": kept, "CALC_FAULT": "1"})
        self.assertEqual(failed["reason"]["code"], "CI_FAIL")
        self.assertEqual(steps(failed)[-1][:2], ("product:api", "fail"))
        self.assertIn("Failed at 'product:api'", failed["action"]["brief"])


class Starting(ProductTest):
    QUICK = CONFIG.replace("ready_secs = 20", "ready_secs = 2")

    def test_a_product_that_only_the_branch_fails_to_start_is_the_tickets_failure(self):
        p = self.product(config=self.QUICK)
        nn = self.change(p, "Listen elsewhere", "server/server.py", 'if __name__ == "__main__":',
                         'if __name__ == "__main__":\n    raise SystemExit("server: no port to listen on")')
        failed = p.rail("advance", nn, expect=3)
        self.assertEqual(steps(failed), [("product", "fail", "ready: not ready after 2s"), ("product:api", "not_run", None)])
        brief = failed["action"]["brief"]
        self.assertIn("What start printed:", brief)
        self.assertIn("server: no port to listen on", brief)  # the product's own output, from the file start wrote to
        event = [e for e in events(p, nn) if e.get("step") == "product"][-1]
        self.assertEqual((event["result"], event.get("counted", True)), ("fail", True))
        self.assertTrue(os.path.exists(os.path.join(self.run_dir(p, nn), "stopped")))  # stop runs after a failed start

    def test_a_product_that_does_not_start_on_the_base_either_costs_no_attempt_and_gets_a_fix_ticket(self):
        with open(os.path.join(PRODUCT, "server", "server.py")) as f:
            broken = f.read().replace('if __name__ == "__main__":',
                                      'if __name__ == "__main__":\n    raise SystemExit("server: no port to listen on")')
        p = self.product(config=self.QUICK, files={"server/server.py": broken})
        nn = self.change(p, "Say more at startup", "server/server.py", '"server: listening on"', '"server: now listening on"')
        failed = p.rail("advance", nn, expect=3)
        self.assertEqual(steps(failed)[0], ("product", "fail", "red base"))
        self.assertIn("the product does not start on the base branch either, so this attempt doesn't count", failed["action"]["brief"])
        event = [e for e in events(p, nn) if e.get("step") == "product"][-1]
        self.assertIs(event["counted"], False)
        fix = p.rail("next")
        self.assertEqual(fix["ticket"], str(int(nn) + 1))
        text = p.git("show", f"{p.git('branch', '--list', fix['ticket'] + '-*', '--format=%(refname:short)').strip()}"
                             f":.rail/tickets/{fix['ticket']}.md")
        self.assertIn("Make the product start on main again", text)
        self.assertIn("The product does not start on main at", text)
        self.assertIn("server: no port to listen on", text)

    def test_a_start_the_shell_cannot_run_checked_nothing(self):
        p = self.product(config=CONFIG.replace('start = "python3 server/start.py"', 'start = "no-such-launcher --up"'))
        nn = self.change(p, "Say more at startup", "server/server.py", '"server: listening on"', '"server: now listening on"')
        failed = p.rail("advance", nn, expect=3)
        self.assertEqual(steps(failed)[0][:2], ("product", "could_not_run"))
        event = [e for e in events(p, nn) if e.get("step") == "product"][-1]
        self.assertIs(event["counted"], False)


class Evidence(ProductTest):
    TOOL = '\n[tools.accounts]\nuse = "The test accounts the driving checks sign in with"\nenv = ["RAIL_TEST_USER"]\n'

    def test_text_is_kept_in_the_journal_with_secrets_named_and_a_binary_file_is_not(self):
        p = self.product(config=CONFIG + self.TOOL)
        env = {"RAIL_TEST_USER": "test-user"}
        nn = p.add(card("Say more at startup", ("server/**",)))["ticket"]
        p.rail("next", "--ticket", nn, env_extra=env)
        wt = p.worktree(nn)
        p.write(".env", "# the keys of the test stack\nexport API_TOKEN='tok-test-0000'\nPORT=8\n", base=wt)
        with open(os.path.join(wt, "server", "server.py"), "a") as f:
            f.write("# said more\n")
        p.queue_reviews(CLEAN)
        shipped = p.rail("advance", nn, env_extra=env)
        self.assertEqual(shipped["state"], "merge-ready")
        branch = p.git("branch", "--list", f"{nn}-*", "--format=%(refname:short)").strip()
        doc = json.loads(p.git("show", f"{branch}:.rail/journal/{nn}-evidence.json"))
        patch = [e for e in events(p, nn) if e.get("event") == "shipped"][-1]["patch_id"]
        self.assertEqual(list(doc), [patch])
        api = doc[patch]["api"]
        # The value of a declared environment name and of a .env entry is replaced by its name; a short value, which
        # would match by chance, is left.
        self.assertEqual(api["files"], {"requests.txt": 'GET /whoami\n{"user": "[RAIL_TEST_USER]", "token": "[API_TOKEN]"}\n\n'
                                                        'GET /add?a=2&b=3\n{"sum": 5}\n'})
        self.assertEqual(api["left"], ["screen.png"])
        self.assertNotIn("screen.png", p.git("ls-tree", "-r", "--name-only", branch))
        # What was not committed stays on the machine, in the local cache.
        common = p.git("rev-parse", "--git-common-dir").strip()
        self.assertTrue(os.path.exists(os.path.join(p.root, common, "rail", "cache", "evidence", nn, "api", "screen.png")))
        # The reviewer's brief holds the text.
        brief = p.briefs()[-1]["brief"]
        self.assertIn("## What the product did", brief)
        self.assertIn('`api` / `requests.txt`:\n```\nGET /whoami\n{"user": "[RAIL_TEST_USER]", "token": "[API_TOKEN]"}', brief)
        self.assertIn("- `api` / `screen.png`: not text, so it was not kept in the journal", brief)

    def test_a_file_and_a_surface_are_cut_at_their_caps(self):
        engine()
        from rail import product
        folder = os.path.join(self.tmp, "evidence")
        os.makedirs(os.path.join(folder, "pages"))
        for name, size in (("a.txt", 100), ("b.txt", product.FILE_BYTES + 5000), ("pages/c.txt", product.FILE_BYTES),
                           ("d.txt", product.FILE_BYTES), ("e.txt", product.FILE_BYTES), ("f.txt", 5000)):
            with open(os.path.join(folder, name), "w") as f:
                f.write("x" * size)
        found = product.collect(folder, {})
        sizes = {name: len(text) for name, text in found["files"].items()}
        self.assertEqual(list(sizes), ["a.txt", "b.txt", "d.txt", "e.txt", "f.txt", "pages/c.txt"])
        self.assertEqual((sizes["a.txt"], sizes["d.txt"], sizes["f.txt"]), (100, product.FILE_BYTES, 5000))
        self.assertEqual(sizes["b.txt"], product.FILE_BYTES + len(product.CUT))  # a file, at its cap
        self.assertTrue(found["files"]["b.txt"].endswith("x" + product.CUT))
        # The last file fills what the surface has left, and no more.
        self.assertEqual(found["cut"], ["b.txt", "pages/c.txt"])
        self.assertLess(sizes["pages/c.txt"], product.FILE_BYTES)
        self.assertEqual(sum(sizes.values()), product.SURFACE_BYTES + len(product.CUT))


def bar(answer):
    """The lines of a doctor answer about the product: {name: (result, kind)}."""
    return {x["step"]: (x.get("result"), x.get("kind")) for x in answer["steps"]
            if x["step"].split()[0] in ("product", "surface", "surfaces") or x["step"].startswith("product:")}


class Bar(ProductTest):
    def test_doctor_names_each_missing_piece_and_whose_act_it_is(self):
        p = self.product()
        self.assertEqual(bar(p.rail("doctor", expect=None)), {
            "product start": ("pass", None), "product seed": ("pass", None),
            "surface api": ("pass", None), "surface cli": ("pass", None)})

        # Surfaces and nothing that starts the product or seeds it; one check that is not there, one that cannot run.
        os.chmod(p.path("cli", "checks", "cli.py"), 0o644)
        p.write(".rail/config.toml", BASE + SURFACES.replace("server/checks/api.py", "server/checks/gone.py"))
        said = p.rail("doctor", expect=None)
        self.assertEqual(bar(said), {
            "product start": ("fail", "ticket"), "product seed": ("fail", "ticket"),
            "surface api": ("fail", "ticket"), "surface cli": ("fail", "ticket")})
        lines = {x["step"]: x["detail"] for x in said["steps"]}
        self.assertIn("[product] start and ready is not set, so nothing starts the product before api is driven", lines["product start"])
        self.assertIn("api needs a test identity to sign in with", lines["product seed"])
        self.assertIn("its check server/checks/gone.py is not a tracked file", lines["surface api"])
        self.assertIn("its check cli/checks/cli.py is not executable", lines["surface cli"])
        # A piece the machine can build is a ticket, not a wait for a person.
        self.assertIn("The machine can build these, each as one ticket (rail add):\n- product start:", said["action"]["brief"])
        self.assertNotIn("- product start", said["action"]["brief"].split("The machine can build these")[0])

        # A command line alone needs nothing started and nobody signed in.
        os.chmod(p.path("cli", "checks", "cli.py"), 0o755)
        p.write(".rail/config.toml", BASE + SURFACES.split("[[surfaces]]")[2].join(["\n[[surfaces]]", ""]))
        self.assertEqual(bar(p.rail("doctor", expect=None)), {"product start": ("pass", None), "surface cli": ("pass", None)})

        # No surface at all is one line.
        p.write(".rail/config.toml", BASE)
        said = p.rail("doctor", expect=None)
        self.assertEqual(bar(said), {"surfaces": ("fail", "ticket")})
        self.assertIn("the config names no way users reach the product", said["action"]["brief"])

    def test_a_mobile_surface_on_a_machine_that_cannot_run_an_emulator_is_a_grant(self):
        p = self.product(config=BASE + STARTS + SURFACES.replace('kind = "cli"', 'kind = "mobile"'))
        engine()
        from rail import product
        from rail.project import Project
        project = Project(p.root)
        names = set(p.git("ls-files").split())
        found = {name: (passed, kind) for name, passed, _, kind in
                 product.bar(project, names, machine={"kvm": False, "mac": False})}
        self.assertEqual(found["product machine"], (False, "grant"))
        for machine in ({"kvm": True, "mac": False}, {"kvm": False, "mac": True}):
            found = {name: (passed, kind) for name, passed, _, kind in product.bar(project, names, machine=machine)}
            self.assertEqual(found["product machine"], (True, None))
        # A grant is a person's act, so doctor's brief lists it under what to fix.
        said = p.rail("doctor", expect=None)
        if bar(said)["product machine"] == ("fail", "grant"):
            self.assertIn("- product machine: a mobile surface needs a machine",
                          said["action"]["brief"].split("The machine can build these")[0])

    def test_doctor_product_runs_each_command_once_on_the_base_branch(self):
        p = self.product()
        found = {x["step"]: (x.get("result"), x["detail"]) for x in p.rail("doctor", "--product", expect=None)["steps"]}
        self.assertEqual(found["product"][0], "pass")
        self.assertIn("start, ready and seed passed on the base branch", found["product"][1])
        self.assertEqual(found["product:api"], ("pass", "1 evidence file, 1 more left on the machine"))
        self.assertEqual(found["product:cli"], ("pass", "1 evidence file"))
        self.assertEqual(found["product stop"], ("pass", "the product was stopped"))
        self.assertFalse(os.path.exists(p.path("server", ".run")))  # a throwaway worktree, not this checkout
        self.assertEqual(p.git("worktree", "list").count("\n"), 1)
        # Plain doctor runs none of them.
        self.assertNotIn("product stop", {x["step"] for x in p.rail("doctor", expect=None)["steps"]})
        # With the fault on, the surface's line fails and says what the check printed.
        found = {x["step"]: (x.get("result"), x["detail"])
                 for x in p.rail("doctor", "--product", expect=None, env_extra={"CALC_FAULT": "1"})["steps"]}
        self.assertEqual(found["product:cli"][0], "fail")
        self.assertIn("cli: calc.py add 2 3 printed '6', wanted '5'", found["product:cli"][1])

    def test_the_init_task_asks_for_the_product_its_surfaces_and_what_is_built_for_agents(self):
        for cloud in (False, True):
            p = self.fixture("cloud" if cloud else "local", init=False, tree=PRODUCT)
            p.git("add", "-A")
            p.git("commit", "--quiet", "-m", "start")
            p.rail("init")
            brief = p.rail("next", cloud=cloud)["action"]["brief"]
            self.assertIn("The product. When users reach what this repository holds, say in .rail/config.toml how", brief)
            self.assertIn("one [[surfaces]] entry for each way users", brief)
            self.assertIn("Ask what the product has that is built for\n   agents", brief)
            self.assertIn("that is a surface of kind\n   `agent` with its own check", brief)
            self.assertIn("file one ticket for each `ticket` line with rail add", brief)
            self.assertIn("list each `grant` line in the pull request" if cloud else "tell the person each `grant` line", brief)

    def test_the_sweep_lists_a_missing_piece_for_a_ticket_once(self):
        p = self.product(config=BASE + SURFACES + "\n[sweep]\nevery = 0\n")
        seed = card("Seed a test user", ("server/**",)).replace('tier = "AUTO"', 'tier = "AUTO"\nexternal_id = "bar#product-seed"')
        p.add(seed)  # as the init task files it: the sweep leaves a piece with an open ticket alone
        nn = self.change(p, "Say what it is", "docs/guide.md", "A calculator", "A small calculator")
        p.queue_reviews(CLEAN)
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        swept = p.rail("sweep")
        self.assertEqual(swept["reason"]["code"], "SWEEP_TICKETS")
        self.assertIn("1 pieces the machine lacks to drive the product", swept["steps"][-1]["detail"])
        with open(os.path.join(p.worktree(swept["ticket"]), ".rail", "journal", f"{swept['ticket']}-summary.md")) as f:
            section = f.read().split("## What the machine lacks to drive the product\n")[1]
        self.assertIn("- `product start`: [product] start and ready is not set", section)
        self.assertIn('Open that ticket, with `external_id = "bar#product-start"`.', section)
        self.assertIn("- `product seed`: listed by an earlier sweep, and still lacking. No ticket.", section)
        p.rail("advance", swept["ticket"])
        self.assertEqual(p.rail("advance", swept["ticket"])["state"], "merged")

        # Nobody filed the ticket. The next sweep names the piece as an old one, and has nothing to file.
        nn = self.change(p, "Say it again", "docs/guide.md", "A small calculator", "A very small calculator")
        p.queue_reviews(CLEAN)
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")
        again = p.rail("sweep")
        self.assertEqual(again["reason"]["code"], "SWEEP_EMPTY")
        with open(os.path.join(p.worktree(again["ticket"]), ".rail", "journal", f"{again['ticket']}-summary.md")) as f:
            section = f.read().split("## What the machine lacks to drive the product\n")[1]
        self.assertEqual(section.strip().splitlines(), [
            "- `product start`: listed by an earlier sweep, and still lacking. No ticket.",
            "- `product seed`: listed by an earlier sweep, and still lacking. No ticket."])



class Stats(ProductTest):
    GUIDE = '\n[[surfaces]]\nname = "guide"\nkind = "data"\nprojects = ["docs"]\ncheck = "docs/checks/guide.py"\n'

    def test_stats_counts_each_surfaces_driving_check_and_splits_the_outcomes_by_surface(self):
        p = self.product(config=CONFIG + self.GUIDE)
        for n in range(1, 6):  # five tickets that reach the server and the command line
            nn = p.add(card(f"Say more, part {n}", ("server/**", "cli/**")))["ticket"]
            p.rail("next", "--ticket", nn)
            for path in ("server/server.py", "cli/calc.py"):
                with open(os.path.join(p.worktree(nn), path), "a") as f:
                    f.write(f"# part {n}\n")
            if n == 1:  # one ship with the fault switched on: the server's check fails, and nothing before it did
                failed = p.rail("advance", nn, expect=3, env_extra={"CALC_FAULT": "1"})
                self.assertEqual(steps(failed)[-2][:2], ("product:api", "fail"))
            p.queue_reviews(CLEAN)
            p.rail("advance", nn)
            self.assertEqual(p.rail("advance", nn)["state"], "merged")
        nn = self.change(p, "Say what it is", "docs/guide.md", "A calculator", "A small calculator")
        p.queue_reviews(CLEAN)
        p.rail("advance", nn)
        self.assertEqual(p.rail("advance", nn)["state"], "merged")

        out = p.rail("stats")["stats"]
        self.assertEqual(out["driving"], {
            "api": {"tickets": 5, "runs": 6, "failed": 1, "share": 0.167},
            "cli": {"tickets": 5, "runs": 5, "failed": 0, "share": 0.0},
            "guide": {"tickets": 1, "runs": 1, "failed": 0, "share": 0.0}})
        # Two surfaces with five tickets each, and the small one summed into `other`.
        self.assertEqual({name: row["merged"] for name, row in out["outcomes"]["by_surface"].items()},
                         {"api": 5, "cli": 5, "other": 1})
        text = p.rail("stats", raw=True).stdout
        self.assertIn("BY SURFACE", text)
        self.assertIn("DRIVING CHECKS", text)
        self.assertIn("A driving check runs after verify, every Check: line and the sensors passed", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
