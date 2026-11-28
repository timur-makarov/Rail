"""What Rail tells an agent to read, the engine puts in front of it: no brief points at a docs page or a skill.

Each step's brief is built on a fixture and checked for a pointer (`rail docs PAGE`, a skill named as something to
use, a path to a guide or a docs page), and for the text the engine inlined in its place. The texts an agent gets
with no engine builder (AGENTS.md, the skills, the reviewer's prompt, the consult prompt) and the engine's own
string literals are checked the same way. A mention that is not an instruction needs an entry in ALLOWED, with
the reason.
"""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import CONFIG, Fixture, RailTest, ticket
from test_guides import BLOCKING, PAGES, guides, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from rail import docs  # noqa: E402
from rail.init import include  # noqa: E402

POINTERS = [
    r"rail docs\b",
    r"\bskills?\b",
    r"\brail-(build|debug|findings|conflict|blast-radius|slice|verify|grill|tool)\b",
    r"\.claude/skills/",
    r"\.rail/engine/(docs|guides)/",
    r"\bGuide: read\b",
]

# (where, the sentence, why it is not an instruction to go and read). `where` is a brief's name, a static text's
# path, or an engine file.
ALLOWED = [
    ("seed/AGENTS.md", "How to code, test and debug is your craft and your skills.",
     "says the craft is the agent's own; it names no page or skill to read"),
    ("contract", "a split into several tickets (`rail-slice`)",
     "the page's own last paragraph says that at this step there is no next skill"),
    ("contract", "draft the ticket (`rail-grill`), split first (`rail-slice`)",
     "the options of the report a person's session gives; at this step the page says there is no next skill"),
    ("contract", "there is no next skill",
     "says the opposite of a pointer: at this step nothing else is to be read"),
    ("seed/skills/rail-blast-radius/SKILL.md", "a split into several tickets (`rail-slice`)",
     "a skill a person starts names the next skill the person may start"),
    ("seed/skills/rail-blast-radius/SKILL.md", "draft the ticket (`rail-grill`), split first (`rail-slice`)",
     "a skill a person starts names the next skill the person may start"),
    ("seed/skills/rail-blast-radius/SKILL.md", "there is no next skill", "says there is nothing more to read"),
    ("seed/skills/rail-grill/SKILL.md", "Draft the tool's ticket with `rail-tool`",
     "a skill a person starts names the next skill the person may start"),
    ("review", ".claude/skills/ (",
     "the brief's directory digest lists the project's folders; a folder's name is no instruction"),
    ("engine/rail/cli.py", "--skills", "an option of rail init, which a person types when setting a project up"),
    ("engine/rail/config.py", ".claude/skills", "the default of [init] skill_dirs: a folder's name is no instruction"),
    ("engine/rail/docs.py", None, "the `rail docs` verb and its generated pages, which are for people"),
    ("engine/rail/tools.py", "<!-- rail-tool: {name} -->",
     "the hidden mark on the issue the engine opens for a tool whose name is missing: it names no page to read"),
    ("engine/rail/init.py", None, "installs the skills; its strings are receipts for the person running init"),
]


def offending(where, body):
    """The pointer lines in `body` that ALLOWED doesn't cover."""
    allowed = [(s, why) for w, s, why in ALLOWED if w == where]
    if any(s is None for s, _ in allowed):
        return []
    bad = []
    for line in body.splitlines():
        rest = line
        for s, _ in allowed:
            rest = rest.replace(s, "")
        if any(re.search(p, rest) for p in POINTERS):
            bad.append(line.strip())
    return bad


def section(path):
    with open(os.path.join(ROOT, path.split("#")[0])) as f:
        found = docs.part(f.read(), path)
    assert found, path
    return found


