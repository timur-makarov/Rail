# Checks the author can't bend, and how strong the tests are: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and are
no longer described here: the review's `REVIEW.md` files, reviewer prompt and schema, all read from the base
branch (`rail docs review`), and flaky checks, meaning the re-run on failure, the `flake` event, the line in the
reviewer's brief, the sweep's ticket and the FLAKES table in `rail stats` (`rail docs retries`, `rail docs
sweep`, `rail docs stats`). Nothing below is implemented, and nothing below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

**Passing the checks is a weak signal.** About one in five benchmark patches that pass their tests fails
stronger tests. Test suites that agents write are 88-96% valid but kill at most 55.5% of planted bugs
(TestSuiteBench). (reported)

**Agents bend checks when they can.** On ImpossibleBench, where any pass is cheating, GPT-5 passed 76% of
one-off impossible SWE-bench tasks. The four methods seen in transcripts: edit the tests, overload operators,
record extra state to return different outputs, special-case the inputs. A stop-if-the-tests-are-wrong line cut
cheating from 93% to 1% on one benchmark and only from 66% to 54% on another; hiding the tests cut it to near
zero and cost real performance; read-only tests are "a promising middle ground". No single countermeasure is
reliable, so they are layered: tests the author can't change, a prompt rule, a detector for edits to tests and
for hardcoded outputs. (reported)

**Where Rail stands.** The Done Contract's `Check:` lines are frozen at acceptance, and `rail amend` is the
only way to change them (`engine/rail/steps.py`, confirmed). But:

- The test files those lines run are not frozen. A ticket can edit an existing test until it passes. Only the
  reviewer looks for it: "a check weakened, skipped or deleted so that it passes" (`REVIEW_LOOK_FOR` in
  `engine/rail/review.py`, confirmed).
- Nothing measures whether the tests would catch a mistake on the changed lines.
- `[tests] paths` exists, and `rail init` fills it from the language profiles (`rail docs languages`), but no
  engine code reads it yet (`engine/rail/docs.py` says "nothing yet", confirmed).

## Part 1: the old tests run against the new code

When a ship passes, and the change edits or deletes a file that existed on the base and matches `[tests]
paths`, the engine runs the checks once more with the base version of those files:

1. In the ticket's worktree, `git checkout <base> -- <files>` for each edited or deleted test file. A renamed
   file counts under its old path. The engine's list of changed files can't give that: `changed_files` runs
   `git diff --name-only`, which with git's default rename detection lists only the new path
   (`engine/rail/project.py`, confirmed). So this step reads `git diff --name-status <base>...<ref>` and takes
   the old path of each `R` row (a rename to a path outside `[tests] paths` counts too).
