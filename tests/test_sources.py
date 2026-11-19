"""Sources: a named prompt that reads one signal and files tickets through rail add, never edits."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import RailTest, ticket

PROMPT = "Each failed run is a ticket when its test fails on the base branch too."


def source(fetch, max_open=2, prompt=PROMPT):
    return f"+++\nfetch = '{fetch}'\nmax_open = {max_open}\n+++\n\n{prompt}\n"


def keyed(key, title="Fix add", scope=("src/**",)):
    return ticket(title=title, scope=scope, front=(f'external_id = "{key}"',))


class Source(RailTest):
    def test_a_fetch_that_prints_nothing_starts_no_agent_task(self):
        p = self.fixture()
        p.write(".rail/sources/ci.md", source("true"))
        quiet = p.rail("source", "ci")
        self.assertEqual((quiet["reason"]["code"], quiet["owner"], quiet["action"]["kind"]),
                         ("SOURCE_EMPTY", "none", "rest"))

    def test_a_source_hands_the_agent_its_prompt_and_signal_and_caps_what_it_files(self):
        p = self.fixture()
        marker = os.path.join(self.tmp, "fetched")
        p.write(".rail/sources/ci.md", source(f"echo once >> {marker}; printf \"run 7 failed: test_add on $RAIL_BASE\""))
        task = p.rail("source", "ci")
        self.assertEqual((task["reason"]["code"], task["owner"], task["action"]["kind"], task["room"]),
                         ("SOURCE", "agent", "agent_task", 2))
        brief = task["action"]["brief"]
        for text in (PROMPT, "run 7 failed: test_add on refs/heads/main", "at most 2 tickets", '"ci#KEY"',
                     "change no file in the repository", "rail add FILE", "the same problem found on a later run gets"
                     " the same key", "file none and say so", "  (none)"):
            self.assertIn(text, brief)

        self.assertEqual(p.add(keyed("ci#add-sign"))["ticket"], "1")
        again = p.rail("source", "ci")["action"]["brief"]
        self.assertIn("  - ci#add-sign (ticket 1, accepted)", again)
        self.assertIn("at most 1 tickets", again)
        dup = p.add(keyed("ci#add-sign"), expect=2)
        self.assertEqual(dup["reason"]["code"], "SOURCE_DUPLICATE")
        self.assertIn("ticket 1 with external_id ci#add-sign is open already", dup["reason"]["message"])
        p.add(keyed("ci#status", title="Add a status code", scope=("api/**",)))
        full = p.add(keyed("ci#third", title="Third", scope=("docs/**",)), expect=2)
        self.assertEqual(full["reason"]["code"], "SOURCE_FULL")
        capped = p.rail("source", "ci")
        self.assertEqual((capped["reason"]["code"], capped["owner"], capped["steps"]), ("SOURCE_FULL", "none", []))
        with open(marker) as f:
            self.assertEqual(f.read().count("once"), 2)  # at the cap, fetch didn't run

        listing = p.rail("source")
        self.assertIn({"name": "ci", "open": 2, "max_open": 2}, listing["sources"])
        self.assertIn({"name": "weekly-review", "open": 0, "max_open": 3}, listing["sources"])  # rail init's seed
        self.assertIn("ci: 2/2 open", p.rail("source", raw=True).stdout)

        # A ticket that belongs to no source keeps what rail add always did: a repeated external_id is taken.
        for key in ("PROJ-7", "PROJ-7", "nosource#x", "nosource#x"):
            p.add(keyed(key, title="Docs", scope=("docs/**",)))

    def test_a_long_signal_keeps_its_tail_and_a_failed_fetch_files_nothing(self):
        p = self.fixture()
        p.write(".rail/sources/logs.md", source("python3 -c \"print(\\\"x\\\" * 25000 + \\\"THE END\\\")\""))
        brief = p.rail("source", "logs")["action"]["brief"]
        self.assertIn("It was cut: these are its last 20,000 characters.", brief)
        self.assertIn("THE END", brief)
        self.assertLess(brief.count("x"), 20100)

        p.write(".rail/sources/broken.md", source("echo no token; exit 4"))
        failed = p.rail("source", "broken", expect=3)
        self.assertEqual((failed["reason"]["code"], failed["owner"], failed["action"]["kind"]),
                         ("SOURCE_FETCH_FAILED", "none", "rest"))
        self.assertEqual((failed["steps"][0]["step"], failed["steps"][0]["result"]), ("fetch", "fail"))
        self.assertIn("exit 4", failed["action"]["brief"])
        self.assertIn("no token", failed["action"]["brief"])
        p.write(".rail/sources/missing.md", source("no-such-tool --json"))
        self.assertEqual(p.rail("source", "missing", expect=3)["steps"][0]["status"], "could_not_run")

    def test_a_bad_source_file_or_name_is_an_error_that_names_the_file(self):
        p = self.fixture()
        for name, text, problem in (
                ("Bad_Name", source("true"), "lowercase letters, digits and hyphens"),
                ("sweep", source("true"), "the engine writes sweep# external ids itself"),
                ("red-base", source("true"), "the engine writes red-base# external ids itself"),
                ("bare", "just a prompt\n", "it must start with TOML front matter"),
                ("unknown", "+++\nfetch = 'true'\nmax = 3\n+++\nLook.\n", "unknown key 'max'"),
                ("nocap", "+++\nfetch = 'true'\n+++\nLook.\n", "max_open is missing"),
                ("noprompt", "+++\nfetch = 'true'\nmax_open = 1\n+++\n", "the prompt is empty")):
            p.write(f".rail/sources/{name}.md", text)
            failed = p.rail("source", name, expect=2)
            self.assertIn(f".rail/sources/{name}.md: ", failed["reason"]["message"])
            self.assertIn(problem, failed["reason"]["message"])
            os.remove(p.path(".rail", "sources", f"{name}.md"))
        self.assertEqual(p.rail("source", "nothing", expect=2)["reason"]["code"], "NO_SOURCE")
        p.write(".rail/sources/unknown.md", "+++\nfetch = 'true'\nmax = 3\n+++\nLook.\n")
        doctor = {s["step"]: s for s in p.rail("doctor", expect=None)["steps"]}
        self.assertEqual(doctor["sources"]["result"], "fail")
        self.assertIn(".rail/sources/unknown.md: unknown key 'max'", doctor["sources"]["detail"])

    def test_the_seed_source_reads_the_weeks_merges(self):
        p = self.fixture()
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        p.rail("advance", "1")
        brief = p.rail("source", "weekly-review")["action"]["brief"]
        for text in ("1: fix add", " src/calc.py ", "Look across them for what a review of one change cannot see",
                     "Key: the kind of problem and the main file", '"weekly-review#KEY"', "at most 3 tickets"):
            self.assertIn(text, brief)

    def test_stats_count_each_sources_tickets(self):
        p = self.fixture()
        p.write(".rail/sources/ci.md", source("true", max_open=3))
        p.add(keyed("ci#add-sign"))
        p.rail("next")
        p.fix_calc("1")
        p.rail("advance", "1")
        self.assertEqual(p.rail("advance", "1")["state"], "merged")
        p.git("revert", "--no-edit", p.git("log", "--grep=^Ticket: 1$", "--format=%H", "main").strip())
        p.add(keyed("ci#status", title="Add a status code", scope=("api/**",)))
        p.rail("drop", "2", "--reason", "not real")
        p.add(keyed("ci#docs", title="Docs", scope=("docs/**",)))
        p.add(keyed("PROJ-7", title="Other", scope=("docs/**",)))
        stats = p.rail("stats")["stats"]
        self.assertEqual(stats["sources"], {"ci": {"filed": 3, "merged": 1, "reverted": 1, "dropped": 1, "open": 1}})
        self.assertRegex(p.rail("stats", raw=True).stdout, r"\nSOURCES +filed +merged +reverted +dropped +open\n"
                                                           r"ci +3 +1 +1 +1 +1")