class Briefs(RailTest):
    def check(self, name, brief, *inlined):
        self.assertEqual(offending(name, brief), [], f"{name} points the agent at a page:\n{brief}")
        for part in inlined:
            self.assertIn(part, brief, name)

    def test_the_work_briefs_carry_their_pages(self):
        p = self.fixture(config=guides())
        p.add(ticket())
        self.check("IMPLEMENT", p.rail("next")["action"]["brief"], text("start"))
        self.check("IMPLEMENT", p.rail("next")["action"]["brief"])
        self.check("STEP_FAILED", p.rail("advance", "1", expect=3)["action"]["brief"])
        self.check("STEP_FAILED", p.rail("advance", "1", expect=3)["action"]["brief"], text("stuck"))

    def test_the_review_briefs_and_the_findings_brief(self):
        p = self.fixture(config=guides())
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.queue_reviews({"summary": "Read it.", "findings": [BLOCKING]}, {"summary": "It holds.", "findings": []})
        self.check("ANSWER_FINDINGS", p.rail("advance", "1", expect=3)["action"]["brief"], text("findings"))
        p.rail("answer", "1", "F1", "declined", "add(-1, 1) is 0.")
        p.rail("advance", "1")
        briefs = [b["brief"] for b in p.briefs()]
        self.assertEqual(len(briefs), 2)
        for brief in briefs:
            self.check("review", brief)
        with open(os.path.join(ROOT, "engine", "reviewer.md")) as f:
            self.check("engine/reviewer.md", f.read())

    def test_the_split_and_contract_briefs(self):
        p = self.fixture(config=guides() + "\n[size]\ncap = 10\n")
        p.add(ticket())
        p.rail("next")
        p.fix_calc("1")
        p.write("src/more.py", "".join(f"x{i} = {i}\n" for i in range(12)), base=p.worktree("1"))
        self.check("SPLIT", p.rail("advance", "1")["action"]["brief"], text("split"))
        brief = os.path.join(self.tmp, "brief.txt")
        with open(brief, "w") as f:
            f.write("Customers see negative totals.\n")
        p.rail("intake", "--external-id", "PROJ-7", "--title", "Fix totals", "--brief", brief)
        self.check("contract", p.rail("next", "--ticket", "2")["action"]["brief"], text("contract"))

    def test_the_conflict_brief(self):
        a, b = self.remote_pair(config=guides())
        a.add(ticket())
        a.rail("next")
        a.fix_calc("1")
        b.git("pull", "--quiet")
        b.write("src/calc.py", "def add(a, b):\n    return b + a  # theirs\n")
        b.git("commit", "--quiet", "-am", "theirs")
        b.git("push", "--quiet", "origin", "main")
        self.check("STEP_FAILED", a.rail("advance", "1", expect=3)["action"]["brief"], text("conflict"))

    def test_the_init_task_and_the_installed_texts(self):
        p = Fixture(os.path.join(self.tmp, "fresh"), init=False)
        p.rail("init")
        self.check("INIT_TASK", p.rail("next")["action"]["brief"], text("setup"))
        with open(p.path("AGENTS.md")) as f:
            self.check("seed/AGENTS.md", f.read())
        skills = p.path(".claude", "skills")
        for name in sorted(os.listdir(skills)):
            with open(os.path.join(skills, name, "SKILL.md")) as f:
                self.check(f"seed/skills/{name}/SKILL.md", docs.part(f.read(), "SKILL.md"))  # body, not front matter
        with open(os.path.join(skills, "rail-grill", "SKILL.md")) as f:
            self.assertIn(section("engine/docs/grill.md"), f.read())

    def test_the_source_briefs(self):
        p = self.fixture()
        p.write(".rail/sources/ci.md", "+++\nfetch = 'echo run 7 failed'\nmax_open = 2\n+++\n\nEach failed run.\n")
        with open(os.path.join(ROOT, "seed", "tickets", "TEMPLATE.md")) as f:
            template = f.read().rstrip("\n")
        self.check("SOURCE", p.rail("source", "ci")["action"]["brief"], template)
        with open(os.path.join(ROOT, "seed", "sources", "weekly-review.md")) as f:
            self.check("seed/sources/weekly-review.md", f.read())
        for name in ("ci", "weekly-review"):
            os.remove(p.path(".rail", "sources", f"{name}.md"))
        self.check("SOURCES", p.rail("source")["text"], section("engine/docs/sources.md#Sources"))

    def test_the_provision_brief(self):
        log = os.path.join(self.tmp, "provisioned.log")
        p = self.fixture(config=CONFIG.replace("[commands]", f'[commands]\nprovision = "echo ran >> {log}"'))
        home = os.path.join(self.tmp, "vm-home")
        os.makedirs(home)
        told = p.rail("next", cloud=True, env_extra={"HOME": home})
        self.assertEqual(told["reason"]["code"], "PROVISION")
        self.check("PROVISION", told["action"]["brief"], section("engine/docs/cloud.md#Set up, once"))

    def test_the_consult_prompt(self):
        with open(os.path.join(ROOT, "packs", "consult", "bin", "consult")) as f:
            self.check("packs/consult/bin/consult", f.read())


class Engine(RailTest):
    def test_no_string_in_the_engine_points_at_a_page(self):
        """A backstop for briefs no fixture above builds: every string in the engine's code, docstrings aside."""
        folder = os.path.join(ROOT, "engine", "rail")
        for name in sorted(os.listdir(folder)):
            if name.endswith(".py"):
                with open(os.path.join(folder, name)) as f:
                    where = f"engine/rail/{name}"
                    self.assertEqual(offending(where, "\n".join(strings(f.read()))), [], where)

    def test_every_allowed_mention_is_still_there(self):
        """An entry whose sentence is gone is removed, so the list stays the mentions that exist."""
        for where, sentence, _ in ALLOWED:
            if "/" in where and sentence is not None:
                with open(os.path.join(ROOT, where)) as f:
                    self.assertIn(sentence, f.read(), where)


def strings(code):
    """The string literals of a module, each f-string's parts joined, docstrings left out."""
    tree = ast.parse(code)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body and \
                isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docstrings.add(id(node.body[0].value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append(node.value)
    return found