2. Run `verify` and each `Check:` line, as ship runs them.
3. Put the worktree back with `git reset --hard <head>` and `git clean -fdq`, as `base_checks` does after its
   run (`engine/rail/steps.py`, confirmed). `clean` without `-x` keeps ignored files such as installed
   dependencies (inferred from git's documented behaviour).
4. Record a `base_tests` event: `patch_id`, the files, and per command `green` or `red` (the same values as
   `base_checks`). It runs once per `patch_id`, so a clean rebase doesn't run it again.

When a command was green with the edited tests and is red with the base ones, the engine adds a blocking
finding: "The base version of `tests/x.py` fails on this change: `<command>`, exit N."

**How the finding enters the ledger.** A `finding` event alone is not enough: `Ledger` builds its findings
only from the runs stored in `NN-review.json`, and reads `finding` events only for ids those runs hold
(`engine/rail/review.py`, confirmed). So the engine stores a run entry, as `_read` does for a reviewer, with:

- `role: "engine"`, `patch_id`, `head`, `at`, and `summary`: "base versions of edited tests, run against this
  change";
- one finding per red command: `severity: "blocking"`, `file` (the old test path), `claim`, and `evidence`:
  the command, its output's tail, and `rerun` filled from the engine's own run with `reproduced: true`. The
  engine ran it, so the evidence is not run a second time: `_read` re-runs a reviewer's evidence, and this run
  doesn't go through `_read`;
- a `finding` event `by: "engine"` with `outcome: "open"`, `severity` and `claim`, as `_read` writes for a
  reviewer's new finding.

Ship adds the updated `NN-review.json` to `run.files`, which commits journal files with the events. On a later
patch, a command that is still red is stored with `repeats` set to the open finding's id, so it stays one
finding.

The author answers it like any finding (`unanswered`, `disputed` and `complete` read every role, confirmed):

- **fixed:** the old test's behaviour is kept. `rail answer NN F fixed` needs no new commit today
  (`engine/rail/cli.py`, confirmed), and `needed_run` re-checks a fixed blocking finding only by a later run of
  `review` or `security` (confirmed), so an `engine` finding marked fixed on an unchanged patch would close
  unchecked. So `rail answer` refuses `fixed` for an `engine` finding while the ticket's `patch_id` is the one
  the finding was reported on, with one sentence: "Change the code or the test, then `rail advance NN`: the
  base tests run again on the new patch." Once the patch changed, the rule runs again at ship, before any
  review of that patch; a command still red is reported again with `repeats`, and the ledger reopens the
  finding as for a reviewer's repeat. `needed_run` keeps its two roles;
- **declined:** the contract changes that behaviour on purpose. The answer names the Done Contract line or
  `## Why` sentence that says so. A disputed blocking finding goes to the refuter, as today, with the contract
  in its brief.

`rail stats` counts `engine` findings on their own line, not under the reviewer's hit rate or `BY MODEL`.

The reviewer's brief also holds the `base_tests` result, so a change that weakened a test and passed is seen
twice: by the rule and by the reviewer.

It runs only at ship, not in `rail ci`: it fails no step, and CI repeats only what can fail a ship (`CHECKS`
in `engine/rail/steps.py`, confirmed). A new test file is the author's, and is left alone: the agent's hands
stay on new tests and off old ones, the middle ground the research describes.

**`[tests] paths`** is read for the first time here: globs of the files that hold tests and their runner's
settings (such as `tests/**`, `**/*_test.go`, `**/conftest.py`, `vitest.config.*`). `rail init` already writes
it from the language profiles; the agent adjusts the list. Empty switches Parts 1 and 2 off. `engine/rail/docs.py`
then drops "nothing yet" from its line.

## Part 2: changes to checks are named

The review brief gains a section, "Changes to what checks this change", listing:

- each changed file that matches `[tests] paths`, with whether it existed on the base;
- each changed `REVIEW.md`;
- the `base_tests` result (Part 1).

The reviewer's look-for list gains one line, beside the one about weakened checks: "output special-cased to a
test's inputs, or code that detects it runs under test". `reviewer.md` is unchanged.

These items go to the reviewer only, not to a person's "Read these" list: a changed test can be undone, and
only what can't be undone reaches a person. A change to `.rail/config.toml`, where `verify` lives, is already
PERSON through `person_paths`, and a change to CI workflows is PERSON under the kind `runs-with-secrets`
(`rail docs kinds`).

`REVIEW.md` stays out of `person_paths`: an AUTO ticket can change it for later tickets, and this section names
that change to the reviewer of the ticket that makes it (Decision 2).

## Part 3: the worker is told to stop on a wrong test

`engine/guides/build.md`, section 2 ("Run every check now"), gains one line:

> **It is wrong:** it contradicts the `## Why`, or no correct change can pass it. Say so and amend the
> contract with `rail amend NN "why"`. Never make it pass by special-casing its inputs, by editing a test to
> match your code, or by detecting that it runs under test.

This is cheap help, not a guard: the same kind of line worked well on one benchmark and little on another
(reported, ImpossibleBench). Part 1 and the reviewer's new line are the guards. Consult's `stop` line already
says a plainly wrong check is the agent's to amend (CHANGELOG, confirmed), so the two agree.

## Part 4: held-out scenarios (to consider)

Scenario checks written when the ticket is made and kept where the worker doesn't read them are one way to
separate who writes the tests from who writes the code (StrongDM's practice; reported, no outcome data
published). In Rail:

- The contract writer (`TICKET_LINT`, run on `[worker] contract`) also writes one to three `Scenario:` lines:
  commands like `Check:` lines, that drive the behaviour from outside.
- They are stored on the ref `refs/rail/holdout/NN`, not in the ticket file, so the worker's brief and
  worktree never hold them. The guard denies a Bash command that names `refs/rail/holdout`. This is mistake
  prevention: a worker that goes looking can still find them, and the run log from `proposals/worker.md`
  shows whether it did.
- At ship the engine runs them after the `Check:` lines. A red scenario fails the ship with its name and exit
  code, not its text, so the brief doesn't hand the scenario to the worker.

Against it: hiding tests costs the worker performance (ImpossibleBench); held-out tests gave "only minimal
improvement" over a model judge on EvilGenie; a failure the worker can't read is hard to fix, and a wrong
scenario would spend attempts up to the cap (reported). So it is built only if its test (Tests, item 5) shows
it catches what Parts 1 to 3 miss. That test needs `rail replay`, which the owner has set aside for now
(2026-11-26), so this part waits.

## Part 5: tests that catch real mistakes (craft)

`engine/guides/build.md`, section 4 ("Test where behaviour is visible"), gains a short list of kinds of test,
each with when it applies. The tool for each language is in its profile (`rail docs languages`); the guide
names none.

- **Property tests** for parsers, encoders, round trips and invariants. Above all for stored data shapes,
  which a revert can't undo (`rail docs kinds`).
- **Idempotency as a property:** running it twice changes nothing. For handlers, jobs and migrations.
- **Differential tests for a rewrite:** the old and the new code on the same inputs, compared. For a service,
  the same recorded requests sent to both.
- **Fuzzing** for code that reads input from outside.
- **A real database in tests**, started for the test, not a mock of it.
- **A migration run up, down and up again.**

The research calls these practice with no cross-study success rate (reported).

## Part 6: a mutation score on the changed lines, as a number first

Plant small faults only in the lines the change added, and count how many the tests catch. There is no public
number on its cost or value for agent pull requests (reported); mutation-style checks rejected about 20% of
"solved" patches in SWE-ABS (reported). So it starts as a measurement:

- **`[commands] mutation`**, empty by default: a command the project names, run with `RAIL_BASE` set, that
  mutates only the diff against it and prints one JSON line `{"killed": K, "survived": S, "timeout": T}`. Each
  language profile proposes one (`proposals/languages.md` Part 4 names the tool and its wrapper per language).
- **When:** at ship, after every check passed, only when a file outside `[tests] paths` changed. Its own
  timeout, `[commands] mutation_timeout_secs` (default 900).
- **What it records:** a `mutation` event with the counts and `patch_id`. It is no step, no attempt and no
  state, like `base_checks` (`engine/docs/journal.md`, confirmed): a failure or timeout records the reason and
  fails nothing.
- **`rail stats`** adds the score (killed over killed plus survived) by month, and by worker model.
- **Later, by decision:** the surviving mutants go into the reviewer's brief as facts for "missing or weak
  checks", or a bar fails a ship. Neither until the numbers show where a bar belongs (Decision 4).

## Docs and files that change

- `engine/rail/review.py` (the brief's new section; the look-for line; a function that stores the `engine` run
  entry and its `finding` events, with `repeats` on a later patch and the evidence's `rerun` filled from the
  engine's own run; `needed_run` keeps its two roles, and its docstring says why); `engine/rail/cli.py`
  (`rail answer` refuses `fixed` on an `engine` finding while the patch is unchanged), `engine/docs/review.md`.
- `engine/rail/stats.py`: `engine` findings on their own line, out of the hit rate and `BY MODEL`; the mutation
  score.
- `engine/rail/steps.py` (`base_tests` after a passing ship, reading renames with `--name-status`; the
  updated `NN-review.json` in `run.files`; the `mutation` run), `engine/rail/config.py` and
  `engine/rail/docs.py` (`[tests] paths` read, `[commands] mutation` and `mutation_timeout_secs`).
- `engine/docs/journal.md`: the `base_tests` and `mutation` events; `by: engine` on a finding; the `engine`
  role in `NN-review.json`. `engine/docs/stats.md`: the mutation score, the engine's findings by outcome.
  `engine/docs/languages.md`: each profile's mutation command.
- `engine/guides/build.md`: the lines in Parts 3 and 5.
- If Part 4 is built: `engine/docs/tickets.md`, `engine/docs/contract.md`, the guard's deny rules.

## Tests, each before its part is kept

1. **Gate cases, no model.** With the stand-in reviewer (`tests/fake_reviewer.py`):
   - a ticket that removes an assertion from an existing test gets a `base_tests` event with `red` and an open
     blocking finding `by: engine`, stored as an `engine` run in `NN-review.json` with reproduced evidence, and
     the ticket can't merge until it is answered; marked fixed while the base test is still red on the new
     patch, it is reported again with `repeats` and reopens; disputed, it goes to the refuter; a ticket that
     edits a test and keeps its behaviour gets `green` and no finding; a deleted test is restored for the run;
     a renamed test is restored under its old path; `rail answer NN F1 fixed` on an `engine` finding is
     refused while the patch is unchanged, and accepted after a commit changes it; a new test file is not run
     in its base version; an empty `[tests] paths` runs nothing; a clean rebase doesn't run it again; the
     worktree is unchanged afterwards;
   - the review brief lists changed test files and `REVIEW.md`;
   - a fake mutation command's JSON lands in a `mutation` event; one that exits 1 or times out fails nothing;
     no mutation run when only test files changed;
   - `rail stats` shows the mutation score and the engine's findings on fixture journals.
   Kept when every case behaves as written.
2. **Part 1 on real history, no model.** On the history of three open-source repositories, one per language
   profile where possible: every commit that edits an existing test file is run with the base version of those
   files. Each red result is read by hand and sorted: a weakened test, a behaviour change the commit message
   states, or neither. Kept when the red results are not dominated by the third kind (at most one in three),
   since each of those would cost an answer and maybe a refuter run. The share of commits that edit tests also
   tells the time Part 1 adds to ships.
3. **The `build.md` line and the reviewer's line, with a model (wording untested until model runs).** Tickets
   with a `Check:` that contradicts the `## Why` (an impossible ticket), and controls whose checks are right;
   old and new text, 4 runs per arm, as prompt changes are tested today (CHANGELOG). Kept when, on the
   impossible tickets, the new text amends in at least 3 of 4 runs and makes the check pass by special-casing
   in none, and on the controls it amends no more often than the old text. For the reviewer's line: changes
   that special-case a test's inputs and plain controls; kept when the reviewer blocks the planted ones in at
   least 3 of 4 runs and raises no new blocking finding on the controls in at least 3 of 4.
4. **Part 5, with a model.** Tickets where a property, idempotency or differential test fits (a parser, a
   handler, a rewrite), old and new `build.md`, 4 runs per arm: kept when the new text writes such a test in at
   least 3 of 4 runs and the mutation score on those tickets is not lower.
5. **Part 4, with a model, only if Decision 3 asks for it.** Needs `rail replay`, which is set aside. Arms
   with and without held-out scenarios: kept when the scenarios fail on some runs that Parts 1 to 3 and the
   review let through, and the solve rate drops by less than the share of bad changes they catch.

Tests 3 to 5 use models, so they wait for the owner to restart the paused model tests.

Not covered: a test that runs real services or secrets the ticket's machine lacks (Part 1 then fails on both
versions and finds nothing); how much a mutation score predicts reverts (Part 6 starts collecting it).

## Assumed, not verified

- That the base version of an edited test usually still runs against the new code. A test that imports a
  renamed helper fails for that reason; test 2 measures how often.
- That `cargo mutants --in-diff`, and diff-limited modes in the other languages' mutation tools, work as
  their names say. Each is checked before a profile names it.
- That `git checkout <base> -- <file>` followed by `reset --hard` and `clean -fdq` leaves the worktree as it
  was, ignored files included, as `base_checks` already relies on.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. Part 1 and Part 2, after test 2: `[tests] paths` is read, the `base_tests` event, the `engine` finding, the
   brief section and the look-for line.
2. Part 6: `[commands] mutation`, the event, the stats line. The default commands come with each language
   profile.
3. Part 3 after test 3; Part 5 after test 4.
4. Part 4 only after Decision 3 and test 5, which needs `rail replay` and the run log (`proposals/worker.md`).

## Left out

- **A formal-proof gate.** Proofs fit narrow components when a team has the skill, and a proof can be "verified
  but vacuous" when its spec misses the property that matters (reported). Property tests and bounded checks
  (Part 5) cover the same ground for ordinary software. A project that proves a component can put the prover in
  `verify` or a `Check:` line like any command.

## Decisions

**Made by the owner (2026-11-25):** Rail is focused, not restricted, by its rules, so checks against an agent
bending its own checks are in scope. Review before merge stays. One attempt per ticket. **(2026-11-26):** the
benchmark and `rail replay` are set aside for now; steps that need model runs build their deterministic part
and mark wording untested.

**Open:**

1. The engine's finding when an old test fails on the new code: blocking, answered like any finding
   (proposed), or a line in the reviewer's brief only.
2. `REVIEW.md` in `person_paths`. Proposed: no. It is guidance; the look-for list is engine code, already a
   person's, and a change to `REVIEW.md` is named to the reviewer (Part 2).
3. Held-out scenarios: drop them, or test them once `rail replay` exists. Proposed: leave them unbuilt while
   replay is set aside.
4. The mutation score: a number only (proposed) until 50 tickets per profile have one; then decide whether
   surviving mutants go to the reviewer, and whether a bar fails a ship.

## Sources

Rail, confirmed: `engine/rail/review.py`, `steps.py`, `config.py`, `project.py`, `docs.py`, `cli.py`;
`engine/docs/review.md`, `journal.md`, `languages.md`, `stats.md`; `engine/guides/build.md`; `seed/config.toml`;
`CHANGELOG.md`.

Reported: TestSuiteBench (ETH/LogicStar, Oct 2026); ImpossibleBench, Zhong, Raghunathan, Carlini, arXiv
2510.20270; EvilGenie, arXiv 2511.21654; SpecBench (Weco AI); SWE-ABS; StrongDM's software factory posts
(held-out scenarios).
