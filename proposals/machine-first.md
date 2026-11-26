# Written for machines: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and are no
longer described here: one term per concept, with `engine/terms.toml`, `rail docs terms` and a check on Rail's
own text, and the JSON that says `person` (`owner: "person"`, `person_wait`, `WAITING_PERSON`, `schema_version`
2) (`rail docs loop`); a reason required from an agent for every decision (`rail docs journal`); the removal of
hidden HTML comments from issue text at intake, with `hidden_removed` and its line in `rail stats`
(`rail docs tickets`, `rail docs stats`); and `[init] skill_dirs` with `rail init --skills` (`rail docs guides`).
What remains is making the brief data first: `action.facts`, a renderer per reason code, and a schema for the
answer. Nothing below is implemented, and nothing below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

The owner's position (2026-11-25): everything is written for machines, and the data holds all the information
the machines need to work effectively and consistently, with as few misunderstandings as possible. People touch
Rail in three places: at the start (grilling and tickets), when prototyping, and in tunnel-vision code reviews.
Deciding what to build is not Rail's concern; Rail takes in what needs building and does the job.

What a misunderstanding costs (inferred from the retry rules, `engine/docs/retries.md`, confirmed): a worker that
misreads a brief ships, fails a step and spends an attempt; one that misreads a contract builds the wrong thing,
which the checks may pass. Both readers are models. Neither can ask a question back.

**Rail is mostly machine data already, and its briefs are not.** The journal is JSON lines with a version and a
documented field table; review runs follow the `review/v1` schema; the config is TOML; the ticket's front matter
is typed (`engine/docs/journal.md`, `engine/review-v1.json`, `engine/rail/ticket.py`, confirmed). The brief, the
one text every worker acts on, is prose that each row of the first-match table builds from the engine's facts
(`engine/rail/table.py`, confirmed). The facts are gone once the sentence is written: nothing but a model can read
them back, and a test can only compare strings. The `rail next --json` answer carries `schema_version`, `owner`,
`action.kind`, `reason.code`, `steps` and `cwd` (`answer()` in `engine/rail/cli.py`), and `action.brief`, one
string per code, is all the rest (confirmed).

## Part 1: every brief is data first

1. **The answer carries the facts.** Every `agent_task` and `person_wait` answer gains `action.facts`: the
   values its brief was built from. Shared keys: `ticket`, `title`, `branch`, `ticket_file`. By code:

   | Code | Facts |
   |---|---|
   | `IMPLEMENT` | `done_contract` (each `Check:` command), `scope_paths`, `out_of_scope`, `size` (`count`, `cap`), `migration`, `base_green`, `findings`, `person_note`, `save_note`, and what the brief now also holds: the ticket's `## Why` and decided rows, `## Tried` |
   | `STEP_FAILED` | `failed` (`step`, `status`, `detail`, `signature`), `advice`, `findings`, `person_note` |
   | `ANSWER_FINDINGS` | `findings`: each id with severity, file, line, claim, check and evidence, as the ledger describes them |
   | `VERIFY_ASSUMPTIONS` | `open_assumptions` |
   | `TICKET_LINT` | `lint_errors`, `not_taken` |
   | `SPLIT` | `size`, `cap`, `rest_branch` |
   | `REBASING`, `CONFLICT` | `cwd`, `branch`, the conflicted files |
   | each `person_wait` | `wait`: what is needed, and how a person answers (`rail accept`, `rail:go`, `rail drop`) |

   A row the table gained since (`TOOL_MISSING`, `TOOL_DOWN`, `STUCK` and the revert rows) gets its facts in
   the same way: the values its brief is built from. Where a page adds to a brief later, it adds a fact key too.
2. **One renderer per code.** The table's lambdas stop reading the facts object `f` directly: each row builds
   `facts`, and a renderer per code writes the brief from `facts` alone. The first version renders today's text
   byte for byte, so no worker sees a change and no model test is needed for it.
3. **A schema for the answer.** `engine/answer-v1.json`, as `engine/review-v1.json` is for the reviewer, with
   `facts` per code, and every `reason.code`, action kind and `wait.kind` the engine writes. Every answer the
   test suite produces is checked against it (inferred: the suite already runs every verb through the real
   launcher). After it lands, a pull request that adds a code adds its schema entry too.

Who reads `facts`: tests, which can assert on a fact instead of a string; `rail work` (`rail docs cloud`), which
can keep the facts of a run beside its result; and any host that drives Rail through its CLI. The worker still
gets the brief: a model reads prose well, and a brief is where the engine says what the facts mean.

**Left out:** a new layout for the brief, such as labelled blocks in place of sentences. It would change what
every worker reads, so it needs real runs first (four per arm, as for every prompt change), and nothing shows yet
that today's sentences are misread. `rail stats` can show it: a step that fails often right after a brief is
where a layout test would start. The same holds for wording: a renderer that is allowed to change its text is
built, and its wording marked untested, until those runs are made.

## Docs and files that change

- `engine/rail/table.py`: rows build `facts`; renderers per code. `engine/rail/cli.py`: `answer()` passes `facts`.
  `engine/answer-v1.json` (new).
- `engine/docs/loop.md`: `action.facts`. `engine/docs/cloud.md`: the runner prompt, if it names a fact.

## Tests, each before its part is kept

1. **Gate cases, no model.**
   - Every answer the suite produces validates against `answer-v1.json`; an answer with a fact key the schema
     doesn't name fails the test.
   - For every row code in a fixture, the renderer given `facts` produces the brief today's code produces,
     byte for byte; a fact removed from `facts` changes the brief (the check can fail).
   - The suite fails when an answer carries a code `answer-v1.json` doesn't name (a planted code).
   Kept when every case behaves as written.

Not covered: whether `facts` lowers misreadings (no model test until a layout change is proposed).

## Assumed, not verified

- That the string literals in `table.py` hold all of the briefs' wording. The review brief (`review.py`) and the
  consult brief (`consult.py`) are built elsewhere; the renderers cover them only if they hold literals.

## Order of work

One pull request, with docs and `CHANGELOG.md`.

1. `action.facts`, the renderers, `answer-v1.json`.

Codes that other pages add go into the engine on their own pull requests; the schema takes every code present
when it lands.

## Decisions

**Made by the owner (2026-11-25):** everything is written for machines, with people at three touchpoints; what to
build is not Rail's concern beyond taking it in. **Made by the owner (2026-11-26):** the benchmark and
`rail replay` are set aside for now, so `facts` is not built for them; steps that need model runs build their
deterministic part and mark wording untested.

**Open:**

1. **An `Assisted-by:` trailer** on squash commits, `Assisted-by: AGENT:MODEL`, as the Linux kernel's convention
   has it (reported, from secondary summaries). The squash message is the engine's, so it would be one line
   beside `Review:`, with the models from the `worked` events. Proposed: no, until an outside reader asks;
   `rail stats` already reads the models from the journal.
2. Whether a person's `rail accept` note should be required too. Proposed: no: approving is itself the reason.

## Sources

Rail, confirmed: `engine/rail/table.py`, `cli.py`, `ticket.py`; `engine/review-v1.json`; `engine/docs/journal.md`,
`loop.md`, `retries.md`, `stats.md`.
