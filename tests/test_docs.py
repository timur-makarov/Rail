"""rail docs: the framework's docs, read from the engine."""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import RailTest, engine


class Reference(RailTest):
    def test_the_config_reference_names_every_field_and_its_reader(self):
        p = self.fixture()
        engine()
        from rail import config, docs
        names = [name for name, _ in docs._fields(config.DEFAULTS)]
        self.assertEqual(sorted(set(names) - set(docs.READERS)), [])
        page = p.rail("docs", "config")["text"]
        for name in names:
            self.assertIn(f"`{name}`", page)
        self.assertIn("| `retry.budget` | `2` | next and advance", page)
        self.assertIn("## Default `review.command`\n\n```text\nclaude -p --safe-mode", page)
        self.assertNotIn("seed/", page)

    def test_the_runner_prompt_in_the_readme_is_the_one_in_the_cloud_docs(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "README.md")) as f:
            readme = f.read()
        with open(os.path.join(root, "engine", "docs", "cloud.md")) as f:
            cloud = f.read()
        start, end = "You are the Rail runner", "what each one needs."
        cut = lambda text: " ".join(text[text.index(start):text.index(end)].split())
        self.assertEqual(cut(readme), cut(cloud))

    def test_the_cli_reference_lists_every_verb(self):
        p = self.fixture()
        page = p.rail("docs", "cli")["text"]
        for verb in ("init", "add", "accept", "amend", "answer", "next", "advance", "status", "context", "drop",
                     "doctor", "ci", "consult", "docs", "stats", "sweep", "source", "adopt", "work"):
            self.assertIn(f"## rail {verb}", page)
        self.assertNotIn("## rail hook", page)

    def test_the_index_lists_topics_and_an_unknown_topic_is_a_usage_error(self):
        p = self.fixture()
        index = p.rail("docs")["text"]
        self.assertIn("- rules: Structure rules", index)
        self.assertIn("- config: Config reference", index)
        self.assertIn("Structure rules", p.rail("docs", "rules", raw=True).stdout)
        failed = p.rail("docs", "nothing", expect=2)
        self.assertIn("topics: ", failed["reason"]["message"])


class Loop(RailTest):
    def test_the_loop_ticket_and_state_pages_cover_what_an_agent_needs(self):
        p = self.fixture()
        loop = p.rail("docs", "loop")["text"]
        for text in ("rail next --json", "rail advance --json", "owner", "person_wait", "Exit codes"):
            self.assertIn(text, loop)
        tickets = p.rail("docs", "tickets")["text"]
        for text in ("rail add", "Check:", "ASSUMED", "rail amend", "rail/ids"):
            self.assertIn(text, tickets)
        states = p.rail("docs", "states")["text"]
        for state in ("new", "accepted", "implementing", "reviewing", "in-ci", "merge-ready", "merged", "dropped"):
            self.assertIn(f"| `{state}` |", states)


class Review(RailTest):
    def test_the_review_contract_and_retry_pages_cover_the_answers_an_agent_gives(self):
        p = self.fixture()
        review = p.rail("docs", "review")["text"]
        for text in ("rail answer NN F1 fixed", "declined", "parked", "refuter", "--owner", "security seat",
                     "skip_paths", "PERSON"):
            self.assertIn(text, review)
        self.assertIn("rail amend NN", p.rail("docs", "contract")["text"])
        retries = p.rail("docs", "retries")["text"]
        for text in ("[retry] budget", "rail consult NN", "rail accept NN", "NN-advice.md"):
            self.assertIn(text, retries)


class Operations(RailTest):
    def test_the_operations_pages_are_there(self):
        p = self.fixture()
        self.assertIn("rail doctor", p.rail("docs", "guards")["text"])
        packs = p.rail("docs", "packs")["text"]
        self.assertIn(".rail/packs/NAME/", packs)
        self.assertIn("never changes ticket state", packs)
        self.assertIn("## Decision", p.rail("docs", "adr")["text"])
        self.assertIn("A person is asked only about what a revert doesn't undo", p.rail("docs", "environments")["text"])
        journal = p.rail("docs", "journal")["text"]
        for name in ("requested", "accepted", "amended", "claimed", "saved", "worked", "step", "shipped", "tier_raised",
                     "finding",
                     "consulted", "continued", "dropped"):
            self.assertIn(f"| `{name}` |", journal)  # every event the engine writes has its row
        for text in ("NN-review.json", "review/v1", "A review is complete for a patch", "rail/ids"):
            self.assertIn(text, journal)
        cloud = p.rail("docs", "cloud")["text"]
        for text in ("Import a ruleset", ".rail/ruleset.json", "Automatically delete head branches", "rail provision",
                     "rail:needs-you", "stale_minutes", "rail/ids", "several repositories",
                     "Unattended work runs in the cloud", "Answer from any device"):
            self.assertIn(text, cloud)
        self.assertIn("required check", p.rail("docs", "github")["text"])
        self.assertNotIn("- away:", p.rail("docs")["text"])  # unattended work is the cloud page's
        self.assertIn("GITHUB_TOKEN", p.rail("docs", "github-runner")["text"])
        sweep = p.rail("docs", "sweep")["text"]
        for text in ("Sweep:", "Review:", "skip_paths", "[sweep] every", "parked"):
            self.assertIn(text, sweep)
        sources = p.rail("docs", "sources")["text"]
        for text in (".rail/sources/NAME.md", "max_open", "rail source NAME --json", "NAME#KEY", "weekly-review"):
            self.assertIn(text, sources)
        self.assertIn("rail source NAME --json", cloud)
        adopt = p.rail("docs", "adopt")["text"]
        for text in ("rail adopt BRANCH FILE", "fails on the base", "base_checks", "`adopted` event", "ASSUMED:"):
            self.assertIn(text, adopt)
        self.assertIn("a stranger's ticket is only ever a request", p.rail("docs", "bots")["text"])
        self.assertIn("| Q1 | scope |", p.rail("docs", "grill")["text"])
        stats = p.rail("docs", "stats")["text"]
        for text in ("rail stats --since", "Hit rate", "merged with no review", "BY MODEL"):
            self.assertIn(text, stats)


def prose(text):
    """A markdown text's lines with what stands in a code span or a fenced block blanked out."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append("")
        else:
            out.append("" if fenced else re.sub(r"`[^`]*`", " ", line))
    return out


def misused(terms, text):
    """[(line number, word, term)] for each word a term's `not` lists that stands in the text's prose."""
    found = []
    for n, line in enumerate(prose(text), 1):
        for t in terms:
            for word in t["not"]:
                if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", line, re.I):
                    found.append((n, word, t["term"]))
    return found


class Terms(RailTest):
    """One word for one thing: Rail's own text keeps to engine/terms.toml."""

    def texts(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = [os.path.join("engine", "reviewer.md"), os.path.join("seed", "AGENTS.md"),
                 os.path.join("seed", "tickets", "TEMPLATE.md")]
        for folder in (os.path.join("engine", "docs"), os.path.join("engine", "guides")):
            paths += [os.path.join(folder, name) for name in sorted(os.listdir(os.path.join(root, folder)))
                      if name.endswith(".md")]
        skills = os.path.join("seed", "skills")
        paths += [os.path.join(skills, name, "SKILL.md") for name in sorted(os.listdir(os.path.join(root, skills)))]
        for path in paths:
            with open(os.path.join(root, path)) as f:
                yield path, f.read()
        # What the table writes into briefs: its string literals, each as one line of prose.
        with open(os.path.join(root, "engine", "rail", "table.py")) as f:
            tree = ast.parse(f.read())
        yield "engine/rail/table.py", "\n".join(
            node.value.replace("\n", " ") for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str))

    def test_rails_own_text_uses_no_word_the_terms_rule_out(self):
        engine()
        from rail import docs
        terms = docs.terms()
        bad = [f"{path}:{n}: '{word}', where Rail says '{term}'"
               for path, text in self.texts() for n, word, term in misused(terms, text)]
        self.assertEqual(bad, [])

    def test_the_check_finds_a_planted_word_and_leaves_a_code_span_alone(self):
        engine()
        from rail import docs
        terms = docs.terms()
        text = "A ticket waits.\nThen a human approves it.\nThe value `human` is gone.\n```\nhuman\n```\nNon-humans too.\n"
        self.assertEqual(misused(terms, text), [(2, "human", "person")])
        self.assertEqual(misused(terms, "Its acceptance criteria are the Definition of Done."),
                         [(1, "acceptance criteria", "Done Contract"), (1, "definition of done", "Done Contract")])

    def test_every_term_names_a_page_that_exists_and_rail_docs_prints_the_list(self):
        p = self.fixture()
        engine()
        from rail import docs
        terms = docs.terms()
        self.assertEqual([t["term"] for t in terms if t["page"] not in docs.topics()], [])
        self.assertEqual(len({t["term"] for t in terms}), len(terms))
        page = p.rail("docs", "terms")["text"]
        self.assertIn("| person | Whoever answers for the repository", page)
        self.assertIn("| `rail docs kinds` | human, humans, operator, maintainer |", page)
        self.assertIn("- terms: Terms", p.rail("docs", raw=True).stdout)
