# What is left to build, in order

This page lists every feature of Rail that is proposed and not built. The unit is a feature: one thing that
can be built, tested and kept or thrown away on its own. The features stand in the order they are to be built.
Nothing on this page is implemented, and nothing on it was run, unless a line says so.

`proposals/team.md` is a separate page for a team that takes Rail up. It stays as it is until the features
here are built, and is brought up to date then.

## How to read this page

- **Next, in this order** holds the steps the owner confirmed on 2026-11-26 and 2026-11-27. Nothing in them
  waits for anything but an earlier step, unless a step says so.
- **Waits for a condition** groups the rest by what has to be true first: tools on the machine, model tests,
  real tickets, a deploy target, more people, the owner taking up a feature set aside.
- **Dropped** names what the owner decided not to build, so that it is not proposed again.

Each feature says what it does, how, the test that decides whether it is kept, what it waits for, the
decisions still open, and what was assumed and not checked. Size is S (under a day), M (a few modules) or L (a
new subsystem). A feature refers to another by its name in bold, and to built behaviour by its docs page, as
`rail docs review`.

A feature is built as one commit or a few, each with its tests, its docs and one line in `CHANGELOG.md`. Wording
for a model that no model run has tested is marked as such where it is written. When a feature is built, its
section leaves this page.

## Next, in this order

### 1. Fixes from the first run on real GitHub

Size: S.

**What it does.** On 2026-11-26 the current Rail was set up in a real repository from a cloud session, and its
pull request ran the `rail` check on GitHub's runner. Two defects were fixed that day: the check's answer for
a pull request with no ticket did not print why `verify` failed, and Rail's own example line for a tool was read
as a credential by the secret scan. These came out of the same run and are left. The answer to a finding of
the secret scan that is no secret is in **An exemption the worker writes is confirmed**.

**How.**

- **The Python sample project fails its own type check.** Seen on 2026-11-26, as soon as basedpyright was on
  the machine: `test_languages.Projects.test_python` fails, in the plain run as well as with `--languages`.
  The profile's `types` part, `uv run basedpyright`, reports four errors in `tests/projects/python`: `dict`
  with no type arguments, twice, and `pytest` not resolved from the two test files. Until then the part was
  reported as "not run", so nobody had seen it. To settle while fixing: whether the sample project is at fault
  (its annotations, and a type checker that is not told where the project's environment is), or the profile's
  default is too strict for a project that has no settings for the type checker. This comes first, because
  the suite is red on any machine that has the tool.
- **pip for a pip project.** `rail init` wrote the uv commands into a project that tracks
  `requirements-dev.txt` and no lockfile. A profile takes the manager whose lockfile is tracked, and with none
  the first one, which is uv; pip's lockfile is `requirements.txt` and no other name. The change: with no
  lockfile tracked, a tracked `requirements*.txt` picks pip, and the pip commands name the file that was found
  (`pip-audit -r requirements-dev.txt`). A `pyproject.toml` with no lockfile and no requirements file stays
  with uv. `profiles/python/profile.toml`, `engine/rail/init.py`, `rail docs languages`.
- **The older engine's `needs_person`.** `engine/rail/review.py` and `readthese.py` still read a
  `needs_person` sentence from a review run stored by an older engine, and `rail docs journal` describes it.
  Rail keeps no compatibility with its earlier versions, so the reads and the sentence go.

**Kept when.** The language tests pass on a machine that has every tool (`python3 tests/run.py --languages`
prints no "not run" line for Python). Gate cases, no model: a fixture with `requirements-dev.txt` and no
lockfile gets the pip commands; one with `uv.lock` beside it keeps uv; a review run that holds only
`needs_person` raises nothing and adds no "Read these" row.

**Waits for.** Nothing.

#### One line of work per ticket, in the docs

Size: S.

**What it does.** The docs define one line of work per ticket and say what the engine does not do: no parallel
lines of work on one ticket and no best-of-N. The owner's position (2026-11-25) is one attempt per ticket for
now.

**How.**
- Defined in `engine/docs/retries.md`, which uses "attempt" for the retry budget only: a ticket has one line
  of work at a time, one worker carrying it from claim to merge. This is not the retry budget's "attempt",
  which is one ship counted toward `[retry] budget` and `cap` (`rail docs journal`, "The retry budget"; `rail
  docs retries`). Those are unchanged.
- The reason: several lines of work with the best kept pays only when something can rank them. For most web,
  API and command-line work every line that passes the checks looks the same to them. The differences are
  design and readability, which only a reviewer judges, at the cost of a review per line and with its own
  false alarms (inferred; reviewers' false alarms on correct changes ran 21-48% in one benchmark, reported).
- Left out: best-of-N in the loop. The narrow cases where it might pay, named so they are recognised: a bug
  that lines of work fail in different ways; performance work with a benchmark that ranks them; a rewrite with
  an old-against-new check that ranks them. Running a ticket again to see whether passing lines of work differ
  in whether they hold is **`rail replay`**, which is set aside.

**Kept when.** `rail docs retries` carries the definition and the Rail text check (`engine/terms.toml`) still
passes. No model test.

**Waits for.** Nothing.

### 2. Numbers later decisions wait for

Size: S.

**What it does.** Four small measurements, each a few lines in the engine, so that decisions on other features
can rest on numbers: how many GitHub REST calls a merged ticket costs, which tools a run used, what dropped
tickets cost and what a worker costs per merged ticket by tier, and whether the runner's Bash calls may run as
long as a worker run.

**How.**
- Counting GitHub REST calls (feeds **A machine identity** and **Conditional GitHub reads**):
  - Each engine event a command writes carries `gh_calls`, the REST calls that command made. Counted in
    `engine/rail/forge.py`.
  - `rail stats` gives calls per merged ticket (`engine/rail/stats.py`, `engine/docs/stats.md`).
  - `rail doctor` shows `x-ratelimit-remaining` (`engine/rail/doctor.py`). The forge already reads that header
    when a limit is hit; the doctor line is not built.
  - Rule: when calls per merged ticket times merged tickets per hour passes half of the token's limit, the
    machine identity is the fix, since an installation's budget is its own. GitHub's limits (confirmed on
    GitHub's docs, 2026-11-25): 5,000 requests an hour for a person's token, shared by every app and token
    acting as that person; 1,000 an hour per repository for `GITHUB_TOKEN`; a GitHub App installation gets at
    least 5,000, rising with repositories and users up to 12,500. Secondary limits: at most 100 requests at
    once, 900 points a minute per endpoint (a read costs 1, a write 5), and in general 80 content-creating
    requests a minute and 500 an hour. A conditional request answered `304 Not Modified` does not count
    against the primary limit.
  - Every session, the runner and the person's own `gh` likely share one person's 5,000 (inferred: the
    runner's work carries that person's login; how a cloud session picks its GitHub identity is not verified).
- The tools a run used: the worker's `worked` event records them, so `rail stats` shows which tools tickets
  use and which probes fail. Documented in `engine/docs/tools.md`.
- Dropped-ticket cost and worker cost by tier. Already in `engine/rail/stats.py`: the `Dropped` line carries
  the sum the drop marks keep ("Their runs reported $X.", JSON `drops.cost_usd`), and every tier's `OUTCOMES`
  column has "cost for each merged ticket" (review and worker cost together, JSON `review_usd`, `worker_usd`,
  `cost_per_ticket` per tier row). What is left, to settle with the person who reads the stats: whether the
  dropped cost needs a line of its own rather than the sentence ending the `Dropped` line, and whether the
  worker's cost alone (without the review's) is shown per tier, since only the JSON has it.
- `rail provision` writes the two Bash variables `BASH_DEFAULT_TIMEOUT_MS` and `BASH_MAX_TIMEOUT_MS` into the
  machine's settings with the hooks (`engine/rail/cli.py`). The repository's `seed/settings.json` already
  gives the Bash tool a 30-minute default and a 2-hour ceiling, and `rail doctor` warns when `[worker]
  timeout_minutes` is not under the ceiling. A session whose repository settings do not load (several
  repositories, a project thread; `rail docs cloud`, "Session shapes") has the Bash tool's own defaults, so a
  worker run of 90 minutes would be cut. `rail provision` writes the hooks there today and no Bash variable
  (confirmed).

**Kept when.**
- `gh_calls` on events matches the fake GitHub's request log (`tests/fake_gh.py`).
- A tool a run used is on its `worked` event, and `rail stats` counts it.
- A fixture checks that `rail provision` writes the two Bash variables into the machine's settings.

**Waits for.** Nothing.

**Assumed, not verified.**
- That a session whose project settings do not load uses the machine's settings for the Bash variables
  (inferred from how the hooks reach it).

### 3. Answer facts, renderers and the answer schema

Size: M.

**What it does.** Every `agent_task` and `person_wait` answer of `rail next --json` carries `action.facts`:
the values its brief was built from. One renderer per reason code writes the brief from those facts alone, and
`engine/answer-v1.json` says what every answer may hold. Tests, `rail work` and any host that drives Rail
through its CLI can then read a fact instead of parsing a sentence. The worker still gets the brief as prose.
The first version renders today's text byte for byte, so no worker sees a change.

**How.**
- Shared keys on every answer with facts: `ticket`, `title`, `branch`, `ticket_file`. Keys by reason code:
  - `IMPLEMENT`: `done_contract` (each `Check:` command), `scope_paths`, `out_of_scope`, `size` (`count`,
    `cap`), `migration`, `base_green`, `findings`, `person_note`, `save_note`, and what the brief now also
    holds: the ticket's `## Why` and decided rows, and `## Tried`.
  - `STEP_FAILED`: `failed` (`step`, `status`, `detail`, `signature`), `advice`, `findings`, `person_note`.
  - `ANSWER_FINDINGS`: `findings`, each with id, severity, file, line, claim, check and evidence, as the
    ledger describes them.
  - `VERIFY_ASSUMPTIONS`: `open_assumptions`.
  - `TICKET_LINT`: `lint_errors`, `not_taken`.
  - `SPLIT`: `size`, `cap`, `rest_branch`.
  - `REBASING`, `CONFLICT`: `cwd`, `branch`, the conflicted files.
  - each `person_wait`: `wait`, which says what is needed and how a person answers (`rail accept`, `rail:go`,
    `rail drop`).
  - The rows `TOOL_MISSING`, `TOOL_DOWN`, `STUCK` and the revert rows get facts the same way: the values their
    brief is built from. A later feature that adds to a brief also adds a fact key.
- Renderers: the lambdas in the first-match table (`engine/rail/table.py`) stop reading the facts object `f`
  directly. Each row builds `facts`, and a renderer per code writes the brief from `facts` alone.
  `engine/rail/cli.py` `answer()` passes `facts` into the answer.
- Schema: `engine/answer-v1.json` (new), as `engine/review-v1.json` is for the reviewer. It holds `facts` per
  code and every `reason.code`, action kind and `wait.kind` the engine writes. Every answer the test suite
  produces is checked against it (the suite already runs every verb through the real launcher). After it
  lands, a pull request that adds a code adds its schema entry too. Codes that other features add go in on
  their own pull requests; the schema takes every code present when it lands.
- Docs: `engine/docs/loop.md` describes `action.facts`. `engine/docs/cloud.md` changes the runner prompt only
  if it names a fact. `CHANGELOG.md`.
- Left out: a new layout for the brief, such as labelled blocks in place of sentences. It changes what every
  worker reads, so it needs real runs first (four per arm, as for every prompt change), and nothing shows yet
  that today's sentences are misread. `rail stats` can show where to start: a step that fails often right
  after a brief. A renderer that is allowed to change its text is built with its wording marked untested.

**Kept when.** Gate cases, no model, all behaving as written:
- Every answer the suite produces validates against `answer-v1.json`. An answer with a fact key the schema
  does not name fails the test.
- For every row code in a fixture, the renderer given `facts` produces the brief today's code produces, byte
  for byte. A fact removed from `facts` changes the brief (the check can fail).
- The suite fails when an answer carries a code `answer-v1.json` does not name (a planted code).

Not covered: whether `facts` lowers misreadings (no model test until a layout change is proposed).

**Waits for.** Nothing.

**Open decision.**
1. Whether squash commits get an `Assisted-by: AGENT:MODEL` trailer, as the Linux kernel's convention has it
   (reported, from secondary summaries). It would be one line beside `Review:`, with the models from the
   `worked` events. Proposed: no, until an outside reader asks; `rail stats` already reads the models from the
   journal.
2. Whether a person's `rail accept` note should be required too. Proposed: no, because approving is itself the
   reason.

**Assumed, not verified.**
- That the string literals in `table.py` hold all of the briefs' wording. The review brief (`review.py`) and
  the consult brief (`consult.py`) are built elsewhere; the renderers cover them only if they hold literals.

### 4. A triage step for the questions the engine raises

Four features, built in this order. The first is the step itself. The other three are the questions it answers
first.

The reason for the step: wherever the worker judges its own case today, a run with no stake in the answer judges
it instead. The engine states a fact, a fresh run answers one closed question about it, and the engine acts on
the answer. The owner decided this on 2026-11-27.

#### The triage step

Size: M.

**What it does.** The engine raises a question from a fact it produced itself, such as a test that fails or a
line the change added. A fresh run that did not write the change answers it with one of a few fixed answers, and
the engine does what that answer means. The refuter already works this way for one question, whether a finding
holds. This makes it one step with a list of question types, so that a new question costs a table entry and its
test.

**How.**

- **One table of question types**, `QUESTIONS` in a new `engine/rail/triage.py`. Each entry holds: the type's
  id; the fact that raises it; what the brief shows; the two to four answers allowed, each with one line on what
  it means; what the engine does on each answer; and for an answer that lets the change through, the evidence it
  must name and how the engine checks it.
- **Events.** `question`, with the type, the `patch_id` and the fact; `answered`, with the answer, its evidence,
  whether the evidence passed its check, and the run's cost. A question is open while its patch has no
  `answered` event.
- **One row.** `TRIAGE` in `engine/rail/table.py` fires for a shipped ticket with an open question, before any
  review, so that no review is spent on a patch that is about to change.
- **The run.** The engine starts it as it starts a review: a fresh session with tools that read and run and
  never push, a brief that holds only what the type says to show, and a JSON answer checked against a schema.
  `[triage] command` and `[triage] model` in `.rail/config.toml`; empty means the review seat's.
- **Evidence.** An answer that lets the change through names its evidence, and the engine checks what it can: a
  quoted contract line is in the ticket, a named file is in the change. An answer whose evidence fails its check
  is invalid output: the run is repeated once, and a second invalid answer is the wait an invalid review already
  has (`STUCK_REVIEW`).
- **An answer that stops the change** fails a step named `triage`. The worker gets the fact and the answer in
  its brief, and the failure counts toward the retry budget like any failed step. The next patch raises the
  question again only if the fact still holds. Nothing goes to the refuter: a second run on the first one's
  answer is not added.
- **Numbers.** `rail stats` counts, for each type, the questions, each answer's share and the cost. The sweep
  names a type that got the same answer in 19 of its last 20 questions: such a type is a rule the engine can
  apply with no run.
- **Only closed questions.** Whether a change is good stays the reviewer's question.
- Files that change: `engine/rail/triage.py` (new), `engine/rail/table.py`, `engine/rail/steps.py`,
  `engine/rail/config.py`, `engine/rail/stats.py`, `engine/rail/sweep.py`, `seed/config.toml`, a new page
  `engine/docs/triage.md`, `engine/docs/journal.md`, `engine/docs/loop.md`, `CHANGELOG.md`.

**Kept when.** Gate cases, no model, with a stand-in for the run as `tests/fake_reviewer.py` is for the
reviewer: a fact raises one question for a patch and no second one for the same patch; an answer that passes
with checked evidence lets the ticket go on to review; an answer that stops fails `triage` and returns the
ticket to the worker; evidence that fails its check repeats the run once and then waits; `rail stats` shows the
counts on fixture journals. Kept when every case behaves as written.

**Waits for.** Nothing. The wording of each brief is not tested with a model until the owner restarts the model
tests.

**Open decision.** None.

**Assumed, not verified.**

- That a run with a narrow brief answers a closed question better than the worker does about its own change. No
  measurement from Rail; each type's own test decides whether it is kept.
- That the review seat's model suits the step. `rail stats` shows the cost for each type once it runs.

#### Old tests run against the new code

Size: M.

**What it does.** When a ticket edits, deletes or renames a test file that existed on the base, Rail runs the
checks again with the base version of that file. If a command that passed with the edited test fails with the
old one, the engine raises the question `old-test`. Reason: about one in five benchmark patches that pass their
tests fail stronger tests, and agents bend checks by editing tests until they pass. The `Check:` lines are
frozen at acceptance, but the test files they run are not.

**How.**

- `[tests] paths` is read for the first time. It holds globs of the files that hold tests and their runner's
  settings (such as `tests/**`, `**/*_test.go`, `**/conftest.py`, `vitest.config.*`). `rail init` already writes
  it from the language profiles, and the agent adjusts the list. Empty switches this feature off, including the
  brief section. `engine/rail/docs.py` drops "nothing yet" from the `tests.paths` line.
- When a ship passes, and the change edits or deletes a file that existed on the base and matches `[tests]
  paths`, the engine runs the checks once more with the base version of those files:
  1. In the ticket's worktree, `git checkout <base> -- <files>` for each edited or deleted test file. A renamed
     file counts under its old path. `changed_files` (`engine/rail/project.py`) runs `git diff --name-only`,
     which with git's default rename detection lists only the new path, so this step reads `git diff
     --name-status <base>...<ref>` and takes the old path of each `R` row. A rename to a path outside `[tests]
     paths` counts too.
  2. Run `verify` and each `Check:` line, as ship runs them.
  3. Put the worktree back with `git reset --hard <head>` and `git clean -fdq`, as `base_checks` does after its
     run (`engine/rail/steps.py`). `clean` without `-x` keeps ignored files such as installed dependencies.
  4. Record a `base_tests` event: `patch_id`, the files, and per command `green` or `red` (the same values as
     `base_checks`). It runs once per `patch_id`, so a clean rebase does not run it again.
- It runs only at ship, not in `rail ci`: it fails no step by itself, and CI repeats only what can fail a ship
  (`CHECKS` in `engine/rail/steps.py`). A new test file is the author's and is left alone.
- **The question.** A command that was green with the edited tests and red with the base ones raises `old-test`.
  The brief shows the old test, the test's diff, the command and the tail of its output, and the Done Contract
  with its `## Why`. It does not show the rest of the change. The answers:

  | Answer | Meaning | Evidence the engine checks | What the engine does |
  |---|---|---|---|
  | `contract` | The contract asks for this change in behaviour | The quoted Done Contract line or `## Why` sentence is in the ticket | Records it; the ticket goes on |
  | `moved` | The behaviour is kept; the test was moved, renamed or rewritten | The named test file is in the change and matches `[tests] paths` | Records it; the ticket goes on |
  | `lost` | Behaviour is lost that the contract does not ask for | None | Fails `triage`; the worker keeps the behaviour, or amends the contract |

- The reviewer's brief gains a section, "Changes to what checks this change", listing: each changed file that
  matches `[tests] paths`, with whether it existed on the base; each changed `REVIEW.md`; the `base_tests`
  result; and the answer to each `old-test` question.
- These items go to the reviewer only, not to a person's "Read these" list: a changed test can be undone. A
  change to `.rail/config.toml`, where `verify` lives, is already PERSON through `person_paths`, and a change to
  CI workflows is PERSON under the kind `runs-with-secrets` (`rail docs kinds`).
- `REVIEW.md` stays out of `person_paths`: it is guidance, the look-for list is engine code, and the brief
  section names a change to it to the reviewer of the ticket that makes it.
- Files that change: `engine/rail/steps.py` (`base_tests` after a passing ship, `--name-status`);
  `engine/rail/triage.py` (the type); `engine/rail/review.py` (the brief section); `engine/rail/config.py` and
  `engine/rail/docs.py` (`[tests] paths` read); `engine/docs/review.md`; `engine/docs/triage.md`;
  `engine/docs/journal.md` (the `base_tests` event); `CHANGELOG.md`.
- Not covered: a test that runs real services or secrets the ticket's machine lacks (the base run then fails on
  both versions and raises nothing). For Rust, unit tests live in `#[cfg(test)]` modules inside source files, so
  this feature covers only integration tests there.
- The paths of driving checks (see **Language fixtures checked on a machine with every toolchain** and the
  per-surface recipes) join `[tests] paths`, so this covers driving checks too.

**Kept when.**

1. Gate cases, no model, with the stand-in for the triage run:
   - a ticket that removes an assertion from an existing test gets a `base_tests` event with `red` and one
     `old-test` question, and no review starts before it is answered;
   - answered `lost`, the `triage` step fails and the worker's brief holds the command and the answer;
   - answered `contract` with a line that is in the ticket, or `moved` with a test file that is in the change,
     the ticket goes on to review; with a line or a file that is not there, the run is repeated;
   - a ticket that edits a test and keeps its behaviour gets `green` and no question;
   - a deleted test is restored for the run; a renamed test is restored under its old path;
   - a new test file is not run in its base version; an empty `[tests] paths` runs nothing; a clean rebase does
     not run it again; the worktree is unchanged afterwards;
   - the review brief lists changed test files, `REVIEW.md` and the answers.
   Kept when every case behaves as written.
2. On real history, no model. On the history of three open-source repositories, one per language profile where
   possible: every commit that edits an existing test file is run with the base version of those files. Each red
   result is read by hand and sorted into the three answers. The share of commits that edit tests tells the time
   this feature adds to ships, and the share of red results tells how many runs it costs. The sorted results are
   kept: they are the answer key for the model test below. This test comes before the feature is built.
3. Model test, once the owner restarts the model tests: the triage brief on the sorted results of test 2, at
   least six of them, with each of the three answers among them, two runs each. Kept when it gives the
   hand-sorted answer in at least three quarters of the runs, and answers `contract` or `moved` in no more than
   one run in eight on the cases sorted as `lost`.

**Waits for.** **The triage step**. The test on real history comes first and waits for nothing.

**Open decision.** None. The owner chose the triage run over a finding the worker answers (2026-11-27).

**Assumed, not verified.**

- That the base version of an edited test usually still runs against the new code. A test that imports a renamed
  helper fails for that reason, and `moved` is its answer; test 2 measures how often.
- That `git checkout <base> -- <file>` followed by `reset --hard` and `clean -fdq` leaves the worktree as it
  was, ignored files included, as `base_checks` already relies on.

#### An exemption the worker writes is confirmed

Size: M.

**What it does.** Three things a worker writes today excuse its own change from a check, and the engine takes
each at its word: a `SENSOR(NN): why` comment on a line a sensor flags, a `VERIFIED: decided, not checked:` row
in the ticket, and, once the docs name it, a line in `.gitleaksignore`. Each now raises a question.

**How.** Three question types, each raised at ship from the change's added lines:

| Type | Raised when the change adds | Answers that let it through | Answers that stop it |
|---|---|---|---|
| `sensor-exempt` | a `SENSOR(NN): why` comment | `holds`: the sensor misreads the line, or the contract requires the line as it is (quotes the contract line) | `does-not-hold`: fails `triage`; the worker removes the comment and mends the line |
| `decided` | a `VERIFIED: decided, not checked:` row | `choice`: nothing in the repository or its dependencies settles it, and no Done Contract item depends on it | `checkable` (names where it can be checked): fails `triage`, and the worker checks it. `contract` (quotes the item that depends on it): fails `triage`, and the worker amends the contract so that the choice stands where the reviewer reads it |
| `secret` | a line in `.gitleaksignore` | `not-a-secret`: says what the string is, such as an example, a fixture or a public id | `secret`: a wait for a person, who rotates it; the line may not stay |

- **The secret scan's false finding gets its answer.** The scan reads every commit of the branch, and the guard
  forbids rewriting a branch, so a false finding has no answer today: the line can be changed, and its first
  commit still fails. `rail docs languages` gains the answer: put the finding's fingerprint, which the scan
  prints, into `.gitleaksignore` and commit it. That line raises `secret`. The file does not join
  `person_paths`: a person adds nothing to a string that is already pushed, unless it is a real secret, and then
  the act is to rotate it.
- **A real secret.** After the person's act the engine starts the ticket's branch again from the base under a
  new name, because the scan would fail on the old branch's commits for good.
- The `secret` brief shows the finding with its rule, file and line, and the string itself only as the scan
  redacts it, with the lines around it.
- Files that change: `engine/rail/triage.py`, `engine/rail/steps.py` (the added lines that raise each type),
  `engine/docs/sensors.md`, `engine/docs/tickets.md`, `engine/docs/languages.md`, `engine/docs/triage.md`,
  `CHANGELOG.md`.

**Kept when.** Gate cases, no model, with the stand-in: each added line raises its question once for a patch;
each answer does what the table says; a `SENSOR` comment that was on the base raises nothing. In use, over the
first 20 questions of a type: a type answered the same way 19 times is turned into a rule or removed.

**Waits for.** **The triage step**.

**Open decision.** None.

**Assumed, not verified.**

- That gitleaks honours `.gitleaksignore` when it scans commits (`gitleaks git`), as its documentation says. Not
  checked here.
- That a redacted finding with its surrounding lines is enough to tell an example from a secret.

### 5. A PERSON ticket takes one act

Size: M.

**What it does.** A person acts once on a PERSON ticket: at the merge, after reading the lines `## Read these`
lists. The approval of the contract before the build is no longer asked for unless the project turns it on for a
kind. The owner decided this on 2026-11-27.

The reason follows from what a person is responsible for, which is what can't be undone. A kind takes effect at
the merge, at a release or at a push (`rail docs kinds`, "Takes effect"), never when a contract is accepted: a
contract is text, and nothing has been built. The lines a person has to read exist only once the change does.
What an approval before the build buys is that no build is spent on a change the person would refuse. That is a
matter of cost, so it is a setting.

**How.**

- **A new key**, `approve_contract`, beside `person_paths` in `.rail/config.toml`: a list of kind ids, empty in
  the seed. A ticket with one of those kinds waits at `APPROVE_CONTRACT` before it is built, and at
  `APPROVE_AMEND` when its contract is amended, as every PERSON ticket does today. A PERSON ticket with none of
  them is accepted by the engine, as an AUTO ticket is.
- **An amended contract** on any ticket is a row of `## Read these`, as it is on an AUTO ticket today.
- **The other waits of a PERSON ticket go the way of an AUTO ticket.** A finding the refuter upheld stands. A
  ticket that comes after a dropped one is decided by the contract writer's model (`AFTER_DROPPED`). A ticket at
  its retry cap goes to **A diagnosis before a stuck ticket is dropped or waits**.
- **What stays a person's.** The merge (`MERGE_BY_PERSON`). The grants: a tool that is missing or down, a merge
  that failed, the budget. `rail:hold` on any ticket.
- **A release ticket** keeps its own act, the approval of the release, because the release is where its kinds
  take effect (**Release tickets**).
- A PERSON ticket still starts on `person_ladder`, and the security seat still reviews it.
- **Numbers.** `rail stats` counts the PERSON tickets a person closed without a merge, by kind. The sweep's
  summary names a kind with three or more among the last 20 PERSON tickets as one to put in `approve_contract`.
- Files that change: `engine/rail/table.py`, `engine/rail/config.py`, `engine/rail/readthese.py`,
  `engine/rail/stats.py`, `engine/rail/sweep.py`, `seed/config.toml`, `engine/docs/kinds.md` (also its paragraph
  on `runs-with-secrets` at push, which speaks of the approved contract), `engine/docs/loop.md`,
  `engine/docs/retries.md`, `engine/docs/tickets.md`, `engine/docs/github.md`, `engine/docs/cloud.md`,
  `CHANGELOG.md`.

**Kept when.** Gate cases, no model: with the seed config, a ticket whose scope reaches `person_paths` is built
with no wait and stops at `MERGE_BY_PERSON`; its amended contract is a "Read these" row and no wait; an upheld
finding and a dropped `after` raise no wait; with `approve_contract = ["money"]`, a ticket of that kind waits
before the build and one of another kind does not. Kept when every case behaves as written.

**Waits for.** Nothing. Built before the diagnosis, which relies on a PERSON contract that no person approved.

**Open decision.** None.

**Assumed, not verified.**

- That a person refuses few PERSON tickets at the merge. The count in `rail stats` shows it, and
  `approve_contract` is the answer for a kind where it is not so.

### 6. A diagnosis before a stuck ticket is dropped or waits

Size: M.

**What it does.** A ticket at its retry cap gets one diagnosis before anything else happens to it. Today an AUTO
ticket at the cap is dropped with a record, and it is tried again only when a person labels its issue again; a
PERSON ticket waits for a person to read the journal and the branch and say what to do differently. Both end at
a person, and neither says why the ticket was stuck. A ticket that is stuck more often has a wrong or too large
contract than a worker that needs a person's hint. The owner decided this on 2026-11-27.

**How.**

- **A question type, `stuck`**, of **The triage step**, raised once for a ticket, on either tier, when it
  reaches the budget after consult, or the cap. It runs on the contract writer's model (`[worker] contract`).
  The brief shows the ticket, each failure in the journal with its step, signature and output's tail, the
  reviewer's findings, consult's advice, and the change.
- **The answers.**

  | Answer | Evidence | What the engine does |
  |---|---|---|
  | `contract`: a `Check:` line or Done Contract item is wrong, or two contradict each other | The quoted line or lines | An agent task for the contract writer: amend the contract. Then a fresh budget and cap |
  | `too-large`: the work is more than one ticket | The parts it names | An agent task for the contract writer: split it with `rail-slice`. The ticket is dropped with a record that names the tickets that replace it, and its issue stays open until the last of them merges |
  | `approach`: the contract is right and the attempts share a mistake | What they share, and what to do instead | A new branch from the base, the note in the implement brief, a fresh budget and cap |
  | `machine`: the failures are the machine's or a tool's | The failure it names | The wait that exists for it (`TOOL_DOWN`) |
  | `cannot-tell` | None | As today: an AUTO ticket is dropped, a PERSON ticket waits (`RETRY_CAP`). The diagnosis is in the record and in the wait's brief |

- **Once.** A ticket that reaches the cap again after its diagnosis is dropped or waits, as today, with the
  diagnosis in the record.
- **The tier is not changed by any answer.** The paths and kinds make a ticket PERSON, so a PERSON ticket whose
  contract the diagnosis amended still stops at the person's merge.
- **Not consult.** Consult advises the worker about the code, before the cap. The diagnosis asks whether the
  contract is the fault.
- A dropped ticket's issue gets the diagnosis as a comment.
- **Numbers.** `rail stats` counts stuck tickets by answer, and how many merged after their diagnosis.
- Files that change: `engine/rail/triage.py`, `engine/rail/table.py` (`STUCK`, `RETRY_CAP`, the two agent
  tasks), `engine/rail/stats.py`, `engine/docs/retries.md`, `engine/docs/triage.md`, `engine/docs/loop.md`,
  `CHANGELOG.md`.

**Kept when.** Gate cases, no model, with the stand-in: a ticket at the cap gets one `stuck` question and no
drop or wait before its answer; each answer does what the table says; a second cap drops an AUTO ticket and
makes a PERSON ticket wait. In use, over the first 20 diagnosed tickets: kept when at least five merged
afterwards, themselves or through the tickets that replaced them; otherwise the type is removed.

**Waits for.** **The triage step** and **A PERSON ticket takes one act**. The wording of the brief is not tested
with a model until the owner restarts the model tests.

**Open decision.** None. The issue of a ticket that was split stays open until the last of the tickets that
replace it merges (owner, 2026-11-27).

**Assumed, not verified.**

- That a fresh run can tell a wrong contract from a wrong approach from the journal and the change. Not
  measured.

### 7. Projects within a repository

Size: L.

**What it does.** One repository may hold several projects: services, apps, libraries and infrastructure, in one
language or several. Rail works out which they are from the tree in front of it, every time, and a ticket then
sets up and checks only the projects its change reaches. Whatever is added to the repository later, by a ticket
or by a person, is found the same way, and what no check reads is stated as a fact and raises a question. The
shape the owner has in mind is a backend, three workers, a frontend and infrastructure in one repository, and
one repository for each team.

The owner's rule (2026-11-27): anything may be put into a repository, and Rail drives what needs driving. A
check that runs once, at `rail init`, cannot do that, so nothing here depends on init.

Tried on 2026-11-27 with today's `rail init`, on a tree with a backend, three workers and a shared library in
Python, a TypeScript frontend and a Terraform folder. It wrote one `setup` of six installs and one `verify` of
2,649 characters with about 26 checks in a row, so a change of one line in one worker runs all of them. It wrote
no check for the Terraform folder. A manifest added after init is named by `rail doctor` and the sweep and
checked by nothing until a ticket edits the config; a folder with no manifest is noticed by nothing.

**How.**

- **Projects are derived, each time they are needed.** The engine reads the tracked manifests of the tree it
  works on: one project for each folder a manifest marks, named after its folder (`workers/billing`; `root` for
  the repository's root), with the language profile's `setup` and `verify` run in that folder. The detection is
  `detect` in `engine/rail/init.py`, which the `languages` line of `rail doctor` already runs on every call. A
  ticket that adds a manifest is set up and checked as a project in its own ship, with no change to the config.
  What a profile brings besides the commands (its rules, test paths, migration paths and generated files)
  applies to the paths of each project of that profile, with nothing written. `rail init` writes no entry for a
  project.
- **`[[projects]]` holds only what can't be derived**, and takes the place of `[[profiles]]` in
  `.rail/config.toml`. An entry either names a derived project and changes its `paths`, `setup`, `verify` or
  `uses`, or declares a project no manifest marks: `name`, `paths`, `setup`, `verify`, `uses`. A repository with
  one manifest at its root and no entry has one project, `root`, with the paths `**`.
- **The base and the branch together.** At a ship the projects are derived from the base and from the branch. A
  change that removes a manifest and keeps the code leaves that code in no project, which the next point states;
  it does not quietly lose its checks.
- **What nothing covers is a fact.** At each ship, and at `rail next` when the base branch has moved by a commit
  no ticket made, the engine lists the tracked files inside no project, by folder and file type. Left out: files
  at the repository's root, the folders Rail and the host own (`.rail/`, `.claude/`, `.github/`), and the
  vendored, installed and built folders detection already skips. The reviewer's brief names the uncovered files
  of the change it reviews.
- **An uncovered folder raises a question, once.** A question type `uncovered` of **The triage step**, for a
  folder and its set of file types. The brief shows the folder's file names and the first lines of a few files.
  The answers:

  | Answer | Evidence | What the engine does |
  |---|---|---|
  | `nothing-to-check`: docs, assets, data, examples | What the folder holds | Records it in `.rail/journal/coverage.json`, which only the engine writes. The folder is asked about again only when its file types change |
  | `needs-checks`: code or configuration that a tool can check, or that takes effect somewhere | What kind of thing it is | Files a ticket, below |

- **The ticket that covers a folder.** Filed by the engine with the id `coverage:FOLDER`, written by the
  contract writer's model with `rail-verify`. Its work: look up the checks this kind of file has (a formatter, a
  validator, a linter, tests), write the `[[projects]]` entry with them, and add the folder's path under its
  kind in `[kinds]` when it is of a kind, as a Terraform folder is `infrastructure`. It edits
  `.rail/config.toml`, so it is PERSON under `controls`: a person merges the gates for a new kind of thing once.
- **Until that ticket merges** the folder's files are checked by nothing, and the change that added them is not
  held for it: the reviewer sees them named, and names their kind, which makes the change PERSON without any
  path (`rail docs kinds`, "The reviewer").
- **Kind paths follow what reviewers find.** When a reviewer names a kind on a file that no `[kinds]` path
  matches, the engine records the file and the kind. The folder's coverage ticket adds the path; where there is
  none, the sweep files a ticket that does.
- **What stays for the whole repository.** `[commands] setup` and `verify` hold only what belongs to the whole
  repository, such as the secret scan over the branch's commits, and they run after the projects' own.
- **What a change reaches.** The projects whose `paths` match a changed file, and every project that uses one of
  them, followed through `uses` to the end. A changed file inside no project reaches every project: a root
  manifest, a CI workflow, `.rail/config.toml`. A lockfile at a workspace's root reaches the members of that
  workspace and no project outside it.
- **Where the set is used.** At claim, `setup` runs for the projects the ticket's `scope_paths` reach. At ship
  and in CI, `verify` runs for the projects the changed files reach, after `setup` for any of them the claim did
  not set up. Each run is its own step, named `verify:NAME`, in the receipts and the journal, so retries, flaky
  checks and time are counted for each project.
- **One required check.** `rail ci` works the same set out from the pull request's diff against the base, so the
  check GitHub requires stays the one check `rail`. No workflow uses a path filter: a required check that a path
  filter skips never reports, and the pull request then waits for good.
- **Where `uses` comes from.** A dependency in code is derived with the projects, from the workspace's own
  files, read and not run: the members of a uv workspace and their workspace sources, the `workspace:`
  dependencies of a pnpm workspace, the path dependencies of a Cargo workspace, the modules of a `go.work`. A
  dependency no import shows, such as a frontend that calls the backend's API, is an entry in `[[projects]]`.
  The next section, **Workspace layouts**, is that detection and the commands, and is built in this step.
- **What `uses` does not do.** It decides which checks run. Whether the frontend still works against a changed
  backend is shown only by a check that drives both (**Driving the real product**). A shape two services share,
  such as a queue message or a database schema, is the kind `data-shape` and makes its ticket PERSON, as today.
- **A repository with its own task graph.** Where Nx, Turborepo, Bazel or Pants already works out what a change
  affects, an entry makes the workspace one project whose `verify` calls that tool with `$RAIL_BASE`.
- **Printed, because it is not written.** `rail doctor` prints the projects as derived: name, paths, profile,
  `uses` and commands, with the entries of `[[projects]]` marked. Its `languages` line becomes `coverage`: the
  folders that are uncovered and not yet answered. `rail context NN` names the projects the ticket reaches and
  their commands.
- **Checks on the table.** The config check refuses a `[[projects]]` entry whose `uses` names no project, and a
  cycle.
- **Numbers.** `rail stats` gains a split by project beside the splits by worker and by language, with groups
  under five summed into `other`.
- **Docs.** `rail docs languages` (its section "A language added later" goes), `rail docs config`, `rail docs
  triage`, the init task's brief, and the seed config.

The areas map is a different thing and stays as it is: `## Areas` says, in a bug reporter's words, what lives
where, for people and for routing. It gets no column for which area may use which (dropped, 2026-11-27): `uses`
is the only graph. A package manager refuses most imports of a project that is not declared as a dependency, and
a boundary inside one project is a rule of that language's sensor (**Sensor sets per language**).

**Not built.** A profile for anything but the four languages: what a Terraform folder or any other new kind of
thing needs is looked up by an agent the first time it appears and written into `[[projects]]` once. A task
graph or a build cache of Rail's own. A required check for each project. A release for each project (**Release
tickets** waits for a deploy target). The projects' checks run side by side, until the time per step in `rail
stats` asks for it.

**Kept when.**

- Gate cases, no model, with the stand-in for the triage run, on a fixture with a Python service, a TypeScript
  app and a library both use:
  - with no `[[projects]]` entry, a change in the app runs the app's `setup` and `verify` only; a change in the
    library runs the library's and both users'; a change to a root file runs all; `rail ci` on the same diff
    runs the same set as the ship did;
  - a ticket that adds a fourth folder with a manifest is set up and checked as a project in its own ship, and
    the config is unchanged;
  - a ticket that adds a Terraform folder raises one `uncovered` question; answered `needs-checks`, a ticket
    `coverage:infra` is filed and is PERSON; answered `nothing-to-check`, the folder is not asked about on the
    next ship, and is asked about again when a file of a new type is added to it;
  - a commit on the base that no ticket made, adding an uncovered folder, raises the question at the next `rail
    next`;
  - a change that removes a manifest and keeps the code raises the question for that folder;
  - an entry in `[[projects]]` replaces a derived project's `verify`, and one with `uses` makes a change in the
    used project run the user's checks; an entry whose `uses` names no project, and a cycle, are refused;
  - `rail doctor` prints the derived projects and the uncovered folders.
  Kept when every case behaves as written.
- The same fixture from `rail init` to a merged ticket with the real toolchains, as the language tests run their
  projects (`python3 tests/run.py --languages`).

**Waits for.** **The triage step**. The fixture's audit and type checks need the tools on the machine
(**Provision lines and toolchain pins per language**). The wording of the `uncovered` brief and of the coverage
ticket is not tested with a model until the owner restarts the model tests.

**Open decision.** None. The ticket's `scope_paths` decide `setup` at claim, and a project the change first
reaches at ship is set up then (owner, 2026-11-27).

**Assumed, not verified.**

- That GitHub leaves a pull request waiting when a required check is skipped by a path filter. Its documentation
  says so; not tried here.
- That each workspace tool keeps its members' dependencies on each other in files Rail can read without running
  the tool.
- That each package manager refuses an import from a project that is not a declared dependency. A uv workspace
  synced with every package in one environment does not.
- That deriving the projects on every call is fast enough on a large tree. `detect` walks the tracked files
  once; not timed.
- That an agent finds the right checks for a kind of file it has not seen in the repository before. The person's
  merge of the coverage ticket is where a wrong set is caught.
- That many tickets changing one lockfile at a workspace's root will not make claims rest on each other too
  often. `rail stats` shows the time a ticket rests; **Claims by changed files** is the answer if it does.

#### Workspace layouts

Size: M.

**What it does.** The detection recognises uv workspaces, pnpm workspaces, Cargo workspaces and `go.work`,
derives one project for each member with commands that name the member, and reads the members' dependencies on
each other into `uses`. Reason: today `uv sync --locked` at a uv workspace's root syncs the root package only,
and a `go.work` repository is read as one profile for each folder that holds a `go.mod`, with nothing between
them.

**How.**

- Already built, so not described here: manifests below the root are found with the folders that hold them; a
  nested manifest inside another's folder counts for the top-most folder only; each part of `verify` and `setup`
  runs in its folder (`(cd web && pnpm test)`).
- A member's commands name it: `uv sync --locked --package NAME`, `pnpm --filter NAME`, `cargo test --locked -p
  NAME`, and `go test ./...` in the module's folder. All not checked.
- No filter for packages changed since the base is written into any command: the set a change reaches does that
  work for every language.
- Files that change: `profiles/*/profile.toml`, `engine/rail/init.py`, `engine/docs/languages.md`,
  `tests/test_languages.py`.

**Kept when.** Gate cases, no model, no toolchains, on fixture trees: a tree with a `pnpm-workspace.yaml`, one
with `go.work`, one with a uv workspace and one with a Cargo workspace each give one project for each member,
the member's commands, and `uses` as the workspace's files say. Kept when every case behaves as written. The
commands themselves are checked on a machine with the toolchains (**Language fixtures checked on a machine with
every toolchain**).

**Waits for.** Nothing.

**Assumed, not verified.**

- That the commands above behave as written: not checked.

### 8. The sweep reads more

Two features, built in this order. Both make the sweep read what it skips today.

#### The sweep reads reviewed merges

Size: S.

**What it does.** Today the sweep runs a reviewer pass only over changes that merged with no review. This adds
a second trigger: every `[sweep] every` merged tickets (20), whatever their review, the sweep's reviewer pass
reads the current code of the areas that changed since the last sweep. The reason is that duplication and
logic in the wrong area show up across tickets, and each ticket's own review sees one change.

**How.**
- In `engine/rail/sweep.py`, `run` calls `review.run` only when `commits` (the unreviewed ones) is non-empty;
  with nothing unreviewed it records a `harvest` step and runs no model. Change this so a sweep that is due by
  `every` always runs the reviewer pass.
- The pass reads the current code of each area (rows of `## Areas` in `ARCHITECTURE.md`) that a ticket merged
  since the last sweep changed. The sweep brief (`brief` in `sweep.py`) gains the list of those areas and the
  merged ticket ids.
- Cost: one model run per 20 tickets.
- A sweep with no parked finding, pattern or flaky check and no changed area still answers `SWEEP_EMPTY`.
- Files that change: `engine/rail/sweep.py`, `engine/docs/sweep.md` (its first bullet and "Review part"), the
  sweep brief text, `CHANGELOG.md`.

**Kept when.** Gate case, no model: a sweep due by `every` with every merged ticket reviewed starts a reviewer
pass, and the brief names the changed areas; a sweep with nothing merged runs none. In use: the pass's
findings that become tickets are counted over five sweeps; a pass that leads to no ticket in five sweeps is
removed.

**Waits for.** Nothing.

**Assumed, not verified.**
- The cost of the design sweep's model run over the areas that changed in 20 tickets.

#### The sweep gathers what tickets leave behind

Size: M.

**What it does.** The sweep collects what each ticket wrote down and nothing reads today, and turns it into
tickets. Information is kept when it is written outside any context window, in one known place, sent by the
engine to the next agent that needs it, marked confirmed, inferred or decided, and closed (done, a ticket, a
check, or dropped). A free-form reasoning log is left out on purpose: each change below has one reader and one
way to close.

**How.** Five collections, all read from the journals and the base branch for tickets merged since the last
sweep (`sweep.py`, next to `history` and `patterns`):
- **Out-of-scope problems.** The `Noticed:` lines under `## Look at` that the brief asks workers to write, and
  the "not tested" lines. Each becomes a candidate ticket in the summary.
- **Declined findings, grouped by kind.** `history` today gathers parked findings, advisory findings left
  open, and the checks of fixed findings. Add findings the author declined, grouped by kind.
- **A person's word.** Every `rail accept` note since the last sweep. The summary lists them. A note that
  reads as a standing rule gets a ticket (a line in the project's part of `AGENTS.md`, a check or a rule).
  Today these notes reach the briefs only until the next ship (`state.py`).
- **Repeated failures.** A failure signature (numbers, hashes and paths left out, as the flaky-check matching
  does) that recurs across tickets is flagged, and the sweep files a check or an `AGENTS.md` line. Today
  signatures are counted only within one ticket.
- **Work left for later.** A structure rule requires each `TODO` and `FIXME` to name the open ticket that will
  do it, `TODO(NN)`. The sweep files a removal ticket when ticket NN merged or was dropped and the comment is
  still in the tree. Fresh text matters because stale TODOs sent agents on detours of about 70% more steps
  (reported).
- Each collected item has one closing path: a ticket, a check, or dropped. The summary page in
  `.rail/journal/NN-summary.md` gains a section per collection; `engine/docs/sweep.md` is updated.

Worker-run patterns across tickets (commands that failed before the right one, commands not found, denied
calls, files re-read, in the `worked` event, a pattern in three or more tickets) are built: `patterns` in
`engine/rail/sweep.py` and "Patterns in the worker runs" in `engine/docs/sweep.md`. Flaky checks are built
too.

**Kept when.** From the journals, before and after, over the same number of merged tickets: failure signatures
that recur across tickets, and how many collected items ended as a merged ticket or check. A collection that
leads to nothing in five sweeps is removed. Gate case, no model: a `TODO(NN)` whose ticket merged gets a
removal ticket; a `TODO` with no number fails its structure rule.

**Waits for.** **The sweep reads reviewed merges** is not required, but both change the same summary and
brief, so build them in the same pass.

**Assumed, not verified.**
- The implement brief stays short with `## Why`, the decided rows and five tickets of history added.

### 9. Driving the real product

A ticket's checks pass on code that may still not work when the product is started and used. These features
make Rail start the product and drive it, at ship and in CI, and keep what it saw. They are built in the order
they stand in.

#### Product surfaces in the config

Size: M.

**What it does.** A project can describe its product in `.rail/config.toml`: how to start it, and each way
users reach it (a surface) with the command that drives that surface. Nothing runs these yet; this feature is
the config and its checks, which the other product features read. Today ship runs `verify` and `Check:` lines,
and nothing tells Rail how the product is reached.

**How.**

- `engine/rail/config.py` (`DEFAULTS`, a check for `[[surfaces]]`), `engine/rail/docs.py` (`rail docs config`)
  and `seed/config.toml` gain `[product]` and `[[surfaces]]`. The `[preview]` table belongs to **Preview
  environments**. Each key names its reader, as the seed config does.
- `[product]` (readers: ship and CI for the product step, `rail doctor`):
  - `start = ""`: starts the product in the ticket's worktree and returns. `RAIL_TICKET` is set, so parallel
    tickets pick their own ports and databases.
  - `ready = ""`: exits 0 once the product answers; changes nothing.
  - `seed = ""`: loads test data and the test identity from files in the repository.
  - `stop = ""`: stops what `start` started.
  - `ready_secs = 120`: how long `ready` may take before the product counts as not started.
- `[[surfaces]]` (readers: ship and CI), one table per surface:
  - `name = "web"`.
  - `kind = "web"`: one of `web`, `api`, `cli`, `agent`, `data`, `integration`, `mobile`.
  - `projects = ["frontend", "backend"]`: a ticket whose change reaches one of these projects runs this
    surface's check (**Projects within a repository**).
  - `check = ".rail/checks/web.sh"`: the driving check; it writes evidence into `$RAIL_EVIDENCE`.
  - `preview = false`: true means the check runs against a hosted preview (**Preview environments**).
- `kind` decides which recipe `rail-verify` uses (**Per-surface recipes and the project's run skill**) and
  which `rail doctor` bar lines apply (**The machine-operable bar in `rail doctor`**). The engine reads no
  other meaning into it.
- A project with no `[product] start` and no surfaces works as today. A `cli` or `data` surface often needs no
  `start`: its check runs the built program itself.
- The config check refuses an unknown key or an unknown kind, as it refuses unknown keys today. `[[surfaces]]`
  is checked like `[[rules]]` and `[[sensors]]`.
- Driving-check scripts live in the repository and count as tests. `rail init` adds each surface's `check`
  path to `[tests] paths` (`rail docs languages` describes the key), so that a ticket that edits a check
  script is held against the base's version of it once **Old tests run against the new code** (step 4) is
  built.
- **A surface added later.** Nothing here depends on `rail init`. The ticket that covers a new folder
  (**Projects within a repository**) says whether users reach what the folder holds, and if they do, it adds
  the surface and its driving check. The sweep files a ticket for a bar line that is new (**The
  machine-operable bar in `rail doctor`**).
- A new docs page, `engine/docs/product.md`, describes the tables.

**Kept when.** Gate cases, no model, on a fixture product in `tests/` (a small HTTP server and a CLI written
with Python's standard library, each with a driving check script and a planted-fault switch): `[product]` and
`[[surfaces]]` load; an unknown kind or key is refused; `rail init` adds each surface's `check` to `[tests]
paths`. Kept when every case behaves as written.

**Waits for.** Nothing. The `[tests] paths` base-version rule is a separate feature; this one only adds the
paths.

#### The product step

Size: L.

**What it does.** Ship and CI run the real product for every ticket that touches a surface: they start it,
seed it, run the surface's driving check, and stop it. A failed driving check counts like a failed `Check:`
line. Today the product is driven once, at setup, and nothing requires it again. About one in five benchmark
patches counted as solved fails stronger tests (TestSuiteBench, reported), so passing tests is a weak signal
that software works.

**How.**

- A new ship step, `product`, is added to `CHECKS` and `check()` in `engine/rail/steps.py`, after the `Check:`
  lines. `check()` is shared by ship and CI (`engine/rail/cli.py`). It runs when the change touches the
  projects of at least one surface:
  1. `start`, then `ready` until it exits 0 or `ready_secs` pass, then `seed`. When a touched surface has
     `preview = true`, **Preview environments** runs first and the check gets its URL.
  2. For each touched surface, its `check`, with `RAIL_EVIDENCE` set to an empty folder for that surface and
     `RAIL_URL` set to the local or preview address. Each is recorded as a `step` event named `product: NAME`,
     with its duration, as `Check:` lines are recorded today.
  3. `stop`, always, including after a failed check.
- A failed driving check counts like a failed `Check:` line: it moves the retry budget and cap as any step
  does (`rail docs retries`).
- **When the product does not start.** When `start` or `ready` fails, the engine runs them once on the base
  branch, as it does for a `verify` that fails. If the base fails as well, the attempt does not count and a
  fix ticket for the base comes first, with the same wording as the red-base `verify` case. If only the
  ticket's branch fails, the failure is the ticket's.
  - A command the shell cannot find (exit 127) is `could_not_run`, as today.
  - A missing tool is a `TOOL_MISSING` wait that costs no attempt; a failed probe afterwards is `TOOL_DOWN`
    (`rail docs tools`, built).
- Run in CI as well as at ship (open decision below): `provision` installs what the step needs on the runner.
- Files: `engine/rail/steps.py` (the step, the red-base rule), `engine/rail/cli.py`, `engine/docs/journal.md`
  (the `product` step), `engine/docs/loop.md` (the product step), `engine/docs/product.md`.

**Kept when.** Gate cases, no model, on the fixture product:
- A ticket whose change reaches a surface's project runs `start`, `ready`, `seed`, that surface's check and
  `stop`; one that reaches no surface's project runs none; `stop` runs after a failed check.
- With the planted fault on, the product step fails and counts against the retry budget; with it off, it
  passes. The same in `rail ci`.
- A `ready` that never exits 0 on the branch but does on the base fails the ticket; one that fails on both
  costs no attempt and gives the red-base answer.

Kept when every case behaves as written. In use, over the first 50 tickets per surface, count driving-check
failures on patches where `verify` and every `Check:` line passed. If a surface's step caught nothing in 50
tickets and its tickets show no revert or `caused_by` either, its recipe is revisited; the step is not removed
on that alone, since a quiet surface may simply be healthy.

**Waits for.** **Product surfaces in the config**. A host for the product's dependencies: a cloud session may
not be able to start a database or a browser (see Assumed).

**Open decision.** Does the product step run in CI as well as at ship? Proposed: yes. It is in `check()`,
which both run, and `provision` installs what it needs on the runner.

**Assumed, not verified.**
- That a cloud session can start the product's dependencies (a database, a browser) with `provision`. The
  machine is the session's to change (`engine/rail/init.py`), but a service that needs Docker may not run
  there.

#### Evidence from the product step

Size: M.

**What it does.** What each driving check saw is kept, so the reviewer and any later reader can see what the
product did. Today a step event keeps only the step, status, result, patch id, detail, duration and a failure
signature (a hash of the output); the output goes into the failure brief cut to 60 lines; the pull request's
Evidence table says "ran, pass" per step.

**How.**

- Each driving check writes what it saw into `$RAIL_EVIDENCE`: the steps it took, requests and responses, the
  command, output and exit code, and for a web page screenshots or a trace.
- **Text evidence**: files under 64 KB each, 256 KB per surface in all (files over a cap are cut at it). It is
  committed with the step events in a new journal file, `NN-evidence.json`: per surface, per file, its name
  and contents, keyed by `patch_id`. Only the engine writes the journal (`rail docs journal`), so the worker
  cannot rewrite it.
- **Redaction**: before anything is committed, for each environment name a `[tools.NAME]` declares (`env`) and
  for each `.env` value the worktree holds, its value becomes `[NAME]`. Evidence holds test identities and
  test-mode responses, and a committed secret cannot be taken out of history. A secret the project never
  declared is not caught.
- **Binary evidence** (screenshots, traces, recordings) is never committed (open decision below). On a
  session's machine it stays in the local cache (`.git/rail/cache/`, `engine/rail/project.py`). In CI the rail
  workflow uploads `$RAIL_EVIDENCE` as a workflow artifact, so every pull request has it. `seed/rail.yml`
  gains the upload step.
- **The pull request's Evidence table** gains one row per surface, such as `product: web | ran, pass | 6
  steps, 2 screenshots`, and the artifact's link when CI uploaded one. Rows come from step events today
  (`engine/rail/steps.py`).
- **The reviewer's brief** (`engine/rail/review.py`) gets the text evidence of the patch it reviews, so a
  claim in the change can be held against what the product did. The reviewer can also run the check itself, as
  it can run any command now.
- Files: `engine/rail/steps.py` (`NN-evidence.json`, the Evidence rows), `engine/rail/review.py`,
  `engine/docs/journal.md` (`NN-evidence.json`), `seed/rail.yml`.

**Kept when.** Gate cases, no model: text lands in `NN-evidence.json`, cut at its caps; a value of a declared
environment name and of a `.env` entry is replaced by its name; a binary file is never committed; the Evidence
table has the surface's row; the reviewer's brief holds the text. Kept when every case behaves as written. The
64 KB and 256 KB caps are revised from the numbers seen in use.

**Waits for.** **The product step**.

**Open decision.** Where does binary evidence live? Proposed: a workflow artifact in CI and the local cache on
a session's machine; never the repository.

**Assumed, not verified.**
- That a GitHub Actions workflow artifact is reachable from the pull request for the length of a review
  (artifacts expire under the repository's retention setting).
- That 64 KB per file and 256 KB per surface keep the journal small enough; the in-use numbers set them.
- That replacing declared values catches the secrets evidence can hold. The project's secret scan in `verify`
  runs over the branch's commits, journal included (inferred: it scans `$RAIL_BASE..HEAD`, per
  `engine/rail/init.py`).

#### The machine-operable bar in `rail doctor`

Size: M.

**What it does.** `rail doctor` says which pieces a project lacks before the machine can start, seed and drive
the product with no person, and whether each is a person's one-time act (`grant`) or work the machine can do
(`ticket`). Today doctor says nothing about whether the product can be started, seeded or driven. The owner's
basis (2026-11-24) is that a person's one-time act grants the machine a capability.

**How.**

- A project is machine-operable when it has each piece below. Plain `rail doctor` reports each and stays fast:
  it runs no project command, only version commands and, with a remote, GitHub calls through `gh`.

| Piece | What `rail doctor` checks | Missing: whose act |
|---|---|---|
| One command starts the product | `[product] start` and `ready` are set, or every surface is `cli` or `data` | A ticket: the machine writes the script |
| A seeded test identity | `[product] seed` is set when a `web`, `api`, `agent` or `mobile` surface exists | A ticket for the seed files. A third party's test account is a grant |
| A driving check per surface | each `[[surfaces]]` has a `check` that exists at its path; at least one surface | A ticket |
| A place to run it | local always; for a surface with `preview = true`, the `[preview]` commands are set and their tool's names are present | The preview host's token is a grant (`[tools.NAME]`, `rail docs tools`) |
| Probes that tell a broken machine from broken code | `[product] ready`; each tool's `probe` (`rail docs tools`) | A ticket for `ready`; a failing tool probe is a grant |
| A way back | the `rail:revert` label (`rail docs tickets`) | Rail sets the label up. Prod is the project's own CD gate (`rail docs environments`) |
| A machine that can run the surface | `mobile` with Android: `/dev/kvm` exists; with iOS: the machine is macOS | A grant: a runner with hardware acceleration, or a Mac |

- **Each failed bar line adds `kind`.** Today a doctor line is a name, a pass or fail, and a detail. `kind` is
  `grant` (a person's one-time act, named exactly: which token, which account, which machine) or `ticket` (the
  machine can build it). `grant` is the same kind as the wait kind of that name (`rail docs states`).
- **`rail doctor --product`** goes further: it runs `start`, `ready`, `seed`, each surface's check and `stop`
  once on the base branch in a temporary worktree, and reports each as passed or failed.
- **Init briefs** (`engine/rail/init.py`, both): ask for `[product]`, the surfaces, the agent-facing surface
  (**Agent-facing surfaces**), and one ticket per `ticket` line, filed with `rail add`. The agent lists the
  `grant` lines in its pull request for the person, as it lists today the repository settings only a person
  can change.
- **Sweep tickets** (`engine/rail/sweep.py`): after setup the sweep runs plain `rail doctor` and files a
  ticket for a `ticket` line that is new since the last sweep.
- Files: `engine/rail/doctor.py`, `engine/rail/init.py`, `engine/rail/sweep.py`, `engine/docs/product.md`.

**Kept when.** Gate cases, no model: `rail doctor` names each missing bar piece with its kind; a `mobile`
Android surface on a machine without `/dev/kvm` gives a `grant` line; `--product` runs each command once on
the base; the init briefs ask for the product, the surfaces and the agent-facing surface; the sweep files a
ticket for a new `ticket` line and none for an old one. Kept when every case behaves as written.

**Waits for.** **Product surfaces in the config**. The preview row waits for **Preview environments**; the
mobile row for **Mobile surfaces**.

**Assumed, not verified.**
- That `/dev/kvm` is a fair test for Android emulator acceleration on Linux (inferred).

#### Driving-check numbers in `rail stats`

Size: S.

**What it does.** `rail stats` shows how often the product step fails and how often it catches what nothing
else did. That second number is the measure of whether the step earns its cost.

**How.**
- One new line in `engine/rail/stats.py` and `engine/docs/stats.md`: driving-check failures per surface, and
  how many of them came after `verify` and every `Check:` line had passed on the same patch.
- The data is the `product: NAME` step events in the journal.

**Kept when.** A gate case on fixture history gives the per-surface failures and the count that followed a
passing `verify` and passing `Check:` lines. The in-use rule is in **The product step**.

**Waits for.** **The product step**.

#### Agent-facing surfaces

Size: S.

**What it does.** When a project's product has a surface built for agents (a CLI, an API, an MCP server,
markdown docs), Rail knows it, and the grill asks whether a new behaviour is exposed there. Agents are a
growing share of users: about 70% of Stripe CLI requests and 4.5 million Salesforce MCP calls in six weeks
(reported; both vendor numbers). Rail asks; it does not build one (decided by the owner, 2026-11-25). Whether
the product should have an agent-facing surface is the project's decision, made where its tickets come from.

**How.**
- `rail init` asks what the product's agent-facing surface is. When there is one, it is a surface of kind
  `agent` with its driving check.
- `engine/docs/grill.md` gains one line in "Draft first": when the project has an `agent` surface and the
  request adds behaviour users get, the draft says whether the behaviour is exposed there, and if so a
  `Check:` line drives it. This changes the contract, so it passes the grill's own test for a question (`rail
  docs grill`, "Ask only what changes the contract").
- The recipe for the surface is in **Per-surface recipes and the project's run skill**: MCP Inspector's CLI
  calls one method per run, `tools/list` or `tools/call`, with stable exit codes. A ticket that exposes
  something as a tool gets a contract test for it. A small eval of tasks a model should finish with the tools
  is recorded, not a gate (Decision below).
- Files: `engine/rail/init.py`, `engine/docs/grill.md`.

**Kept when.** Gate case, no model: the init briefs ask for the agent-facing surface. The grill line is text,
so it is marked untested until model tests run. No measure beyond that.

**Waits for.** **Product surfaces in the config** (the `agent` kind).

**Open decision.** Is the agent-facing eval a recorded score or a gate? Proposed: a recorded score. It runs a
model, so its result varies between runs.

**Assumed, not verified.**
- The Inspector CLI's flags and exit codes: its docs page is under `/docs/draft/` (reported).

#### Node for web surfaces of Go and Rust projects

Size: S.

**What it does.** A web interface is driven by Playwright whatever language serves it, so a Go or Rust project
with a web surface needs Node on the machine. The Go and Rust profiles' `provision` adds Node only when the
project has a web surface (inferred).

**How.**

- The Go and Rust `profile.toml` provision adds Node when the project has a web surface. How init detects a
  web surface is not settled; the per-surface recipes in `rail-verify` own the surfaces.
- Files: `profiles/go/profile.toml`, `profiles/rust/profile.toml`, `engine/rail/init.py`.

**Kept when.** Checked with the fixtures: a Go or Rust fixture with a web surface gets Node in `provision`,
and its Playwright driving check passes and fails when the behaviour it drives is broken (**Language fixtures
checked on a machine with every toolchain**).

**Waits for.** **Provision lines and toolchain pins per language**, and the per-surface recipes in
`rail-verify`.

#### Stats split by surface

Size: S.

**What it does.** `rail stats` gets a third split of outcomes, by the surface a ticket changed, beside `BY
WORKER` and `BY LANGUAGE`.

**How.**
- Group by the surfaces whose projects a ticket's change reached, with the same rule as the other splits: a
  group under five tickets is summed into `other`.
- What a surface is, and the paths that mark one, come from `[[surfaces]]` in the product feature that defines
  it (not built). Name that feature here when it is written.
- Files: `engine/rail/stats.py`, `engine/docs/stats.md`.

**Kept when.** A fixture with tickets on two surfaces shows two rows and a small group in `other`. Not
verified: whether such a split shows anything the language split does not; read it on real tickets before
keeping it.

**Waits for.** The feature that defines `[[surfaces]]` (not built).

**Assumed, not verified.**
- That the surface split shows something the language split does not.

### 10. Priority

A label or a front matter line that `rail next` reads before the ticket's number, so that one ticket can go
first. `proposals/team.md` describes it in its section on priority; it is as useful to one person as to a
team, and it is built from that page.

### 11. A skill that adds a tool

Size: S.

**What it does.** A `rail-tool` skill walks an agent through adding a tool: the declaration, the probe, the
name in each place, and the line in `rail.yml` for a `ci = true` key. `rail-grill` points to it when a request
needs a new service.

**How.**
- New file `seed/skills/rail-tool/SKILL.md`. `seed/skills/rail-grill/SKILL.md` points to it.
- The `[tools.NAME]` declaration itself is built (`rail docs tools`).
- Adding a tool edits `.rail/config.toml`, so it is a PERSON ticket.

**Kept when.** The skill's text passes the Rail text check; a person reads one run of it on a fixture request
for a new service.

**Waits for.** Nothing. Order of work: with the tools-on-runs item in **Numbers later decisions wait for**.

### 12. One scenario for each language, from an empty repository to a merge

Size: M.

**What it does.** One scripted run for each of Python, TypeScript, Rust and Go carries a small real project
through everything the steps above add, in one go, with the language's own toolchain. The gate cases of each
feature show that the feature behaves as written; this shows that the features work together. The owner asked
for it as the last step (2026-11-26).

**How.**

- It extends `Projects` in `tests/test_languages.py`, which today takes one small real program for each language
  from `rail init` to one merged ticket. The stand-ins play GitHub, the worker, the reviewer and the triage run,
  so it costs no model run and gives the same result every time.
- The run, for each language:
  1. `rail init` in a repository that holds only the sample project. No `[[projects]]` entry is written, and
     `rail doctor` prints the derived project.
  2. A plain AUTO ticket merges: `setup`, `verify:NAME`, the `Check:` lines, the review, the engine's merge.
  3. A ticket adds a second project in a new folder that uses the first. It is set up and checked in its own
     ship, and a later change to the first project runs both projects' checks.
  4. A ticket edits an existing test so that the old test fails on the new code. The `old-test` question is
     raised; answered `lost`, the ticket goes back to the worker, and with the behaviour restored it merges.
  5. A ticket whose scope reaches a path of a kind is built with no wait, stops at the person's merge with its
     `## Read these` list, and merges on `rail:go`.
  6. A ticket is driven to its retry cap. The `stuck` question is raised once; answered `approach`, the ticket
     starts again from the base and merges.
  7. A ticket adds a folder no check reads. The `uncovered` question is raised; answered `needs-checks`, the
     ticket `coverage:FOLDER` is filed and is PERSON.
  8. A ticket changes a project of a surface. The product is started, seeded, driven and stopped, and with the
     sample's planted fault switched on the step fails.
  9. `rail stats` shows a number for each of these: the split by project, the questions by type and answer, the
     PERSON tickets, the stuck tickets by answer, the driving-check failures.
- **Once on real GitHub.** The same run, with the same stand-ins for the worker, the reviewer and the triage
  run, in a repository on GitHub kept for such checks, for one language. It shows what the stand-in for GitHub
  cannot: the required check, the labels, the line comments of `## Read these`, an issue carried to its merge.
- **Once with a model**, when the owner restarts the model tests: the same run with a real worker, reviewer and
  triage run, two runs for each language. This is the only place where the wording of every brief is read by a
  model in the order a real ticket meets it.
- Files that change: `tests/test_languages.py`, `tests/projects/*` (a second project, a planted fault, a driving
  check script for each), `tests/fake_worker.py` and the stand-in for the triage run.

**Kept when.** No model: every step of the run behaves as written for all four languages with `python3
tests/run.py --languages`, on a machine that has every tool. On real GitHub: the one run ends with every ticket
merged or waiting where the list above says. With a model: at least six of the eight runs end the same
way; a step that fails more often names the brief whose wording is revisited.

**Waits for.** Steps 4 to 9, and every tool on the machine. A step of the run is added when its feature is
built, so the run grows with the steps and is whole after the last one. The run with a model waits for the owner
restarting the model tests.

**Assumed, not verified.**

- That the stand-ins can play each answer of the triage run without the run becoming a second copy of the gate
  cases. Each step here checks only that the ticket ends where it should.

## Waits for a condition

Each group names what has to be true before its features are built or kept. Within a group the features stand
in the order they would be built.

### The tools are on the machine

These features write or run commands of tools a machine may lack: scanners, type checkers, linters, mutation
tools. A line nobody ran is a guess, so each is built on a machine that has the tools and is checked there. A
cloud session has them when its environment's setup script installs them; a session without that script may
be refused the installs. The session of 2026-11-26 has gitleaks, pip-audit, basedpyright, govulncheck and
cargo-deny, installed by hand at the owner's word, and lacks lizard, jscpd and the mutation tools.

#### Provision lines and toolchain pins per language

Size: M.

**What it does.** `rail init` writes a `[commands] provision` into a new config, so the scanners, linters and
toolchain `verify` names are installed on a cloud machine or a CI runner without an agent writing the line.
`rail doctor` checks each profile's toolchain against its pin and each tool the profile's `verify` names.
Reason: init today writes `setup` and `verify` and leaves `provision` empty, and nothing checks a language's
compiler or its pin. The owner decided on 2026-11-25 that Rail is Python, TypeScript, Rust and Go first, not
language-neutral; a choice that makes one of the four worse for the sake of neutrality is not made.

**How.**

- Each profile's `profile.toml` (`profiles/LANG/profile.toml`) gains what installs its tools, and `rail init`
  writes it into a new config's `[commands] provision` (`engine/rail/init.py`). Init never writes a
  `provision` into an existing config. The profile's tools (ruff, basedpyright, pip-audit, oxlint, cargo-deny,
  golangci-lint, govulncheck, gitleaks) get one install line each, pinned to a version. Every line is not
  checked until its fixture runs it.

  | | Python | TypeScript | Rust | Go |
  |---|---|---|---|---|
  | Toolchain pin `rail doctor` looks for | `.python-version` or `requires-python` | `packageManager` in
  `package.json`, and `engines.node` | `rust-toolchain.toml` | the `go` and `toolchain` lines of `go.mod` |
  | Provision | uv, then the tools `uv tool install` pins | Node via the pin, corepack for the manager |
  rustup with the pinned toolchain, `cargo install --locked` for cargo-deny | the Go toolchain from the pin,
  golangci-lint and govulncheck pinned |
  | Installing runs package code? | a wheel runs none; building an sdist runs its build backend. `setup` adds
  `--no-build`, wheels only (not checked) | built: `setup` passes `--ignore-scripts` | yes, always: `build.rs`
  and procedural macros run at every build, with no switch | no: fetching and building run no package code
  (cgo compiles C the package ships, not scripts) |

  The only piece of the last row left to write is the Python `--no-build`; the rest explains why Rust has no
  switch.
- `rail doctor` (`engine/rail/doctor.py`) gains a line per profile:
  - the toolchain is on PATH and matches the pin;
  - each tool the profile's `verify` names is installed;
  - the pin file exists (missing: a ticket for the machine, since adding a pin is reversible work an agent can
    do);
  - the registry domains are in the sandbox list when the sandbox is on.
  A missing tool on a cloud machine points at `provision`; on a person's machine it names the install, which
  is the person's to run. Each profile tool could be a declared `[tools.NAME]` with its own probe (`rail docs
  tools`); until then doctor checks `command -v`.
- Files that change: `profiles/{python,typescript,rust,go}/profile.toml`; `engine/rail/init.py` (`provision`
  written into a new config; the Python `--no-build`); `engine/rail/doctor.py`; `engine/docs/languages.md`;
  `CHANGELOG.md`; `proposals`-side pointer is not needed once the page is merged into the feature list.

**Kept when.** Gate cases, no model, no toolchains, on fixture trees:

- init writes a `provision` into a new config for each profile found, and none into an existing one;
- `rail doctor` reports a missing toolchain, tool and pin, and the registry domains missing from the sandbox
  list.

Kept when every case behaves as written. The lines themselves are checked by **Language fixtures checked on a
machine with every toolchain**.

**Waits for.** Nothing for the gate cases. The install lines wait for **Language fixtures checked on a machine
with every toolchain** before they ship.

**Assumed, not verified.**

- That uv's `--no-build` and pnpm's default on lifecycle scripts behave as the table says.
- That GitHub's Ubuntu runners and Claude Code cloud machines have enough disk for four toolchains.
- That gitleaks' `git` subcommand takes `--log-opts` as written (the fixtures have not run it).

#### Language fixtures checked on a machine with every toolchain

Size: M.

**What it does.** Runs, end to end, every command line of the language features that is marked not checked, so
no profile ships a line that was never run. This is the check before the provision lines, workspace commands,
mutation wrappers and tool names are kept.

**How.**

- Run in a cloud session with all four toolchains, what the fixtures (`tests/projects/LANG/`,
  `tests/test_languages.py`) do not run yet:
  - `provision` installs what the profile names;
  - the audits (pip-audit, pnpm audit, cargo-deny, govulncheck), the secret scan (gitleaks), basedpyright and
    oxlint each fail on a planted mistake (a lockfile pinned to a version with a known advisory, a fake secret
    in a commit, a type error, a lint error) and pass again when it is removed;
  - the lines for Poetry, pip, npm, Yarn and Bun, if they are kept (open decision below);
  - the fixture's driving check from the per-surface table in **Wording about tests, for the reviewer and the
    worker** (the API, web page or CLI of its shape) passes, and fails when the behaviour it drives is broken.
- A part whose planted mistake does not fail is fixed or dropped before it ships.
- Mutation wrapper cases are listed under **Mutation score on changed lines**.

**Kept when.** No model. Kept when every case passes.

**Waits for.** A cloud session with all four toolchains installed. **Provision lines and toolchain pins per
language** for the first run.

**Open decision.** Package managers other than uv and pnpm. Proposed (and as built): their commands stay, with
no fixture. The other options are fixtures for each, or uv and pnpm only with the rest unsupported.

**Assumed, not verified.**

- That GitHub's Ubuntu runners and Claude Code cloud machines have a C compiler for Go's `-race`.
- Every command line and tool name the language features mark as not checked.

#### Complexity and duplication sensors on by default

Size: M.

**What it does.** Two language-neutral sensors, plus each language's suppression markers, ship switched on
once they pass their test. The reason: on SlopCodeBench, complexity concentrated in branchy functions rose in
77% of runs and duplicated code in 75.5%; telling the agent after each turn which changed functions were too
complex lowered erosion for all four models tested with no correctness cost detected; half of multi-turn
chains held duplicated logic by turn 5. Rail's reviewer reports style only when a rule says so, and no sensor
ships on.

**How.**
- The engine already runs any `[[sensors]]` entry (`rail docs sensors`); this feature adds the entries, tool
  configs and provisioning to the seed. Stage 1 needs no language profile.
- **Duplication (jscpd):** 50 tokens or more, new copies only:

```toml
[[sensors]]
id = "duplication"
paths = ["**/*"]                    # runs only when the change touches these
command = "jscpd --config \"$RAIL_SENSORS/jscpd.json\" --reporters xcode ."
ok_exit = [0]                       # no violations
violations_exit = [1]               # violations printed
fix = "Call the code that already does this, or move both copies into one function."
```
  jscpd v5 installs by pip, cargo, Homebrew or a standalone binary, needs no Node, and prints one clone per
  line with `--reporters xcode`. The `seed/config.toml` has this entry commented out today.
- **Complexity (lizard):** reads source text in all four languages, needs no build. It runs on the old and new
  text of each touched file. It reports a function when its span overlaps added lines, it is over the cap of
  20 after the change, and its cyclomatic count grew. Growth stands in for "the change added branches"
  (inferred). A touched legacy function over the cap does not block unless the change makes it more complex.
- **Suppression markers** added to `no-new-suppressions` (text, no tool), per language: `# type: ignore`, `#
  pyright: ignore`, `@ts-expect-error`, `biome-ignore`, `oxlint-disable`, `#[allow(`, `//nolint`. The
  `SENSOR(NN)` marker is the one way past a sensor.
- **Output.** Each sensor names a one-line format and turns off its tool's caps on repeated findings
  (golangci-lint shows 3 of a kind and 50 per linter by default).
- Thresholds: a sensor fails a ship only on code that is almost never right. Few, high values: a false
  violation that repeats reaches a person after three attempts; tight limits get gamed (agents removed an
  architecture violation by deleting the new file in 44 of 125 runs in one study; reported); some complex
  functions are legitimate. No length sensor: max-lines rules pushed complexity elsewhere, and longer files
  scored better on code questions in LongCodeBench (reported). Duplication: 50 tokens, new copies. Cyclomatic:
  20 and grew. The past-commit test tunes every value.
- Files: `seed/config.toml`, `seed/` sensor configs copied to `.rail/sensors/` by `rail init`, a `provision`
  line pinning lizard and jscpd, `engine/docs/sensors.md`, `CHANGELOG.md`. `.rail/sensors/**` is already in
  `person_paths`.

**Kept when.**
- Gate cases, no model, per sensor: a planted violation fails; a clean change passes; code that only moved
  passes; a touched legacy function the change doesn't make more complex passes; a `SENSOR(NN)` line passes
  and `SENSOR:` without a number fails; a sensor config edited on the ticket's branch has no effect; a `TODO`
  without a number fails. Kept when every case behaves as written.
- Past commits, no model: the last 200 merged commits of two active open-source projects per language pass
  through stage 1. Recorded: the share of commits that would fail per sensor, the minutes added, ten failures
  per sensor read by hand. A sensor stays in the default when it fails at most 5% of human commits, at least 8
  of the 10 read failures are a real instance of its kind, and it runs well inside `timeout_secs` (900).
- Model arms: arm A is Rail as now; arm B is A plus stage 1. Work: SlopCodeBench problems (Python, graded with
  its `scb-check`), one multi-ticket project per other language graded with lizard and jscpd, and a project's
  own merged tickets once replay exists. Measured per arm: erosion and verbosity growth, strict solve rate,
  review rounds, person waits by cause, waits whose failing step is `sensors`, review cost. B is kept when,
  against A: erosion growth is lower by a third or more, the solve rate is not lower by more than 10 points,
  person waits are not higher, and no ticket waits for a person because of `sensors`. With about 24 tickets
  per arm a rate is known to about 20 points either way (inferred), so the arms run the same tickets and only
  large differences count.

**Waits for.** The gate cases and past-commit test need no model. The model arms wait for the owner to restart
the paused model tests; arm B as a replay arm waits for replay (set aside by the owner, to be written up as
its own feature).

**Open decision.** The touched-legacy rule: fail only when a function over its cap gets more complex
(proposed), or whenever a touched function is over its cap.

**Assumed, not verified.**
- That lizard parses all four languages well enough to compare one function before and after.
- That each tool's one-line format holds for every rule turned on, and that each tool's exit codes are as
  declared (jscpd's `xcode` reporter was read in source; the others in docs).
- That git's moved-line detection can be read reliably from a diff: it is a feature of coloured output
  (`--color-moved`), and `rules.added` asks for `--no-color` on purpose.

#### Sensor sets per language

Size: L.

**What it does.** `rail init` writes a language profile into the project: that language's further sensors
(dead code, escape hatches, masked errors, boundaries, types), their tool configs and its suppression markers.
A sensor that checks what a tool can check keeps the next agent's change honest where annotations alone did
not (a blocking type checker raised correct outcomes from 1 to 11 of 12 seeded bugs in one study; type hints
with no checker made no difference in 766 runs in another; reported).

**How.** A **profile** is a language's further sensors, tool configs and suppression markers. ("Pack" stays
the word for an optional feature that only adds hints, `rail docs packs`.)
- `rail init` detects `pyproject.toml` or `setup.cfg`, `package.json` with `tsconfig.json`, `Cargo.toml` and
  `go.mod`. For each match it writes the profile's `[[sensors]]` entries into `config.toml`, copies tool
  configs to `.rail/sensors/LANG/`, adds the language's markers to `no-new-suppressions`, and adds a
  `provision` line that installs pinned tool versions. A monorepo gets one profile per language, each limited
  by `paths`. After init every file is the project's.
- Rule lists:

| | Dead code | Escape hatches and masked errors | Boundaries | Types |
|---|---|---|---|---|
| Python | Ruff F401, F841, ARG; deptry DEP001-DEP004 | Ruff S110, BLE001, E722, PGH003, ANN401 | import-linter | the project's checker, else basedpyright |
| TypeScript | knip (files, exports, dependencies) | oxlint, type-aware: no-explicit-any, ts-comment bans, empty catch, floating promises | dependency-cruiser | tsc (strict by default since TypeScript 6) |
| Rust | rustc dead_code; cargo-shear | clippy, pinned, `clippy.toml` through `CLIPPY_CONF_DIR`: unwrap_used and expect_used in library crates, let_underscore_must_use, map_err_ignore | crates and `pub(crate)`; cargo-deny bans | rustc |
| Go | golangci-lint v2 unused, unparam; deadcode; `go mod tidy -diff` | errcheck with check-blank, forcetypeassert, nolintlint with require-explanation | depguard or go-arch-lint | the compiler; go vet |

- The boundary sensor runs its tool on the rules the project keeps in that tool's own config (import-linter
  contracts, dependency-cruiser rules, a depguard list). Rail holds no map of which area may use which.
- Tool facts checked on primary sources 2026-11-24 and 2026-11-25 (reported): Ruff has no baseline mode;
  oxlint has an undocumented bulk-suppression file; Clippy reads `clippy.toml` from `CLIPPY_CONF_DIR` first
  and calls the file unstable, so the profile pins Clippy; Clippy thresholds can't be set in `Cargo.toml`.
  Rail needs no baseline mode, because it keeps only violations on added lines.
- Kinds the sensors cover: dead code added (an import, variable, parameter, export or dependency nothing
  uses); escape hatches in code (`Any`, unchecked casts, `unwrap` in library code); masked errors (empty
  catch, except-pass, an ignored error return); an import across areas the map forbids, or a new import cycle.
- Trend values, not sensors, for the measures in the thresholds table of **Trend numbers**.
- Oxlint is the TypeScript linter (owner, 2026-11-24).
- Candidate rule sets, checked 2026-11-25 on their repositories. Each enters a profile only through the
  past-commit test, rule by rule, with the same bar as any sensor:

| Rule set | What it is | Use in Rail |
|---|---|---|
| `scb-check` (gabeorlanski/scb-check, Apache-2.0) | SlopCodeBench's own checker as a CLI: `uvx scb-check check PATH --report` gives JSON with verbosity and erosion; exit 0 clean, 1 findings, 2 usage error. Its ast-grep "slop rules" and structural rules (trivial wrappers, short functions used once) are Python-only; for Rust, JavaScript and TypeScript it still reports clones and erosion. No Go | **Trend:** computes erosion as SlopCodeBench defines it for Python, JavaScript, TypeScript and Rust, and verbosity for Python only (verbosity counts its slop-rule hits; inferred from the rules being Python-only), instead of Rail recomputing them from lizard; Go keeps lizard. **Python sensor candidate:** its slop and structural rules on added lines. Its suppression marker, `# scbc ignore[`, joins the Python markers if adopted |
| `@cloudflare/oxlint-config` (Apache-2.0) | Cloudflare's shared oxlint preset, built on `@nkzw/oxlint-config`, with rules for type safety, promise handling and type-only imports. Its type-aware mode uses `tsrs`, published as a beta. The author of `dmmulroy/anti-slop` (MIT, a vendored oxlint plugin of about 20 rules: chained type assertions, `unknown` leaking through contracts, module mocking) says to prefer this preset, which adopted most of his rules | **TypeScript sensor candidate:** the profile's oxlint config extends it. Anti-slop rules the preset lacks are candidates one by one |
| `@factory/eslint-plugin` (Factory) | Factory's internal lint rules, made generic: file layout (enums in `enums.ts`), naming, tests beside each file, structured logging. Its README says not to import it but to take the ideas, and that it won't be maintained; GitHub lists it as Apache-2.0 and the README says MIT | **Ideas only.** Its rules are one team's conventions, not kinds of bad code |

- Left out: a model-judged fork of anti-slop (K-Mistele/anti-slop, MIT; "middle man", "feature envy", an
  `integrity` script): a model call per rule per ship costs more than Rail's one review, and the reviewer
  already looks for "a check weakened, skipped or deleted so that it passes". Semgrep's rules (their licence
  bars use in products and SaaS), CodeScene (paid), in-crate layering tools for Rust (young), per-language
  prose pages (models know the idioms; each sensor's `fix` line carries the advice). Newer models have
  regressed on some patterns, such as Python's `%` formatting in place of f-strings (reported): a lint rule
  catches that, and a prompt can't keep up with each model.
- One pull request per language. Files: `engine/rail/init.py` and the profile seeds, `engine/docs/sensors.md`,
  `engine/docs/languages.md`, `CHANGELOG.md`.

**Kept when.** The same gate cases as for stage 1, run per sensor and language, plus a new directory with a
new map row passing the boundary sensor. Past commits, no model: for each language, the last 200 merged
commits of two active open-source projects pass through stage 1 and the profile. Recorded: the share of
commits that would fail, per sensor and for the profile as a whole; the minutes added; ten failures per sensor
read by hand. A sensor stays in the default when it fails at most 5% of human commits, at least 8 of the 10
read failures are a real instance of its kind, and the whole profile fails at most 15% of commits and runs in
under a third of `timeout_secs` (900). Thresholds are tuned here first. Model arms: arm C is B plus the
profiles, kept on the same rule as arm B against the arm before it (erosion growth lower by a third or more,
solve rate not lower by more than 10 points, person waits not higher, no wait because of `sensors`).

**Waits for.** **Complexity and duplication sensors on by default** (stage 1 first). The model arm waits for
the owner to restart the paused model tests.

**Assumed, not verified.**
- That `scb-check` reports each finding with a path and a line, so its rules can be kept to added lines like
  any sensor (its README shows the JSON totals and source context, not a line format).
- That `tsrs`, the beta type-aware backend `@cloudflare/oxlint-config` uses, is stable enough for a default;
  oxlint's type-aware mode is young.
- That basedpyright on a project with no types doesn't flood the added lines of every change.
- The rule names and values: read on the tools' docs or source by a research agent, not run.

#### Mutation score on changed lines

Size: L.

**What it does.** After a ship passes, Rail plants small faults only in the lines the change added and counts
how many the tests catch. The score is recorded and shown in `rail stats`; it fails nothing. Reason: nothing
measures whether the tests would catch a mistake on the changed lines. There is no public number on its cost
or value for agent pull requests; mutation-style checks rejected about 20% of "solved" patches in SWE-ABS
(reported). So it starts as a measurement.

**How.**

- `[commands] mutation`, empty by default: a command the project names, run with `RAIL_BASE` set, that mutates
  only the diff against it and prints one JSON line `{"killed": K, "survived": S, "timeout": T}`.
  `engine/rail/config.py` reads the key; `seed/config.toml` documents it.
- `[commands] mutation_timeout_secs`, default 900: its own timeout.
- When: at ship, after every check passed, only when a file outside `[tests] paths` changed. With empty
  `[tests] paths` it runs whenever a source file changed.
- What it records: a `mutation` event with the counts and `patch_id`. It is no step, no attempt and no state,
  like `base_checks` (`engine/docs/journal.md`): a failure or timeout records the reason and fails nothing.
- `rail stats` adds the score (killed over killed plus survived) by month and by worker model
  (`engine/rail/stats.py`, `engine/docs/stats.md`). `engine/docs/journal.md` documents the event.
- Per-language wrappers. Each profile ships a short wrapper, written by `rail init` to
  `.rail/profiles/LANG/mutation` (the project's file afterwards), that scopes the run to the diff against
  `$RAIL_BASE`, runs the tool, reads its report and prints the line. Mutants that do not build are left out of
  all three counts. With no changed source file it prints zeros without running the tool. Each profile
  proposes the wrapper as its `[commands] mutation` default. Each tool's report format is not checked.
  `profiles/LANG/profile.toml` holds the wrapper beside the provision lines; `engine/docs/languages.md` lists
  each.

  | | Python | TypeScript | Rust | Go |
  |---|---|---|---|---|
  | Mutation on changed code | mutmut 3, scoped by module patterns built from the diff | StrykerJS, scoped by
  `--mutate` with the changed files | cargo-mutants `--in-diff` | gremlins `--diff "$RAIL_BASE"` |

  Tool behaviour the design rests on (cargo-mutants and StrykerJS read on 2026-11-25 on their whole docs
  pages; mutmut, gremlins and gremlins#301 in search excerpts only, reported):
  - cargo-mutants `--in-diff DIFF_FILE` tests only mutants overlapping the diff's changed regions, ignores
    non-Rust files, and runs nothing for a diff that only changes tests (https://mutants.rs/in-diff.html).
  - mutmut 3 has no line or diff mode. Its `run` takes wildcard patterns over mutant names, at module level;
    mutating only covered lines is a setting (`mutate_only_covered_lines`). A diff-scoped run is a small
    script that turns changed files into module patterns. A pattern matching nothing raises an error
    (reported, a September 2026 write-up), so the wrapper must not pass one.
  - StrykerJS `--incremental` reuses a previous run's report file and re-tests what changed since; it is not a
    diff against a base. Restricting `--mutate` to the changed files is the diff-scoped form
    (https://stryker-mutator.io/docs/stryker-js/incremental/; the `--mutate` form is not checked).
  - gremlins has `--diff REF`, which tests only mutants in code changed against a ref, and mutates only lines
    the tests cover. It is 0.x, made for "smallish" modules, and an open bug (go-gremlins/gremlins#301, August
    2026) skips the later edits of a hunk that holds two, silently. Go's score is the weakest of the four
    until that is fixed; the score is a trend, not a gate.
  - The Python and TypeScript wrappers mutate whole changed modules or files, so their counts include
    unchanged code in those files; cargo-mutants and gremlins mutate changed regions or lines.
- Later step, by decision, clearly separate from the rest: after 50 tickets per profile have a score, decide
  whether the surviving mutants go into the reviewer's brief as facts for "missing or weak checks", or whether
  a bar fails a ship. Neither is built until the numbers show where a bar belongs (open decision below). Until
  then the score is a number only.

**Kept when.**

- Gate cases, no model: a fake mutation command's JSON lands in a `mutation` event; one that exits 1 or times
  out fails nothing; no mutation run when only test files changed; `rail stats` shows the mutation score on
  fixture journals. Kept when every case behaves as written.
- Wrappers, no model. On each fixture, a ticket that changes one function: the profile's mutation command runs
  only mutants in that function, and a test removed from that function's suite lowers the score. Each wrapper
  prints exactly one line of JSON with the integer keys `killed`, `survived` and `timeout` and exits 0, and
  prints zeros without running the tool when no source file changed. For Go, a ticket with two edits in one
  hunk shows whether gremlins#301 still skips the second. Kept per language when both hold; a language whose
  command fails is left without a mutation score until it passes.
- In use: how much a score predicts reverts is not covered; this feature starts collecting it.

**Waits for.** The wrappers wait for the key and the event, so they come after the first paragraph of this
feature is built. Tool checks run on a machine with the toolchains (**Language fixtures checked on a machine
with every toolchain**). The later step (surviving mutants to the reviewer, or a bar) waits for 50 scored
tickets per profile.

**Open decision.** The mutation score is a number only (proposed) until 50 tickets per profile have one; then
decide whether surviving mutants go to the reviewer, and whether a bar fails a ship.

**Assumed, not verified.**

- That `cargo mutants --in-diff`, and diff-limited modes in the other languages' mutation tools, work as their
  names say. Each is checked before a profile names it.
- That each mutation tool's report can be turned into the three counts (killed, survived, timeout).

#### Rust builds across worktrees

Size: S.

**What it does.** Decides whether the Rust profile adds a compiler cache to `provision`. Each ticket has its
own worktree (`.claude/worktrees/NN`) and `setup` runs in each. uv and pnpm link from a shared cache, and Go
shares its module and build caches, so a new worktree is cheap for those three (not checked). Rust builds
`target/` from nothing in each worktree. Sharing one `CARGO_TARGET_DIR` across worktrees makes concurrent
builds wait on Cargo's lock on that folder (not checked).

**How.**

- Measure first. If Rust `setup` and `verify` dominate the time per ticket (`rail stats`, "WHERE THE TIME
  GOES"), the Rust profile adds a compiler cache (sccache) to `provision` (`profiles/rust/profile.toml`,
  `engine/docs/languages.md`).
- No shared `CARGO_TARGET_DIR`.

**Kept when.** Measured in use: sccache is added only if Rust `setup` and `verify` dominate the time per
ticket on real Rust tickets. The page sets no number.

**Waits for.** **Provision lines and toolchain pins per language**, and real Rust tickets having run.

**Open decision.** Measure first, then sccache if needed (proposed); or sccache from the start.

**Assumed, not verified.**

- That Cargo's lock on a shared target folder makes concurrent worktree builds wait, and that sccache helps.

### The owner restarts the model tests

Each of these is wording a model reads, or a behaviour only a model run can show. The owner paused the model
tests. A part that needs no model may be built before, with its wording marked as not tested; whether the
wording is kept is decided by its test.

**How a model test is run** (owner, 2026-11-27). Every model test on this page follows these rules, and a
feature's own text adds only its situations and what is graded.

- **Many situations, two runs each.** A situation is a fixture with one known right outcome: a ticket, a
  change, a request, a repository. A test has at least six, and each is run twice in each arm. Until now a
  test ran one to three situations four times each. Runs of one situation mostly agree with each other, and
  situations differ, so a wider set says more about the wording than repeats do. More certainty is bought with
  more situations, not more runs.
- **Planted and control.** Where the wording asks for a behaviour, half the situations call for it and half do
  not, so that wording which makes the model do it everywhere fails.
- **Graded by a command.** Each situation names the command that says whether a run is right. No result is
  read by hand to decide.
- **Kept over the set.** The wording is kept when it is right in at least three quarters of the runs on the
  situations that call for the behaviour, and wrong in no more than one run in eight on the controls. Where an
  old text exists it is the second arm, and the new one must also be right in more runs than the old. No single
  situation decides.
- **A situation whose two runs disagree** is named in the result. It counts as one run right and one wrong.
- **The fixtures of the gate cases are the situations** wherever a feature has them: the stand-in shows that
  the engine acts on each answer, and the model on the same fixture shows that it gives the right one.
- **The result** goes into the feature's `CHANGELOG.md` line with its counts, such as "right in 10 of 12 runs
  over six situations, the old text in 4 of 12".

Wording comes after the check that measures the same thing (owner, 2026-11-27). The pairs:

| Wording | The check built first |
|---|---|
| The worker stops on a wrong test and amends | **Old tests run against the new code** |
| The reviewer looks for output special-cased to a test's inputs | **Held-out scenarios** |
| The kinds of test the build guide lists | **Mutation score on changed lines** |
| The build guide's lines on repeated code and interfaces | **Complexity and duplication sensors on by default** |

A line of wording is built once its check has run on real changes, and it is kept only when its model test
shows it moves the number the check reports.

Two tests that belong to no single feature also wait here:

- **Init with a model.** Eight real repositories, two for each language, none prepared for Rail; `rail init`
  with the language profiles against init as the seed first wrote it, two runs each. Graded: each part of
  `verify` (tests, lint, types, format, secret scan, audit) is present and shown to fail on a planted mistake,
  and `verify` is the same in both runs. Kept when the profile arm covers at least as many parts as the other
  arm in every repository and gives the same commands in both runs for at least six of the eight. The wording
  of the init task stays untested until this runs.
- **Language-specific review lines.** None at first (proposed): a finding that repeats in one language becomes
  a sensor or a rule, not a line in the reviewer's brief.

#### Wording about tests, for the reviewer and the worker

Size: S.

**What it does.** Four pieces of wording: the reviewer is told to look for output special-cased to a test's
inputs; the worker is told to stop on a wrong test and amend the contract; the build guide lists the kinds of
test that catch real mistakes; and the seed's skills name the test and driving-check tool per language. The
first two are cheap help, not guards: the same kind of line cut cheating from 93% to 1% on one benchmark and
only from 66% to 54% on another. **Old tests run against the new code** is the guard.

**How.**

- Reviewer look-for list (`REVIEW_LOOK_FOR` in `engine/rail/review.py`) gains one line beside the one about
  weakened checks: "output special-cased to a test's inputs, or code that detects it runs under test".
  `reviewer.md` is unchanged.
- `engine/guides/build.md`, section 2 ("Run every check now"), gains one line:

  > **It is wrong:** it contradicts the `## Why`, or no correct change can pass it. Say so and amend the
  contract with `rail amend NN "why"`. Never make it pass by special-casing its inputs, by editing a test to
  match your code, or by detecting that it runs under test.

  Consult's `stop` line already says a plainly wrong check is the agent's to amend (`CHANGELOG.md`), so the
  two agree.
- `engine/guides/build.md`, section 4 ("Test where behaviour is visible"), gains a short list of kinds of
  test, each with when it applies. The guide names no tool; the tool for each language is in its profile
  (`rail docs languages`):
  - Property tests for parsers, encoders, round trips and invariants. Above all for stored data shapes, which
    a revert cannot undo (`rail docs kinds`).
  - Idempotency as a property: running it twice changes nothing. For handlers, jobs and migrations.
  - Differential tests for a rewrite: the old and the new code on the same inputs, compared. For a service,
    the same recorded requests sent to both.
  - Fuzzing for code that reads input from outside.
  - A real database in tests, started for the test, not a mock of it.
  - A migration run up, down and up again.
  This list is practice with no cross-study success rate.
- Tool names per language for the seed's skills (`seed/skills/rail-verify/SKILL.md`, and the seed's build
  skill where the guidance on tests lands). All names are not checked until the fixtures run them (**Language
  fixtures checked on a machine with every toolchain**).

  | | Python | TypeScript | Rust | Go |
  |---|---|---|---|---|
  | Property tests | Hypothesis | fast-check | proptest | rapid (`pgregory.net/rapid`), or `testing/quick` |
  | Fuzzing | Hypothesis (no separate fuzzer by default) | fast-check | cargo-fuzz (needs nightly Rust) | `go
  test -fuzz` (built in) |
  | Real database in tests | testcontainers | testcontainers | testcontainers (Rust crate) | testcontainers-go |

  | Surface | Python | TypeScript | Rust | Go |
  |---|---|---|---|---|
  | Web interface | Playwright (its Python package) | Playwright Test | Playwright Test against the built
  server | Playwright Test against the built server |
  | HTTP API | requests from pytest against the running server; Schemathesis on the schema | requests from
  Vitest against the running server | the built server and a client in an integration test | the built binary,
  and `net/http` requests from a test |
  | Command line | the installed entry point run in a temporary folder from pytest | the built CLI run from
  Vitest | assert_cmd on the built binary | testscript (`rogpeppe/go-internal`) |
  | Agent-facing (MCP) | the official Python SDK's client | the official TypeScript SDK's client, or MCP
  Inspector | the official Rust SDK | the official Go SDK |

  The Blender and video examples stay out of the per-language tables. The guidance on kinds of test and the
  per-surface recipes in `rail-verify` do not exist yet; the tool names go in once they do.
- Files that change: `engine/rail/review.py`, `engine/guides/build.md`, `seed/skills/rail-verify/SKILL.md`,
  `CHANGELOG.md`.

**Kept when.** Model tests, wording untested until they run. Each is the old text against the new, by the
rules at the head of this group.

- Worker line: tickets with a `Check:` that contradicts the `## Why` (an impossible ticket), and controls
  whose checks are right. Kept when, on the impossible tickets, the new text amends in at least three quarters
  of the runs and makes the check pass by special-casing in none, and on the controls it amends no more often
  than the old text.
- Reviewer line: changes that special-case a test's inputs, and plain controls. Kept when the reviewer blocks
  the planted ones in at least three quarters of the runs and raises a new blocking finding on the controls in
  no more than one run in eight.
- Kinds-of-test list: tickets where a property, idempotency or differential test fits (a parser, a handler, a
  rewrite), old and new `build.md`. Kept when the new text writes such a test in at least three quarters of the
  runs and the mutation score on those tickets is not lower.

**Waits for.** The owner restarting the paused model tests, and for each line the check that is built first:
the worker's line waits for **Old tests run against the new code**, the reviewer's line for **Held-out
scenarios**, and the kinds-of-test list for **Mutation score on changed lines**, whose score its test uses. The
tool-name tables wait for the kinds-of-test guidance and the per-surface recipes in `rail-verify` to be
written.

**Assumed, not verified.**

- Every tool name and command in the tables above is not checked.

#### Build and debug guide wording

Size: S.

**What it does.** Section 5 of `rail-build` keeps its reuse list and gains lines only for what no sensor
checks, and `rail-debug` and the grill page get one or two lines each. The guide changes on evidence, like any
guide: the old page against the new on the same requests.

**How.** Proposed text, replacing the `Abstraction`, `Place` and `You notice a problem` lines of
`seed/skills/rail-build/SKILL.md` section 5:

> - **Repeated code:** a run of 50 tokens or more that already exists fails the duplication sensor. Call the
code that exists, or move both copies into one function. Shorter repetition, such as wiring, may stay.
> - **Interfaces:** before you add or change an interface (an exported function or type, a CLI flag, a config
key, a file format, an endpoint), find its callers. Give it the parameters and options they use, and what the
Done Contract asks for.
> - **Pass-throughs:** a new function or module hides work from its callers. When it only hands a call on,
call the target directly.
> - **Names:** one name for one concept, the same in every layer. A name says what the thing is or does; long
and specific is fine.
> - **Found by search:** write each use of a name so that grep finds it: spell identifiers out where they are
used, and register a handler where the registry is. Where the codebase registers by decorator or init
function, follow its pattern.
> - **Place:** put code in the area whose `Holds` names its concept. Logic for one feature lives with that
feature, not as a branch inside a shared flow. When several callers share a fault, fix the shared code.
> - **You notice a problem the ticket didn't ask about:** leave it, and write a `Noticed:` line in `## Look at`.

- Section 7 step 4 of `rail-build` adds: "Write a `Noticed:` line for each problem outside the ticket."
  Section 3 loses its `rail context` line once the brief carries the context history (built). Counted: 97
  lines today, 7 bullets for 3 (about +12), sections 3 and 7 (about -1): about 108 lines, slightly over the
  guide rule's "about a hundred" (`rail docs guides`).
- `seed/skills/rail-debug/SKILL.md` gains two lines. Step 4: "Write each explanation you ruled out under `##
  Tried` in the ticket." Step 7: "A sensor is wrong on one line: mark it `SENSOR(NN): why`. Wrong in general:
  open a ticket that changes `.rail/sensors/`." This sits beside the existing rule for a wrong `Check:` (`rail
  amend`), which stays: a `Check:` is the contract, a sensor is not.
- `engine/docs/grill.md`, which the `rail-grill` skill and chat bots follow, gains one line in its section 3,
  "Ask only what changes the contract": "Ask first about what would be expensive to change later: a database
  schema, a stored or wire format, an interface other code calls. A choice that is cheap to change later, such
  as wording or a colour, is an `ASSUMED:` row, not a question." The measure is the chance of rework times the
  cost of the change (reported, Horthy). The grill keeps its cap of five questions.
- How pages are written stays as `rail docs guides` says: no persona (no gain in any study found), no capitals
  for emphasis (emphasis makes models over-apply a rule), a reason with each rule, the wanted behaviour
  stated, effort set by the worker ladder rather than "think hard".
- **Ownership-sentence arm.** Anthropic's page for Fable 5.2 reports that the sentence "You are the owner and
  long-term maintainer of this codebase" made it merge duplicated code in about 75% of runs against under 10%,
  at 70-80% more output and some unrequested changes (reported). It is a test arm only: it was measured on
  Fable, and Rail's workers run on Sonnet 5.5 and Opus 5.5. It is not added to any brief unless it passes the
  rule below.

**Kept when.** Model arms (same tickets in every arm, so each ticket is compared with itself): arm D is C plus
the text above; arm E is D plus the design sweep and the collections; and one further arm is D plus the
ownership sentence added to the brief, on the same worker models. Work: SlopCodeBench problems (Python, graded
with `scb-check`), one multi-ticket project per other language graded with lizard and jscpd, and a project's
own merged tickets once replay exists (a replay arm can't add engine code, so arms B to E run as replay arms
only once their parts are in the project's engine behind a config key). Measured per arm: erosion and
verbosity growth, strict solve rate, review rounds, person waits by cause, waits whose failing step is
`sensors`, review cost, and worker cost (once `rail work` records it). A part is kept when, against the arm
before it: erosion growth is lower by a third or more; the solve rate is not lower by more than 10 points;
person waits are not higher; and no ticket waits for a person because of `sensors`. The ownership sentence is
kept on the same rule, and when it adds no more scope amends or split offers than arm D.

**Waits for.** **Complexity and duplication sensors on by default**, which is built first and reports the
numbers this wording has to move; **Sensor sets per language** (arm C); the owner restarting the paused model
tests; and replay for replay arms (set aside by the owner, to be written up as its own feature). For the arm E
part, **The sweep gathers what tickets leave behind**.

#### Findability probe

Size: M.

**What it does.** The sweep measures whether the next agent can find its way in an area: for up to five
tickets merged since the last sweep, a fresh agent gets only the ticket's `## Why` and the repository at the
ticket's base, and names the files it would change. The score is its overlap with the files the ticket
changed. A falling score per area means the next agent can no longer find its way there. The merged diff is
the answer key, so no person grades it (inferred). It costs up to five model runs per sweep. Names and
interface design have no sensor; the probe and the trend are how their effect is seen. Obfuscated names cut
model code understanding by 10-30 points across studies, and success falls steeply with the number of files a
change spans (reported).

**How.**
- In the sweep, after the numbers: pick up to five merged tickets, check out (read) the base tree of each, run
  a fresh agent with the ticket's `## Why` only, record the files it names, and score the overlap with the
  ticket's changed files. Store the score per area in the `trend` event.
- Optional: built only if the pilot passes and the owner decides to keep it.

**Kept when.** Pilot: two runs on each of three areas as they are, and two on a copy of each with identifiers
renamed to placeholders and one module's logic spread over three files. Kept when the damaged copy scores
lower in at least five of the six pairs. This uses models.

**Waits for.** **Trend numbers**, and the owner restarting the paused model tests.

**Open decision.** Build the probe after its pilot, or not at all (proposed: after its pilot).

#### Per-surface recipes and the project's run skill

Size: M.

**What it does.** `rail-verify` tells the agent, for each kind of surface, what to drive, what to keep as
evidence, how to prove the check can fail, and what agents most often fake there. It also writes a project
skill that says how to start, seed, stop and drive each surface, so a session with no ticket uses the same
procedure. Today section 3 of `rail-verify` asks for "one check that drives it the way a user would", with a
Blender add-on and a video pipeline as examples. Those go: Rail is for software (decided by the owner,
2026-11-25).

**How.**
- `seed/skills/rail-verify/SKILL.md` keeps its five sections. Section 3, "Drive the real product", drops the
  Blender and video examples and gains one recipe per surface. Each recipe says what to drive, what to keep as
  evidence, its negative control (break the behaviour on purpose, see the check fail, restore it), and what an
  agent most often fakes. A profile in `rail docs languages` gives the variant per language (Python,
  TypeScript, Rust and Go first).

| Surface | Driving check | Evidence | What gets faked |
|---|---|---|---|
| Web | A Playwright script against the running app, as the seeded user, with deterministic assertions on what the page shows. An agent clicking through found the same bug in some runs and missed it in others for 22-28% of scenarios (reported, Waterloo seminar abstract), so an agent's exploratory pass is extra and repeated, never the check | Screenshots or a trace, the steps | Claiming done without opening the page; calling the API instead of clicking |
| HTTP or RPC API | Real requests with assertions (Hurl, curl, grpcurl); responses checked against the schema (Schemathesis, against a local or preview instance only, since it sends many invalid requests, reported). For a rewrite, the same requests to old and new, compared | Each request and response | Mocking the thing under test |
| Command line | The built binary on real files in a temporary folder, error cases and exit codes included. Snapshot tools that an agent can rewrite in one command (`TRYCMD=overwrite`, reported) count as changed tests | Command, output, exit code | Testing the library and never the binary; accepting new snapshots of broken output |
| Agent-facing | MCP Inspector's CLI (see **Agent-facing surfaces**). A ticket that exposes something as a tool gets a contract test for it. A small eval is recorded, not a gate | The calls and results; the eval score | Testing the handler and never the tool as an agent sees it |
| Data job | The whole job on a real sample into a dev schema, with data-contract checks; then replayed with late, duplicate and out-of-order input, and run twice to show it is idempotent. Replaying found 7.0-79.2% of snapshot-certified pipelines silently wrong (ArrivalBench, arXiv 2610.02363, reported) | Row counts, sample rows, contract results | One clean run taken as proof |
| Integration with a third party | The provider's test mode; a retry test and an idempotency test; secrets from the environment, tokens scoped | Requests, responses, the retry run | A mock of the provider standing in for its test mode |
| Mobile | See **Mobile surfaces** | | |

- Web, API, CLI, data job and integration come first, then agent-facing; mobile is last.
- **The project's own run skill.** When `rail-verify` finishes, it also writes a project skill that says how
  to start, seed, stop and drive each surface, generated from `[product]` and `[[surfaces]]`. Claude Code's
  built-in `run` skill "first looks for a project skill that already covers launching the app" (its
  description in a session's skill list, 2026-11-25). The config stays the source and the skill is generated
  from it: the engine reads the config, not the skill, so the two cannot disagree in what the engine does, and
  `rail-verify` writes the skill again whenever it changes `[product]` or `[[surfaces]]`. A project skill
  named like a built-in one may shadow it; whether Claude Code has a built-in `/verify` skill was not checked.
- Files: `seed/skills/rail-verify/SKILL.md`.

**Kept when.** A model test (this uses models). For each of web, API, CLI, agent-facing and data job, a
fixture project with no driving check and a hidden fault the recipe's check should catch, and a second
fixture for each surface where one is cheap to write. Two runs for each fixture with the new skill and two
with today's. Kept when the new skill's check catches the hidden fault in at least three quarters of the runs,
its negative control was run in at least three quarters (seen in the transcript), and it does worse than
today's on no surface. In use, per **The product step**: a quiet surface's recipe
is revisited after 50 tickets.

**Waits for.** The owner restarting the paused model tests. Until then the recipes are built and their wording
is marked untested (decided by the owner, 2026-11-26: a step that needs model runs builds its deterministic
part and marks its wording untested). **Product surfaces in the config** for the generated skill. The skill's
name waits on the pilot.

**Open decision.** What is the project skill's file name? It must be one that Claude Code's `run` skill finds,
without shadowing a built-in skill. Proposed: `run-product`, checked in the pilot.

**Assumed, not verified.**
- That the built-in `run` skill finds a project skill by its description, not only by its name.
- Whether Claude Code has a built-in `/verify` skill: not checked.

#### The contract writer's tier

Size: S.

**What it does.** Ticket lint already fails a PERSON ticket whose `person_reason` has no known kind, and the
`rail-blast-radius` guide names the kinds. Not tested: whether the contract writer, given a request, picks the
tier and kind the rule needs. Wording is in the guide and the brief; no model run has checked it. This feature
is the test, and the wording fix it leads to.

**How.**
- Intake cases, some that hold a kind (`rail docs kinds`) and some that do not.
- Run at `[worker] contract`, at least six cases, two runs for each.
- If a case fails, fix the wording in `seed/skills/rail-blast-radius/SKILL.md` and the contract brief, then
  run again.
- Not covered: whether the list of kinds is complete for every project (`rail init` asks per project); harm
  from a change that can be undone but costs users while it is live (the dev smoke check and the revert are
  the defence); secrets a ticket branch reaches, which `ci = true` keys bound and no tier can.

**Kept when.** Model test: kept when the tier and `person_reason` match the case in at least three quarters of
the runs on the cases that hold a kind, and a kind is named in no more than one run in eight on those that do
not. In
use, over 50 AUTO tickets merged: if any is counted under "AUTO tickets that held a kind" in `rail stats`, the
kind's detection (paths, the reviewer's text, or the contract writer's guide) is revisited before anything
else.

**Waits for.** The owner restarting the paused model tests.

**Assumed, not verified.**
- That dropping an AUTO ticket at the cap loses no work a person would want: the branch is deleted, and the
  closed pull request's commits and the drop mark remain. Whether a relabelled issue's new ticket should start
  from those commits is not designed here.

#### `caused_by` in the contract brief

Size: S.

**What it does.** The brief that asks an agent to write a ticket's contract tells it to name the ticket that
caused a bug. More merged tickets then carry `caused_by`, which `rail stats` counts as a measure of how often
a merged ticket causes a fix. The coverage line in `rail stats` already shows whether it works.

**How.**
- `caused_by` is set today by intake for a deploy issue that starts with `Commit:` (`engine/rail/cli.py`), by
  a revert ticket, and by an agent that writes it (the sweep brief says to). The `TICKET_LINT` brief in
  `engine/rail/table.py` does not mention it.
- Add one line: when the request is a bug in code a merged ticket wrote, find that ticket (the squash commit
  of the failing lines, `git log -L` or `git blame`, and its `Ticket:` trailer) and set `caused_by`.

**Kept when.** Model test, two runs for each case. At least three fixture bug requests where blame leads to a
merged ticket, and as many controls where the bug predates Rail. Kept when `caused_by` is right in at least
three quarters of the runs on the first and empty in all but one run in eight on the controls. Wording is
untested until then.

**Waits for.** The owner restarting the paused model tests.

#### The runner calls `rail work`

Size: M.

**What it does.** The runner prompt stops asking a runner to choose a model, reuse a subagent and avoid `rail
advance`. It runs `rail work NN` and lets the engine start the worker, so the worker's cost is recorded and
each choice is the engine's. A pilot on real tickets sets the default limits.

**How.**
- Today the runner prompt (`engine/docs/cloud.md`, "Run with no session open", and `README.md`) tells the
  runner to read `action.model`, decide whether to reuse a subagent, start it, and not run `rail advance`
  (confirmed: step 2 of the list in `cloud.md`). `seed/AGENTS.md` says the same to a session nobody drives.
  The cost of a worker started that way is not recorded.
- New step 2: "If `action.kind` is `agent_task` for a ticket, run `rail work NN --json` with a timeout of 120
  minutes. When it ran a worker, run `rail advance NN --json`. If it ran nothing, do the brief it returned
  with a subagent, then run `rail advance NN --json`." The runner no longer picks models or reuses subagents
  for a ticket's work.
- A session a person drives is unchanged: it does the brief itself, and its cost is not recorded (`rail stats`
  says the worker cost covers `rail work` runs only).
- A source's brief (`rail source NAME`) is not a ticket's and stays as it is.
- Files: `engine/docs/cloud.md` and `README.md` (the prompt, and the paragraph after it, "One worker carries a
  ticket ...", which describes subagents); `seed/AGENTS.md` (its lines on starting a subagent and running
  `rail advance` for the brief); `seed/config.toml` and `engine/rail/config.py` (the `[worker]` command and
  limit values, once the pilot has set them). The skills that say "run `rail advance`" (`rail-build`,
  `rail-findings`, `rail-conflict`) stay as they are: a session a person drives still runs it, and inside a
  worker run the added brief line and the refusal say otherwise.
- Default limits in the seed now, a first guess that was not tried on real tickets: 300 turns, $15 and 90
  minutes per run, $40 per ticket, no daily limit. The Claude Code flags behind them were read on the docs,
  not run through a runner.
- The open decision below.

**Kept when.**
- Gate case, no model: a fixture checks that the prompt in `engine/docs/cloud.md` and `README.md` names `rail
  work NN --json` and the 120-minute timeout. Wording is untested until the pilot.
- Pilot, with a model: three real tickets in a cloud session through the runner with `rail work`, one that
  merges, one that fails a check once, one with a review finding. Recorded: a `worked` event per run with a
  cost; the guard hook ran inside the worker (a canary: the ticket asks the worker to run a command the guard
  denies, and the denial is in its transcript); the claim stayed with the runner through a run longer than 30
  minutes (the third ticket's worker is asked to wait); a resumed session kept its context (the second run
  does not re-read files the first read). Kept when all of these hold on all three tickets. The pilot's
  numbers set the default limits and decide whether `daily_usd` is on by default.

Not covered: the cost of a session a person drives, and of consult; another vendor's CLI (the command is open
to it, and no one has run one); whether the default values suit real tickets.

**Waits for.** The owner restarting the paused model tests (the pilot uses models and a cloud session). The
Bash variables from **Numbers later decisions wait for**, so a runner can pass a timeout above 30 minutes in a
session whose settings do not load. Order: provision change first, then the pilot, then the prompt,
`seed/AGENTS.md` and the seed command values.

**Open decision.**
1. The default limits (300 turns, $15 and 90 minutes per run, $40 per ticket, no daily limit). The pilot
   decides whether they stay.
2. Whether `daily_usd` is on by default for an unattended runner. The pilot decides.
3. Whether `rail next` answers with `script: rail work NN` itself, so the runner needs one rule fewer.
   Proposed: no, while a session a person drives still does the brief itself and needs `agent_task`.

**Assumed, not verified.**
- That a child `claude -p` in a worktree applies the worktree's `.claude/settings.json` allow rules. The docs
  say project allow rules apply only once the folder is trusted, and that `-p` shows no trust dialog; how the
  two meet was not found (reported). The pilot shows it.
- That `RAIL_WORKER`, set by `rail work`, reaches the child's Bash tool and its hooks (inferred: a child
  process inherits its parent's environment, and Claude Code passes its own to the commands it runs).
- That auto mode is available for `-p` on the account the runner uses (the docs list the eligible models and
  plans; reported).
- That the child's own Bash calls run in the sandbox when `rail work` itself is excluded from it, on a
  person's machine (inferred: the child applies its own settings).
- That a resume on a new machine fails the way the engine expects (the engine then runs once more fresh; `rail
  docs loop`). The fake worker in the tests stands in for the CLI.

#### Read-only tools for the review seats

Size: M.

**What it does.** The reviewer, the refuter and consult can call a tool server declared `review = true` in a
`[tools.NAME]`. Today they run with `--safe-mode`, which ignores an explicit `--mcp-config` (tested locally
and in the cloud on 2026-11-24), so such a tool reaches their brief as text and never as a server they can
call.

**How.**
- The engine writes an MCP config holding only the `review = true` servers from `.mcp.json` to the cache and
  sets `RAIL_MCP_CONFIG` before every review, refuter and consult run. It points to an empty server list when
  no tool has `review = true`.
- The seed's review, refuter and consult commands change from `--safe-mode` to `--setting-sources ""
  --disable-slash-commands --strict-mcp-config --mcp-config "$RAIL_MCP_CONFIG"`, keeping the other flags they
  have (the review command already takes `RAIL_REVIEW_PROMPT` and `RAIL_REVIEW_SCHEMA`).
- Tested on 2026-11-24 (Claude Code 2.1.292) with canaries: these flags loaded no CLAUDE.md, project skill,
  plugin or project hook, as `--safe-mode` does, and did load the server. That is a tested result, not
  documented behaviour, so the pilot checks it again on the version in use.
- The command stays agent-neutral: the engine sets a variable, the command chooses its flags.
- Files: `engine/rail/config.py`, `seed/config.toml`, `engine/rail/review.py`, `engine/rail/consult.py`,
  `engine/docs/tools.md`.
- Adding or changing a tool edits `.rail/config.toml`, so it is a PERSON ticket. Granting the machine a key is
  a person's act (`engine/docs/environments.md`).

**Kept when.**
- Gate case, no model: the review, refuter and consult commands get `RAIL_MCP_CONFIG` (with the review
  command's other variables), with an empty server list when no tool is `review = true`; the file holds only
  `review = true` servers.
- Cloud pilot, with a model: one tool reached through a network secret with a probe, one `review = true` MCP
  server. The worker uses the tool; the reviewer sees the server and no project hook (a canary, as on
  2026-11-24); breaking the secret gives a failing probe and a grant wait, with no attempt spent. Wording
  stays untested until then.

**Waits for.** The owner restarting the paused model tests (the pilot). Built after the cloud pilot. Related:
**A skill that adds a tool**.

**Assumed, not verified.**
- That the replacement flags keep loading only the server on later Claude Code versions.

### Real tickets have run

Each of these needs numbers from use before it is built, or before the decision in it can be made: journals of
merged tickets, `rail stats`, pull requests a person commented on. The numbers start with the first tickets a
runner carries through on a real repository; step 2 above adds the ones not yet counted.

One measure belongs to no single feature: after 20 merged tickets in each language, the split by language in
`rail stats` is read, and a language whose reverts or cost for each merged ticket are twice the others' gets a
ticket on its profile.

#### Trend numbers

Size: M.

**What it does.** The sweep stores per-area numbers in a `trend` event, so the next sweep and `rail stats` see
slow decay that no single change shows. Erosion is SlopCodeBench's measure: the share of complexity
(cyclomatic x square root of lines) held by functions above 10.

**How.**
- The trend commands (lizard, jscpd, each profile's own) report per area the measures below, sensor-rule
  counts over the whole tree, and `SENSOR(NN)` markers.
- From the journals the engine adds, per area: files and areas changed per merged ticket, failed steps and
  review rounds, and the worker's cost once `rail work` records it (today only review runs carry `cost_usd`,
  `steps.py`).
- The sweep writes one `trend` event per sweep (document the fields in `rail docs journal`), and `rail stats`
  shows the change since the last one.
- Trend thresholds (usual textbook values feed the trend; sensors use only the high ones):

| Measure | Counts | Usual defaults | Sensor | Trend |
|---|---|---|---|---|
| Cyclomatic complexity (lizard) | paths: 1 + each branch, loop, case, `and`/`or` | 10 (McCabe, Ruff), 15 (lizard), 20 (ESLint) | 20, and grew | over 10 counts toward erosion |
| Cognitive complexity | how hard a function is to follow; nested branches weigh more | 15 (Sonar, complexipy), 25 (Clippy), 30 (gocognit) | none | over 15, where the language has a tool |
| Nesting depth | blocks inside blocks | 4 (ESLint), 5 (nestif, Ruff) | none | over 5 |
| Parameters | arguments of one function | 3 (ESLint), 5 (Ruff), 7 (Clippy) | none | over 5 |
| Function length | lines | 50 (ESLint), 60 (funlen), 100 (Clippy) | none | over 100 |
| File length | lines | 300 (ESLint), 1000 (pylint) | none | over 1000 |
| Duplication (jscpd) | a repeated run of tokens | 50 tokens / 5 lines | 50 tokens, new copies | duplicated share |

- Also tracked per area: duplicated share, dead code totals, long functions and files, deep nesting, many
  parameters.
- Trend source for erosion and verbosity: `scb-check` where adopted (see **Sensor sets per language**), lizard
  for Go.

**Kept when.** The trend has no rule of its own: it is kept while the sweep reads it.

**Waits for.** **Complexity and duplication sensors on by default** (lizard, jscpd), **Sensor sets per
language** for each profile's own commands, and the worker's cost recording by `rail work` for the cost column
(the worker-cost part is set aside; leave it out until `rail work` records it).

**Assumed, not verified.**
- The cost of the design sweep's model run over the areas that changed in 20 tickets.

#### Refactor tickets from the sweep

Size: M.

**What it does.** The sweep files refactor tickets for design cost that no tool measures, each with evidence
and a `Check:` that fails before the refactor and passes after.

**How.**
- Each ticket names a kind from this list (pass-throughs, options no caller uses, leaky interfaces, misleading
  names, code that search can't find, a concept in the wrong area, a special case in a shared flow, or any
  trend kind), with evidence (tool output, or two `file:line` places) and its cost (the next correct change is
  slower or riskier than the problem requires).
- Its `Check:` lines are the tests plus a threshold command that fails before the refactor and passes after.
- At most `[sweep] max_refactor_open` (3) refactor tickets are open at once, as sources cap theirs with
  `max_open` (`rail docs sources`); the rest stay in the summary with their numbers.
- A refactor over `[size] cap` is offered a split like any ticket.
- A kind that keeps returning gets a "make it a check" ticket. When that check is a sensor or rule in
  `.rail/config.toml`, the ticket is PERSON, as such tickets are today.
- Files: `engine/rail/sweep.py`, `engine/rail/config.py` (the new key and its default),
  `engine/docs/sweep.md`, `engine/docs/config.md`.

**Kept when.** From the journals: refactor tickets that merge, and whether the kind's trend number falls over
the next sweeps. No other rule is set.

**Waits for.** **The sweep reads reviewed merges** and **Trend numbers**.

**Open decision.** The cap as "open at once" (`max_refactor_open`, proposed) or "per sweep".

#### `rail stats --forge`

Size: S.

**What it does.** `rail stats` reads only the journals and the base branch's history, and line comments live
on GitHub. `--forge` also reads each merged ticket's pull request comments, so the numbers show whether a
person's attention lands on the lines `## Read these` lists. Without `--forge` these lines are left out.

**How.**
- On PERSON tickets: the person's line comments per ticket (unmarked ones, those with no
  `SHORTCUT`/`TODO`/marker form), and the share that fall on a "Read these" item.
- On tickets reverted afterwards: whether the reverted lines held an item.
- Files: `engine/rail/stats.py`, `engine/rail/forge.py` (the comment reads), `engine/docs/stats.md`,
  `CHANGELOG.md`. I found no `forge` in `stats.py` or `docs/stats.md` today.
- Not covered: how long a person takes per pull request (GitHub doesn't report reading time); whether a person
  reads the items or the whole diff; forges other than GitHub.

**Kept when.** Gate case, no model: `rail stats --forge` reads line comments from a test repository; without
`--forge` those lines are left out. In use, from the journals, over 20 PERSON tickets: when fewer than half
the person's line comments fall on items, the sources of the list are revisited.

**Waits for.** Nothing. The in-use measure waits for 20 PERSON tickets with `## Read these` in place.

#### Whether a reviewer's request still makes a ticket PERSON

Size: S.

**What it does.** The reviewer's `kinds` can raise an AUTO ticket to PERSON today (`rail docs review`). This
decision is whether it keeps doing so once there are numbers on what the person's review adds.

**How.**
- Nothing is built until the decision. The proposed answer: decide on the numbers in `rail stats` once it has
  20 PERSON tickets raised this way, with `## Read these` in place. Size raises no tier any more.
- If the owner ends the raise, its cases are no longer routed to a person before merge; the reviewer's `kinds`
  field and `rail docs review` change to match, and `rail docs kinds`.
- Do not route those cases to a reviewer `attention` field: the owner dropped that field.

**Kept when.** The decision rests on 20 such tickets in `rail stats`: how many of the person's line comments
fall on "Read these" items and how many of those tickets the person changed or sent back.

**Waits for.** 20 PERSON tickets that the reviewer raised, with `## Read these` in place; **`rail stats
--forge`** for the comment numbers.

**Open decision.** Whether the reviewer's request keeps making a ticket PERSON. Proposed: decide on those
numbers.

#### Claims by changed files

Size: M.

**What it does.** A project can let a ticket rest only while its scope overlaps files an open ticket has
already changed, instead of the whole scope of that ticket. Today one ticket scoped `src/**` holds back every
ticket under `src/` until it merges or is dropped, review, CI and the wait for its merge included.

**How.**
- Today an accepted ticket whose `scope_paths` overlap those of any open ticket (implementing, reviewing, in
  CI, merge-ready: `OPEN` in `engine/rail/state.py`) rests as `SCOPE_OVERLAP` (`engine/docs/tickets.md`).
  Overlap is judged glob against glob (`engine/rail/util.py`). `rail stats` already reports how long tickets
  rest this way ("accepted to claimed" and "behind a ticket with an overlapping scope").
- Config key `[claim] overlap = "scope"` (today's rule, the default) or `"changed"`. With `"changed"`, a
  ticket rests only while its `scope_paths` overlap files an open ticket has already changed
  (`Project.changed_files` in `engine/rail/project.py`), not that ticket's whole scope.
- A ticket can only change files in its own scope, so two tickets collide only when both change the same file.
  That shows at the second one's rebase as a conflict, which already has its brief (`CONFLICT`). So
  `"changed"` trades rests for an occasional conflict.
- Rule for switching the default: when `rail stats` shows that accepted-to-claimed time behind an overlapping
  ticket is over a quarter of request-to-merge time across 30 merged tickets, and conflicts at rebase stay
  under one in ten tickets in a trial with `"changed"`. Both numbers are guesses for the owner to set (open
  decision below).
- Files: `engine/rail/state.py` (`derive`), `engine/rail/config.py`, `seed/config.toml`,
  `engine/docs/tickets.md`.

**Kept when.** Gate cases, no model (fixture projects, `tests/fake_gh.py`): with `overlap = "changed"`, two
tickets with overlapping scopes and different changed files both claim; the same file changed by both gives a
conflict at the second rebase; `"scope"` keeps today's rest. The default switch needs the numbers above from
real tickets. Built after those numbers from `rail stats`, with the load test.

**Waits for.** Real tickets: 30 merged tickets for the switching numbers. **A load test on real GitHub** is
run before and after.

**Open decision.** The numbers for switching `[claim] overlap` to `"changed"`: a quarter of request-to-merge
time resting, conflicts under one in ten (proposed).

#### One rebase at a time

Size: M.

**What it does.** When several shipped tickets are behind the base, the engine rebases only the one that will
merge next. Today the ruleset requires branches to be up to date, so each merge puts every other shipped pull
request behind, each is rebased with no agent work, and CI runs again for each. With K tickets shipped and
waiting, merging them one by one can start about K(K-1)/2 extra CI runs (inferred).

**How.**
- Engine rule: rebase only the ticket that will merge next (lowest ID among the green ones, else the lowest
  ID), and leave the rest behind until it merges. CI then runs about once per ticket per merge instead of once
  per ticket per earlier merge (inferred).
- Today this is the `REBASE_BEHIND` row of `engine/rail/table.py` (`engine/docs/github.md`). Files:
  `engine/rail/cli.py`, `engine/rail/table.py`, `engine/docs/github.md`.
- Rule for building it: `rail stats` shows more than two rebases per merged ticket on average over 30 merged
  tickets (`Rebases after the first ship`).
- Dropped, not carried: merge-queue support.

**Kept when.** Gate case, no model: three shipped tickets behind; after one merge only the next to merge is
rebased. Then the load test: CI runs per merged ticket fall and nothing else changes.

**Waits for.** Real tickets (the 30-ticket number). **A load test on real GitHub** before and after.

**Open decision.** One rebase at a time (proposed). The alternative is to ask projects to turn on GitHub's
merge queue; owner dropped merge-queue support on 2026-11-26, so the proposed answer stands.

**Assumed, not verified.**
- That the inferred CI saving holds on real GitHub (the load test measures it).

#### Conditional GitHub reads

Size: M.

**What it does.** The forge sends `If-None-Match` on a repeated read, so a `304` costs none of the primary
rate limit. Today what the forge read is thrown away after every write and every shell command
(`engine/rail/forge.py`), so a command that runs `verify` reads the pull requests again, and nothing sends
`If-None-Match`.

**How.**
- The forge keeps each read's `etag` in the local cache (`.git/rail/cache/`) and sends `If-None-Match` on the
  next read of the same URL. On a `304` the cached body is used. A `304` does not count against the primary
  limit (confirmed on GitHub's docs, 2026-11-25).
- Whether `gh api` returns a `304` as a success or an error was not checked, and whether `gh api` passes
  `If-None-Match` at all.
- Files: `engine/rail/forge.py`.

**Kept when.** Gate case, no model: the fake answers `304` to a repeated read and the cached body is used.
Then calls per merged ticket (from **Numbers later decisions wait for**) fall in the load test.

**Waits for.** **Numbers later decisions wait for** (the call count, to show the fall). Check `gh api`
behaviour with `If-None-Match` first.

**Assumed, not verified.**
- That `gh api` passes `If-None-Match` and reports a `304` in a form the forge can read.

#### A cache of settled tickets

Size: M.

**What it does.** The engine stops deriving the facts of merged and dropped tickets on every command. Today
every command reads every ticket ever filed: `Project.tickets()` reads each ticket branch, every `Ticket:`
trailer on the base branch and every file under `.rail/tickets/` on it, and `derive` builds the facts of each
one (lint, review ledger, retry budgets; `engine/rail/project.py`, `engine/rail/state.py`). The cost grows
with the project's history (inferred). It was never measured.

**How.**
- A merged or dropped ticket's facts cannot change. Keep them in the local cache keyed by the base branch's
  tip and the `rail/ids` counter's tip, and derive only open tickets on each command. A changed key reads them
  again.
- Built only after a measurement: `rail next` on a fixture with 20 and with 2,000 merged tickets. Rule: build
  it when the 2,000 case takes over 5 seconds, or over twice the 20 case.
- Files: `engine/rail/project.py`.

**Kept when.** Gate case, no model: on a fixture with 2,000 merged tickets, facts from the cache equal facts
from a full derive, for every ticket, before and after a merge and a drop. The timing measurement runs first.

**Waits for.** The timing measurement (a fixture of 20 and of 2,000 merged tickets).

#### A load test on real GitHub

Size: M.

**What it does.** This is a check, not a feature: a run of the loop under load on real GitHub, with no model,
taken before and after the scale features land, so their effect is measured instead of inferred.

**How.**
- In a throwaway repository, 20 small tickets with overlapping and separate scopes, three sessions in
  parallel, the worker replaced by a fake command that writes a fixed change (it uses `rail work`, which is
  built).
- Recorded: REST calls per merged ticket, CI runs per merged ticket, rebases, time per state, any rate-limit
  answer.
- Run before and after **Claims by changed files**, **One rebase at a time**, and **Conditional GitHub reads**
  with the call count.

**Kept when.** (The check passes when) CI runs and calls per merged ticket fall and nothing else changes.

**Waits for.** `rail work` (built); the call count from **Numbers later decisions wait for**.

### A deploy target exists

These need a place to release to, with its CD, or a host that makes previews. Until a project that runs on
Rail has one, their gate cases could run only against a stand-in, and the pilot that decides them could not
run at all. Mobile surfaces also need an emulator with hardware acceleration, or a Mac.

#### Release tickets

Size: L.

**What it does.** Rail decides and records each release to prod while the project's CD carries it out. A
release that can be undone needs no person; one that cannot waits for a person's approval. Today Rail stops at
dev: prod is a person's act, so every change waits for a person before users get it. In NBER working paper
w35275 (500,000+ GitHub developers), autonomous agents raised commits by 240% and releases by about 30%; the
authors read it as bottlenecks of people later in the chain (observational; reported). The owner's rule
(2026-11-25): what cannot be undone is a person's responsibility; what can be undone needs no person to
approve, review or learn about it. Rail decides because only Rail has the record of what each merged ticket
did and which kinds it holds; CD deploys because deployment differs per project, and so prod secrets stay with
CD.

**How.**

- **A release is a ticket of its own**, as the sweep is (`engine/docs/sweep.md`): it changes only its journal
  summary, and its squash commit carries a trailer, `Release: <sha>`, the commit it released. The trailer
  marks where the next release starts, as `Sweep:` does (`engine/rail/sweep.py`, `engine/rail/steps.py`). A
  trailer, not a git tag, because a cloud session refuses tag pushes (`engine/docs/cloud.md`). The ticket's
  `kind` field takes `release` beside `revert` (`TICKET_KINDS` in `engine/rail/ticket.py`); ticket lint and
  `engine/docs/tickets.md` know it.
- **When it is offered.** `rail next` offers a release when no ticket work is waiting and the base branch
  holds at least `[release] after` merged tickets (by their `Ticket:` trailers) since the last `Release:`
  trailer. A person can run `rail release` at any time. The candidate is the base branch's tip, provided:
  - it has been on the base branch for `[release] soak_minutes`, so the dev deploy and its smoke check ran;
  - no issue labelled `rail` that starts with `Commit:` is open for a commit in the range (a failed dev smoke
    check, `environments.md`);
  - no `rail:stop` brake is open.
  Otherwise the release rests, and the answer says why.
- **Its contract** is built in: `kind = "release"`, the range, and the list of tickets in it with their tiers
  and kinds. Its one check is the release check.
- **Config**, with `.rail/config.toml` readers `rail next` and `rail release`. An empty `command` means Rail
  does not release and prod stays a person's act as today:

```toml
[release]
command = ""        # starts the project's deploy of $RAIL_RELEASE_SHA and returns when it is live or failed,
                    # such as: gh workflow run deploy.yml -f sha=... and a watch
check = ""          # the release check: read-only against prod, exit 0 when it is healthy
rollback = ""       # deploys $RAIL_RELEASE_SHA (the last released commit) again
reversible = true   # false for a library, a package, an app store build: every release is PERSON
after = 1           # merged tickets since the last release before one is offered; 0: off
soak_minutes = 30   # time on the base branch (dev deploy and smoke check) before a release
drill_days = 30     # an AUTO release drills its rollback when the last one passed longer ago; 0: no drills
tool = ""           # the [tools.NAME] whose names the commands read (rail docs tools)
```

  A person approves the `[release]` table, since `.rail/config.toml` is in `person_paths`.
- **Its tier** is AUTO when the release can be undone, and PERSON otherwise:

| PERSON when | Why |
|---|---|
| `[release] reversible = false` for the project | A published library version, an app store build: others already have it (`public-release`) |
| A ticket in the range holds a kind that takes effect at release: `data-loss`, `data-shape`, `data-exposure`, `external-effect`, `access`, `infrastructure` (`rail docs kinds`) | Prod data and prod users meet it now; a rollback restores the code, not the data or the effect |
| `[release] drill_days = 0` (drills off) and no real rollback has passed | With drills off, "can be undone" is a claim nobody has run, like a migration's `rollback` field |

- **Tier from the range's kinds.** A ticket's kinds are read from its journal: the `accepted` event's kinds,
  each `tier_raised` event's `kind`, and the `kinds` items of its review runs (`rail docs journal`). The
  release takes the union over the range, read from the base branch, where merged tickets' journals are. A
  kind that takes effect at push or merge only (`controls`, `money`, `licence`) does not make a release
  PERSON: its effect was earlier, and the ticket was PERSON then. `runs-with-secrets` does, when the range
  changes the deploy workflow or a dependency whose build scripts the prod build runs: that code meets the
  prod secrets now (`rail docs kinds`). The release brief lists each PERSON reason with the tickets and kinds
  behind it.
- **A PERSON release** waits at `APPROVE_CONTRACT` (`engine/rail/table.py`), whatever `approve_contract` holds,
  because the release is where its kinds take effect: the person approves it with `rail accept NN` or `rail:go`.
  Then the engine runs it. Its merge is the engine's whatever its tier: the merge only records what happened,
  and the person's act was the approval. This is the one ticket kind where a PERSON ticket's merge is not a
  person's, and the docs say so. **The `MERGE` row exception**: today the `MERGE` row refuses the engine's merge
  of a non-AUTO ticket when there is a remote (`and not (f.project.remote and not f.auto)`), so a PERSON release
  would fall to `MERGE_BY_PERSON`. The row gains `or kind == "release"`.
- **What the engine runs** (the release ticket's ship, in order):
  1. `command` with `RAIL_RELEASE_SHA` set to the candidate. A failure stops here and counts as a failed step,
     with the retry budget and cap as for any step (`engine/docs/retries.md`). Nothing reached prod, or CD's
     own failure left the old version, which `check` confirms.
  2. `check`. On a pass, the ticket merges with the `Release:` trailer.
  3. On a failed `check`: the failure path in **Rollback and the release issue**.
- **The read-only check.** `check` must not write prod data or send anything (an `external-effect`). A rule
  alone is not a guard, so two things back it:
  - It runs as a read-only identity. The test identity it signs in with, if any, has a role that cannot write
    (a project's own setting; Rail cannot read a project's roles, so it proves this only through the gate case
    below). Without sign-in it reads public pages and endpoints only.
  - A gate case catches a writing check before it is kept: `check` runs against a local fake prod that records
    every request, and any write method (POST, PUT, PATCH, DELETE) or outbound message fails it.
    `rail-verify`, which writes the check, runs that case on the project's own `check`.
- Files: `engine/rail/config.py` defaults, `engine/rail/docs.py` (`rail docs config`), `seed/config.toml`
  (`[release]`); `engine/rail/table.py` and `engine/docs/loop.md` (the release offer, its rests, the `MERGE`
  row's exception); `engine/rail/steps.py` (the release ship, the trailers); `engine/rail/cli.py` (`rail
  release`); `engine/rail/ticket.py`, ticket lint, `engine/docs/tickets.md` (`kind = "release"`); a new page
  `engine/docs/release.md`; `engine/docs/environments.md` (see **Release docs and the read-only check
  wording**).
- Not covered: canary and percentage rollouts (CD's own); releases of several services in a set order; mobile
  release trains; a project whose prod data a rollback cannot run against (its tickets are `data-shape` and
  its releases PERSON).

**Kept when.** Gate cases, no model, with fake `command`, `check` and `rollback` scripts that record their
calls and exit as told:
- with `after = 1`, a merge makes `rail next` offer a release once nothing else waits; with `command` empty,
  nothing is offered; `0` turns it off;
- a candidate younger than `soak_minutes`, an open `Commit:` issue in the range, or an open `rail:stop` makes
  it rest with the reason;
- a range of AUTO tickets with no kinds is an AUTO release; a range with a `data-shape` kind (from an
  `accepted` event, a `tier_raised` event, or a review's `kinds`), or `reversible = false`, or a changed
  deploy workflow, or `drill_days = 0` with no rollback since, is PERSON with that reason; a range whose only
  kinds are `controls` or `money` is AUTO; an AUTO range with no rollback record within `drill_days` stays
  AUTO;
- a PERSON release, once approved, is merged by the engine with a remote, and a PERSON ticket of any other
  kind still waits at `MERGE_BY_PERSON`;
- fake prod: a `check` that sends a POST to the fake prod, or a message, fails the case; a `check` that only
  reads passes;
- a passing release merges with `Release: <sha>`; the next release's range starts after it.

Kept when every case behaves as written. A pilot on a real deploy (a service on a host with a deploy API and a
rollback, its CD started by `workflow_dispatch` from a cloud session) runs three releases: one that passes,
one with a check made to fail (rolled back, issue filed), one PERSON by a `data-shape` ticket (approved, then
run). Kept when each ends as written and no prod secret was in the cloud session's environment. It needs no
model.

**Waits for.** The pilot waits for the owner: it needs a host account and a grant. Starting the deploy from a
session needs the dispatch grant in **Release checks in `rail doctor`**, which waits for the machine identity
(a GitHub App, not built). Built and relied on: the journal's kinds and `tier_raised` events, `rail:stop`,
tool declarations and the wait kinds `approval`, `grant` and `hold`.

**Open decision.**
- Who releases? Proposed: Rail decides, records and starts the release; CD carries it out and holds the
  secrets. The alternatives are Rail only recording what CD released, or Rail deploying itself.
- When is a release offered? Proposed: after each merge (`after = 1`). The alternatives are after a count, or
  on a schedule.

**Assumed, not verified.**
- That `soak_minutes` and the absence of a `Commit:` issue mean the dev smoke check passed. The smoke step
  only opens an issue on failure, so a CD that never ran looks the same. A project can make `command` refuse a
  commit dev has not deployed.
- That library registries cannot truly undo a published version (npm, crates.io and PyPI each restrict
  deleting or reusing one; from general knowledge, not checked). `reversible = false` does not depend on the
  details.

#### Rollback and the release issue

Size: M.

**What it does.** When a release's check fails, Rail puts the last released version back, records that, and
files an issue so a fix ticket follows. If the rollback itself fails, prod is in a state the machine cannot
vouch for, and a person is told.

**How.**
- On a failed `check`, the engine runs `rollback` with `RAIL_RELEASE_SHA` set to the last released commit,
  then `check` again.
- **When that passes**: the ticket merges with a `Rolled-back: <sha>` trailer instead of `Release:`, so the
  next release starts from the same place. The engine opens an issue labelled `rail` that starts with
  `Release: <sha>` and holds the check's output and the range.
  - `rail intake github` (`engine/rail/cli.py`) turns an issue that starts with `Release:` into a fix ticket,
    as it does a dev smoke issue (`environments.md`).
  - If the range holds one ticket, the fix ticket's `caused_by` is that ticket. With several, the fix ticket's
    brief lists them and its first task is to find which one (open decision: one fix ticket for the range).
  - No release is offered while that issue is open (**Release tickets**).
- **When the rollback or its check fails**: the ticket waits for a person with a new wait `RELEASE_BROKEN` of
  kind `approval`, with both outputs. It is added to `WAIT_KINDS` in `engine/rail/table.py`. This is the one
  release wait on an AUTO release: prod broken and not restored is harm still happening, which no later act of
  the machine undoes.
- Files: `engine/rail/steps.py` (the trailers, the failure path), `engine/rail/table.py` (`RELEASE_BROKEN`),
  `engine/rail/cli.py` (intake), `engine/docs/loop.md`, `engine/docs/release.md`.

**Kept when.** Gate cases, no model: a failing check runs `rollback` with the last released commit, merges
with `Rolled-back:`, opens a `Release:` issue that intake turns into a fix ticket (with `caused_by` for a
one-ticket range), and no release is offered while it is open; a failing rollback gives `RELEASE_BROKEN` on an
AUTO release. The pilot in **Release tickets** covers it on a real host.

**Waits for.** **Release tickets**.

**Open decision.** On a rolled-back release, file one fix ticket for the range (proposed), or revert first as
a failed deploy to dev does (`rail docs environments`)?

#### The rollback drill

Size: S.

**What it does.** A release counts as one that can be undone only while its rollback is known to work, so an
AUTO release proves its rollback when the last proof is old. The engine records each `rollback` run that ended
with a passing `check` in the release ticket's journal. When the newest record is older than `drill_days`
(default 30), or there is none, the release does a drill first. A project whose first release has no record
gets the drill on it.

**How.**
- The drill runs in this order: release the candidate, run `check`, roll back to the last released commit, run
  `check`, release the candidate again, run `check`. The drill's rollback is the record.
- A drill puts the old version back for the time between two deploys, and the old version then reads data the
  new one wrote meanwhile. This is safe only because of the tier: a range with a `data-shape`, `data-loss` or
  `infrastructure` kind is PERSON, so an AUTO release's range changed no stored shape, and the old version
  reads what the new one wrote.
- So a missing or old rollback record does not make a release PERSON: an AUTO release runs the drill, and the
  drill writes the record.
- A PERSON release has no drill, since its range may change a stored shape the old version cannot read. The
  person approves it knowing whether the last drill is recent.
- `drill_days = 0` turns drills off: no drill runs, and a release is PERSON until a real rollback has passed
  (Decision).
- Files: `engine/rail/steps.py`, `engine/docs/release.md`.

**Kept when.** Gate cases, no model: an AUTO release with no rollback record within `drill_days` runs the
drill in order, and the drill's rollback counts as the record; a PERSON release runs no drill; `drill_days =
0` with no rollback record makes the release PERSON.

**Waits for.** **Rollback and the release issue**.

**Open decision.** Run the drill when the last rollback is older than 30 days (proposed), or never, with every
release PERSON until a real rollback has passed?

**Assumed, not verified.**
- That a drill's brief return to the old version is acceptable for every service that calls itself reversible.

#### Release checks in `rail doctor`

Size: M.

**What it does.** `rail doctor` checks that a release cannot run from a ticket branch with prod secrets, and
names the one-time grants a person must make. The machine still holds no prod secret: `command` starts the
project's deploy through GitHub (`POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`, a
`workflow_dispatch` event; not checked on GitHub's docs), and the deploy workflow reads the prod secrets from
a GitHub environment that only that workflow uses.

**How.**
- `workflow_dispatch` takes any `ref`, so a dispatch could run the deploy workflow from a ticket branch, with
  that branch's workflow file and code. The prod environment's deployment-branch rule must allow the base
  branch only: then a job on any other ref cannot read the environment's secrets (GitHub's environment rule;
  not checked on GitHub's docs). `rail doctor` already reads each environment that holds a secret and fails
  one open to any branch (`rail docs tools`, built).
- What this adds: the release setup names its deploy environment; `rail doctor` reports a release setup whose
  environment fails that line as broken; `rail next` offers no release until it is fixed.
- What a person grants once:
  - the machine's identity may dispatch the deploy workflow;
  - the prod environment's protection lets that dispatch run without a GitHub reviewer, since Rail's tier now
    decides when a person approves. A project that keeps GitHub's required reviewer gets a second approval on
    every release, and every AUTO release then waits there; `rail doctor` reports that state;
  - the deploy workflow file is under `.github/workflows/**`, which the seed lists under `[kinds]
    runs-with-secrets` (`seed/config.toml`), so the machine cannot change what it runs with the prod secrets
    without a person.
- `check` needs only what a user has: the prod URL, and a test identity if the check signs in. That identity
  is a grant like the dev one, not a prod secret, and is `access` only if it can do more than a user.
- Files: `engine/rail/doctor.py`, `engine/docs/github.md`.

**Kept when.** Gate case, no model, against a fake GitHub: a prod environment whose deployment-branch rule
allows more than the base branch makes `rail doctor` report it and `rail next` offer no release; a required
reviewer on the prod environment is reported. The pilot in **Release tickets** confirms the dispatch on a real
host.

**Waits for.** **Release tickets**. The dispatch grant waits for the machine identity (a GitHub App), which is
not built, so the grant has nothing to attach to yet.

**Assumed, not verified.**
- That a cloud session's GitHub access may call the `workflow_dispatch` endpoint. `cloud.md` lists what the
  cloud refuses and does not name it; Rail uses REST for everything else there.
- The `workflow_dispatch` endpoint and the environment's deployment-branch rule were not checked on GitHub's
  docs.

#### Release numbers in `rail stats`

Size: S.

**What it does.** `rail stats` shows how releases go and how long merged work waits for prod. The time from
merge to prod is the line that shows the NBER gap (autonomous agents raised commits by 240% and releases by
about 30%) in this project.

**How.**
- `engine/rail/stats.py` and `engine/docs/stats.md` read the `Release:` and `Rolled-back:` trailers and add:
  - releases, by tier and by PERSON reason; rollbacks; drills; releases broken (`RELEASE_BROKEN`: prod is
    broken and not restored);
  - time from merge to prod: for each ticket, from its squash commit to the `Release:` commit that carried it;
    the median, and the share released within a day;
  - fix tickets from a release issue, and their `caused_by`.

**Kept when.** A gate case on fixture history: `rail stats` reads the trailers and gives time from merge to
prod.

**Waits for.** **Release tickets**, **Rollback and the release issue** (for the rollback and fix-ticket lines).

#### Release docs and the read-only check wording

Size: S.

**What it does.** The docs and the skill text that describe releasing are written once the pilot has run, so
they say what happened and not what was planned. Until then the config and engine can be built without them.

**How.**
- `engine/docs/environments.md`: the Prod row becomes: with `[release] command` set, Rail offers a release
  after merges, starts the project's CD with the commit, runs the release check, and rolls back when the check
  fails; a release that cannot be undone waits for a person's approval; without it, releasing is a person's
  act, as today. The person's acts become: merging a PERSON ticket; deleting data; handling credentials
  (grants); approving a release that cannot be undone. "The machine holds no prod secret" stays true.
- A new page, `engine/docs/release.md`. It also says that a PERSON release's merge is the engine's (the one
  exception to a PERSON ticket's merge being a person's).
- `engine/docs/tickets.md`: `kind = "release"`.
- `seed/skills/rail-verify/SKILL.md`: how to write a release check that is read-only, and the fake-prod gate
  case that proves it. This wording comes after the pilot.
- Each pull request that builds a part of the release features carries its docs and `CHANGELOG.md`.

**Kept when.** No test of its own; the docs match the behaviour the gate cases and the pilot showed.

**Waits for.** The pilot in **Release tickets** (a real deploy, a host account and a grant, which wait for the
owner). **Release tickets**, **Rollback and the release issue**.

#### Preview environments

Size: L.

**What it does.** A ticket whose surface needs a hosted URL gets a preview made from commands the project
names, and Rail destroys it at merge or drop. Most driving checks run on `localhost` (a cloud session has it,
and GitHub's cloud agent limits its browser to `localhost` by default, reported). A preview is for what
`localhost` cannot give: OAuth redirects, webhooks from third parties, data shared with another service, a
reviewer outside the session. The platform stays the project's choice; Rail ships no adapter.

**How.**

```toml
[preview]                                 # reader: ship (the product step), cleanup after merge or drop, rail doctor
create = ""                               # prints {"id": ..., "url": ...} as JSON; RAIL_TICKET is set
wait = ""                                 # exits 0 once the preview answers; RAIL_PREVIEW_ID is set
seed = ""                                 # loads test data from files in the repository, never from production
destroy = ""                              # removes the preview; must succeed when it is already gone
list = ""                                 # optional: prints the open previews' ids as JSON
max_open = 5                              # previews open at once; a ticket over it rests until one is destroyed
tool = ""                                 # the [tools.NAME] whose token the commands use (rail docs tools)
```

- Hosts the research compared document a command or action output that gives the URL as JSON or on stdout
  (Netlify `deploy --json`, `vercel deploy`, the Fly action's outputs, Neon's action's `db_url`; reported,
  vendor docs). Cloudflare is left out: the research cites `wrangler preview --json` for Wrangler 4.135.0 or
  later, but the current Wrangler gives preview URLs through `wrangler versions upload`, and which is right
  was not checked.
- **The engine creates it** at the first ship of a patch that needs it, records a `preview` event (`id`,
  `url`, `created`) with the step events, and reuses it for later patches of the same ticket, running `seed`
  again.
- **Where the commands run.** `create`, `wait` and `seed` run where the product step runs: in the worker's
  session at ship, and in pull-request CI when **The product step** keeps the step there (CI then reuses the
  ticket's preview by the id in its journal, and creates one only when none is open). `destroy` and `list` run
  in the session that runs `cleanup()` or `rail next`, never in pull-request CI. Each place runs the ticket
  branch's own code, so nothing they hold may be a production secret or production data: `seed` loads only
  files in the repository, with test identities and test values, never a dump or a copy of production.
- **Teardown is the engine's, because that is where hosts leak.** Neon branches made through its API and CLI
  and Render previews never expire by default; Cloudflare leaves container apps behind; Supabase branches sit
  outside its spend cap (reported, vendor docs).
  - At merge or drop, `cleanup()` (`engine/rail/cli.py`, `engine/rail/steps.py`), which already removes a
    merged or dropped ticket's worktree and branch, also runs `destroy` for the ticket's preview, whose id is
    in the ticket's journal (merged with the code, `rail docs journal`). `rail drop` runs it directly, since a
    dropped ticket's journal goes with its branch.
  - No journal event is written for a destroy. The engine commits the journal only on the ticket's branch;
    after a merge that branch is gone and the journal is on the base branch, where only a merge may write (the
    guard denies a push to it, `rail docs guards`); after a drop the branch is deleted. The local cache notes
    the destroy, and `destroy` must succeed on a preview already gone, so a second machine running it again
    does no harm.
  - With `list`, `rail next` reconciles once per hour: any preview whose ticket is merged, dropped or unknown
    is destroyed. Without `list`, `rail doctor` lists the `preview` events of merged and dropped tickets the
    cache has not seen destroyed.
  - A pull request closed by hand also gets `destroy` (a gate case below).
- **Access is a grant.** The preview token is a `[tools.NAME]` declaration (`rail docs tools`) scoped to one
  project: a person grants it once. The machine still holds no production deploy token (`rail docs
  environments`). The token is reachable from a ticket branch (the worker's session holds it; when the product
  step runs in CI, the tool is `ci = true` and reaches pull-request CI, which runs the branch's own code). So
  it must be a token whose exposure a rotation undoes and that costs nothing meanwhile: one that can create
  and delete previews and nothing else. A host that offers only a wider token (Fly needs an org-scoped token
  to create apps, reported) is a wider grant, and `rail doctor` says so. The grant bounds the spend;
  `max_open` and teardown keep it bounded.
- **Production data.** Copying production data into a preview is `data-exposure`, a kind that cannot be undone
  (`rail docs kinds`), so a `seed` or `create` that branches production data is a PERSON choice.
- **`engine/docs/environments.md` gets a Preview row** between Local and Dev: "Per ticket, when a surface
  needs it: the project's `create`, `wait` and `seed` at ship, `destroy` at merge or drop. The machine holds a
  token scoped to previews." Today Rail does nothing at runtime outside Local and the machine, so the page
  names this as the one exception.
- Files: `engine/rail/config.py`, `engine/rail/docs.py`, `seed/config.toml`, `engine/rail/steps.py`,
  `engine/rail/cli.py` (teardown in `cleanup()` and `rail drop`, the hourly reconcile),
  `engine/rail/doctor.py`, `engine/docs/journal.md` (the `preview` event), `engine/docs/environments.md`.
- Not covered: Kubernetes-based previews (worth it only for projects already on Kubernetes, per the research).

**Kept when.** Gate cases, no model, with fake commands that write to a log: `create` once per ticket, its URL
in `RAIL_URL`, `seed` on each patch; `destroy` at merge, at `rail drop`, and for a pull request closed by
hand; `destroy` twice passes; with `list`, an orphan is destroyed; over `max_open`, the ticket rests; `rail
doctor` reports a missing preview command or tool name. Kept when every case behaves as written.

**Waits for.** **The product step**, **Product surfaces in the config**. A person's grant of the preview
host's token, and a preview host. In CI, the tool marked `ci = true` (built).

**Open decision.**
- Is `[preview] list` optional or required? Proposed: optional.
- Is `max_open = 5` the right default? Proposed: 5.

#### Mobile surfaces

Size: M.

**What it does.** A project with a mobile app gets a `mobile` surface driven by a Maestro flow on an emulator
or simulator. It comes last: no study of agent-built mobile code was found, and Rail's first target, a cloud
session, runs Linux (reported).

**How.**
- The recipe in `rail-verify`: a Maestro flow on an emulator or simulator. Evidence: screenshots or a
  recording. What gets faked: a test never seen to fail on a broken build (so the negative control is
  required).
- Android's emulator needs hardware acceleration, which a cloud machine may lack. iOS simulators need macOS
  (reported).
- The `rail doctor` bar line: for `mobile` with Android, `/dev/kvm` must exist; with iOS, the machine must be
  macOS. When it fails the line has `kind = grant`: a runner with hardware acceleration, or a Mac.
- `mobile` is already a valid `kind` in the config (**Product surfaces in the config**), and a `mobile`
  surface needs a seeded test identity (**The machine-operable bar in `rail doctor`**).
- Not covered: iOS in a Linux cloud session.

**Kept when.** Gate case, no model: a `mobile` Android surface on a machine without `/dev/kvm` gives a `grant`
line (the case is part of the bar's). The recipe has no model test of its own; it is marked untested.

**Waits for.** **Per-surface recipes and the project's run skill**, **The machine-operable bar in `rail
doctor`**. A machine with hardware acceleration or a Mac. Last in the order of the product features.

**Assumed, not verified.**
- That `/dev/kvm` is a fair test for Android emulator acceleration on Linux (inferred).
- That Maestro runs as the research describes on an emulator: reported, not run.

### More people

`proposals/team.md` holds what a team needs: a ticket a person keeps, waits addressed to one person, code
owners, a runner for each person, a warning when two tickets overlap. Its features are built when a second
person works in a repository that runs on Rail. The features below wait for the same thing.

#### A machine identity

Size: L.

**What it does.** The machine acts on GitHub as its own identity (a GitHub App or a machine account), set up
once by a person, and `rail doctor` lists the grants Rail holds and lacks. A grant is a person's one-time act
that lets the machine do something. Each wait the machine cannot get past already names the grant it needs
(the `grant` wait kind is built). Pull requests by the machine can be approved by any person, and an
installation's rate limit is its own.

**How.**
- The machine identity: a GitHub App or a machine account. Reasons for an App (open decision below): its own
  rate limit (at least 5,000 an hour for an installation, rising up to 12,500; the person's own token shares
  one 5,000 with every app acting as that person) and scoped permissions.
- The admin grant: lets the engine apply and repair the repository's settings: the ruleset, squash settings,
  branch deletion, labels. A cloud session cannot write settings (`engine/docs/cloud.md`), so this needs the
  machine identity with admin rights. It weakens the guard "a cloud session can't change settings", which
  `cloud.md` names as the one an agent cannot get around. Decision 3.
- `rail doctor` lists grants held and lacking (`engine/rail/doctor.py`; not built). Says which guard each
  grant removes.
- Docs: `engine/docs/cloud.md` (the machine identity). Not verified: how a cloud session picks its GitHub
  identity, so whether a machine identity works in the cloud at all. Check this first, then build after
  Decision 4.
- Dropped, not carried: the local sudo grant for `rail provision`.

**Kept when.** Gate case, no model: with a fixture config, `rail doctor` lists a held and a lacking grant, and
the admin grant's line names the guard it removes. A real check in the cloud for how the session picks its
identity, before building.

**Waits for.** A check of how a cloud session picks its GitHub identity. The call count from **Numbers later
decisions wait for** shows when the rate limit needs it.

**Open decision.**
1. Machine identity as a GitHub App (proposed: its own rate limit and scoped permissions) or a machine account.
2. The admin grant. Proposed: not by default; a project that wants it grants it, and `rail doctor` says which
   guard that removes.

**Assumed, not verified.**
- How a cloud session picks its GitHub identity.

#### Sources on a schedule

Size: M.

**What it does.** A source declares how often it runs, so one runner runs every source and no scheduled task
is needed per source (`engine/docs/sources.md`, "Running a source"). `rail next` answers a due source, and a
due sweep with it, before it reports that a ticket waits for a person, so one open wait does not stop the
sweep or starve the source.

**How.**
- A source's front matter gains `every = "1d"` (`engine/rail/sources.py`, `engine/docs/sources.md`).
- Where `rail next` answers matters. Today it returns `WAITING_PERSON` whenever any ticket waits for a person,
  before it reaches the sweep (`engine/rail/cli.py`). A due source and a due sweep are answered before the
  `WAITING_PERSON` return: after every ticket the agent can act on, after a CI watch, and before reporting
  waits. The waits still go into the answer's `waits` list and their labels are set earlier in the same
  command, so the person's inbox is unchanged. The runner, which stops only when `rail next` says nothing is
  left for an agent, keeps going until the source has run.
- A source's last run is kept the way the sweep's is: the sweep finds its last run from the `Sweep:` trailer
  on the base branch (`engine/rail/sweep.py`). A source files tickets and merges nothing, so it has no commit
  of its own on the base. Its run time goes into the `requested` event of each ticket it files, and a run that
  files nothing writes a one-line mark in the local cache (inferred design). A fresh cloud clone then runs a
  source that filed nothing once more, which costs one `fetch` and files nothing new, since `external_id`s are
  unique. The counter branch is not used: it holds ids and drop marks (`engine/rail/project.py`).
- Files: `engine/rail/cli.py`, `engine/rail/table.py`, `engine/rail/sources.py`, `engine/docs/sources.md`,
  `engine/docs/cloud.md` (sources without their own tasks).

**Kept when.** Gate cases, no model: a due source is answered by `rail next` when no ticket work is left, and
not before. With a ticket waiting for a person, the due source and a due sweep are still answered, the waiting
ticket keeps its label, and the next `rail next` after the source ran returns `WAITING_PERSON`.

**Waits for.** Nothing.

### The owner takes it up again

The owner set these two aside on 2026-11-27. They are the two directions between the framework and a project
that runs on it. The first was a confirmed step, and neither waits for anything else.

#### Taking Rail's changes into a project

Size: M.

**What it does.** A project learns what changed in Rail since its copy of the engine, through a source a
person schedules, instead of a person asking an agent to clone the framework and "see what we can integrate"
(owner, 2026-11-09). No `upgrade` verb is added; that decision of 2026-11-09 holds.

**How.**
- A seed source `seed/sources/rail-framework.md`, copied by `rail init` (`engine/rail/init.py`) and scheduled
  by a person. Its `fetch` fetches the framework at the URL in `.rail/SOURCE` into a temporary folder and
  prints the `CHANGELOG.md` lines added since the commit in `.rail/SOURCE`, each with its commit.
- `.rail/SOURCE`: `rail init` writes the framework's URL and commit there (built; no docs page describes it,
  so add a short description to `engine/docs/sources.md` or the page that covers `rail init`). The source
  reads it and its work updates the commit in it.
- Its prompt files one ticket per change worth taking, `external_id = "rail-framework#SHA"`, with `tier =
  "PERSON"`, because every such ticket changes Rail's own gates. Its work copies the changed files from that
  commit, keeps the project's own changes to them, and updates the commit in `.rail/SOURCE`.
- `person_paths` additions in `seed/config.toml`. The default covers only part of what `rail init` copies:
  `.rail/bin/**`, `.rail/engine/**`, `.rail/config.toml` and `.rail/sensors/**`; `.claude/**` and
  `.github/workflows/**` are PERSON through the kind `runs-with-secrets`. The seed's `person_paths` gain:
  - `.rail/packs/**` (a pack runs code, as consult runs a model),
  - `.rail/sources/**` (a source's prompt files tickets),
  - `.rail/ruleset.json` (the branch protection a person imports),
  - `.rail/tickets/TEMPLATE.md`.
  With these, the paths make the tier PERSON too, and the front matter is a second hold.
- `README.md` says how a project takes Rail's changes (the source) instead of the prompt.
  `engine/docs/sources.md` lists the source.

- Seen on 2026-11-26: running `rail init` again in a project that has Rail merges the settings and creates
  missing labels, and refreshes neither `.rail/engine/` nor a skill that is already there. Until this source
  exists, a project takes a newer Rail by copying the engine by hand.

**Kept when.** Gate cases, no model:
- `rail-framework`'s `fetch` against a fixture framework repository prints the CHANGELOG lines after the
  recorded commit and none before it.
- With the seed's `person_paths`, a ticket that changes only `.rail/packs/consult/` or `.rail/sources/` is
  PERSON at add.

Model test, built once model runs are available (until then the wording of the prompt is untested): three
fixture changelogs, each with changes the project already has and changes it lacks, two runs each. Kept when
it files a ticket for each change the project lacks, and for no other, in at least five of the six runs.

**Waits for.** The owner restarting the paused model tests (for the model test only). Order of work: the
`person_paths` additions first, then the source after its model test.

**Open decision.** Nothing open beyond the source form, which is settled for this source (a source, no verb).

#### Sending a project's fixes back to the framework

Size: M.

**What it does.** A project that fixed something in its copy of Rail's files can draft an issue for the
framework, and a person approves the text before anything leaves the repository. Today nothing carries a fix
back. Rail is developed without Rail (owner, 2026-11-26), so the framework side only receives an issue.

**How.**
- A seed source `seed/sources/rail-upstream.md`, copied by `rail init` and scheduled by nothing until a person
  does. Its `fetch` lists the merged commits since its last run that changed the files `rail init` copied from
  the framework: `.rail/engine/**`, `.rail/bin/**`, `.rail/packs/**`, `.rail/ruleset.json`,
  `.rail/tickets/TEMPLATE.md`, `.rail/sources/weekly-review.md` and the two Rail sources,
  `.claude/skills/rail-*/**` and `.github/workflows/rail.yml`. Each commit is listed with its `Ticket:`
  trailer, its ticket's `## Why`, and the diff of those files only, plus the counts from `rail stats --json`.
- Its prompt: a change that would help any project running Rail (a bug in the engine, a brief that misled, a
  missing guard) is drafted as an issue for the framework repository named in `.rail/SOURCE`. A change that is
  this project's own setting is not. The draft holds the diff of Rail's files, the reason, and the stats lines
  that show its effect; never code outside Rail's files, and never a value from an environment variable.
- A person sends it. An issue on another repository is text published outside the repository, the
  `external-effect` kind, which cannot be undone (`rail docs kinds`). The source opens the draft as an issue
  in the project's own repository with the label `rail:upstream` (add it to `LABELS` in
  `engine/rail/forge.py`). Intake reads only `rail`, so it does not take that issue. A person who adds
  `rail:go` to it approves the text. The next run of the source opens it on the framework's repository with a
  grant for that, links it, and closes the draft.
- On the framework's side the issue is labelled `rail` and becomes a request: its author cannot push there, so
  it is never taken as a whole ticket (`engine/rail/cli.py`).
- Docs: `engine/docs/sources.md` lists the source and says that `rail-upstream` opens an issue elsewhere after
  a person's `rail:go`.

**Kept when.** Gate cases, no model:
- `rail-upstream`'s `fetch` on a fixture history lists the commit that changed `.rail/engine/` and not one
  that changed only product code; its diff holds no file outside Rail's paths.
- `fetch` lists a commit that changed only `.rail/packs/` or `.rail/ruleset.json`.
- A `rail:upstream` issue is not taken by intake; `rail:go` on it lets the next run of the source open it.

Model test, two runs each, wording untested until then: six fixture histories, three with an engine fix and
three with only a project setting changed in `.rail/config.toml`. Kept when it drafts an issue in at least
five of the six runs on the first three and in no more than one on the others, and no draft holds a line from
outside Rail's files.

Not covered: whether an upstream issue's text leaks something of the project that Rail's paths do not show
(the person's approval of the text is the check); how many projects will send anything.

**Waits for.** **A machine identity** (the grant to open an issue on the framework's repository), and the
model test above. The source comes after the model test.

**Open decision.** Whether `rail-upstream` is a source that opens an issue elsewhere after `rail:go`
(proposed), or a verb. A source keeps the prompt editable, and it is the first source that acts outside `rail
add`.

**Assumed, not verified.**
- That a cloud session's GitHub access can open an issue on another repository. If not, it is a grant: an
  identity for the machine with access to the framework's repository.

### `rail replay` is taken up again

The owner set the benchmark and `rail replay` aside on 2026-11-26. The code under `bench/` stays as it is and
is not developed. What follows is not built until the owner takes replay up again.

#### `rail replay`

Size: L.

Set aside by the owner (2026-11-26): not built until the owner takes it up again.

**What it does.** A new verb that runs a merged ticket again, on a clean copy of the code as it stood before
the merge, with a different model, effort, prompt or setting, and grades the result. Rail has choices that
only runs can settle: the worker ladder's models and efforts (`seed/config.toml` `[worker]`), the reviewer's
model, every change to a skill or a brief, and the arms in other proposals' tests. Test tasks written for the
purpose are few, cost a person's time, and may not look like the project's real work. Each merged ticket is
already a graded task (inferred): the request and contract, the code it started from (the parent of its squash
commit), what "done" meant (the `Check:` lines and the change that passed them), and what it cost and how it
went (its journal). Warp builds the same thing from recorded runs and warns that the replayed agent must not
see the finished work, or it copies it (reported, Boundary talk with Warp's founder, 2026-11-25;
https://www.youtube.com/watch?v=XUEfIxkdT2Q).

**How.**

Verb:

```text
rail replay NN [--arm NAME] [--runs K]     # one merged ticket
rail replay --pick N [--arm NAME] [--runs K]  # N tickets from the merged ones that qualify
rail replay --report                       # compare the arms run so far
```

An arm is a named set of overrides in `.rail/replay.toml`: `.rail/config.toml` keys that the current engine
knows (the ladder, the reviewer's model, `[worker] command`), and files to put in place of the copy's (a skill
page, `reviewer.md`). The arm `as-is` changes nothing. An arm cannot change engine code: a choice that needs
new engine code becomes an arm once that code is in the project's engine and a config key turns it on.

The copy the worker sees:
1. The code. A new repository, outside the project, holding one commit: the tree of the squash commit's
   parent. It has no remote, no other commit and no branch but the base, so the finished change is nowhere in
   it (inferred). The commit's message has a `Ticket: NN` line for every ticket merged on the base before that
   parent, so the engine sees those tickets as merged, not dropped. Without them, a ticket whose `after` names
   one would wait as `AFTER_DROPPED` (`engine/rail/project.py`, `engine/rail/state.py`).
2. The engine. The project runs its own engine from `.rail/engine/` (`bin/rail`), and the parent's may be
   older than the arms need: the config loader refuses keys it does not know (`engine/rail/config.py`), and an
   engine from before `rail work` cannot run a worker. So the copy takes `.rail/engine/`, `.rail/bin/` and
   `.claude/` from the project's current base, and `.rail/config.toml` from the parent, with the arm's
   overrides on top. A ticket whose old config the current engine refuses does not qualify. Replay measures
   the current setup on old tasks, not the old setup.
3. The ticket. It qualifies only when its Done Contract never changed: the merged file's Done Contract hashes
   to the `done` of its first `accepted` event. That event keeps the hash, not the text
   (`engine/rail/cli.py`), and the engine finds the first text from the ticket's branch
   (`engine/rail/review.py`), which is deleted after the merge. With the hashes equal, the merged text is the
   first text, and the worker is graded on the checks it was given. Each part of the ticket file:

   | Part | In the copy |
   |---|---|
   | `## Request`, `## Why`, `## Grilling`, `## Out of scope`, the Done Contract | Kept from the merged file |
   | `scope_paths` | From the first `accepted` event |
   | `tier`, `after`, `reversibility`, `rollback` | Kept from the merged file's front matter |
   | `caused_by`, `external_id` | Dropped: they point at the project's forge |
   | `## Assumptions` | Left empty. The merged section holds the worker's `VERIFIED:` answers, and the open
   `ASSUMED:` rows are lost with the branch. A ticket whose `requested` event has `assumed` above 0 does not
   qualify |
   | `## Look at`, `## Tried`, anything else the work wrote | Dropped |

   The replay accepts the contract with `rail accept NN` for a PERSON ticket, standing in for the person who
   approved it then.
4. The forge and the network. The replay runs with no remote, so Rail works locally and merges with `rail
   advance` (`engine/docs/loop.md`, "With no remote"). `GH_TOKEN` and `GITHUB_TOKEN` are unset, and
   `GH_CONFIG_DIR` points at an empty folder, since `gh` keeps its own stored login. `RAIL_CLOUD=0`, so no
   `rail provision` runs. The sandbox's `allowedDomains` limits Bash, not the web tools (reported, Claude Code
   docs; Rail's sandbox is in `engine/docs/guards.md`), so the replay brief says the forge is out of bounds,
   and the run is searched afterwards.

The run: the replay acts as the runner. It calls `rail next` and acts on each answer until the ticket merges
in the copy, waits for a person, or is dropped.
- An answer whose action is a `rail` command (`rail advance`, `rail next`) runs as given.
- A `rail work` answer runs the arm's worker command, through `rail work`.
- A PERSON ticket's merge wait is answered with `rail accept NN` and counted in the report as a person's act
  the replay stood in for.
- Any other answer for a person or for an agent outside `rail work` (`SETUP_FAILED`, `RED_BASE`, a finding
  that waits for a person) ends the run, and its code is the outcome.
- `--runs K` (3 by default) repeats each ticket, each on a new copy. The worker command's whole stream is kept
  for the run, uncut.

The taint search: every tool input in the stream (Bash commands, WebFetch URLs, WebSearch queries, file paths)
is searched for the original pull request's URL, `OWNER/REPO/pull/`, `OWNER/REPO/commit/`, the squash commit's
hash (its first 7 characters or more), and `gh` commands. A hit marks the run `tainted`, and the report leaves
it out. The bare repository name is not searched: Go module paths and scoped npm names contain it, so ordinary
commands would match.

The grade: each run is graded on a new copy of its result.
1. The checks: each `Check:` line of the ticket's contract, run as ship runs it. These are the checks the
   worker was given.
2. The tests the original added: with `[replay] tests` set (globs such as `tests/**` or `**/*_test.go`), the
   files the original change added or changed under those globs are copied over the result first, so the
   checks also run the original's own tests. Without it, the run is graded with the worker's own tests, and
   the report says so: that grade is weaker. The original's tests can name things a valid solution names
   differently; the pilot reads by hand every run that fails only on them.
3. What the run cost and did: merged or not, attempts by step, review rounds and findings, person waits by
   reason, person acts the replay stood in for, the worker's and reviewer's cost, minutes, changed lines, and
   any trend numbers a later feature adds on the changed files.

A run solves the ticket when it merged and every check passed in step 1, with step 2's tests when they are set.

Which tickets qualify: `--pick` takes merged tickets, newest first, that:
- have at least one `Check:` line that was red on the base at the first claim (`base_checks`,
  `engine/docs/journal.md`);
- kept their Done Contract, had no open `ASSUMED:` rows at the start, and run under the current engine (steps
  2 and 3 of the copy);
- have no `adopted` event: an adopted ticket's contract and scope were written from finished work
  (`engine/rail/adopt.py`);
- were not reverted, and are not named in a later `caused_by`, so the change that passed was right;
- pass the oracle and null grades on the current machine.

Oracle and null grades: outside the loop, with no model, the grade's steps 1 and 2 run on a copy with the
original squash's product diff applied (the oracle), and on the copy as it is (the null). The oracle must pass
and the null must fail. An oracle that fails means the copy cannot rebuild an environment the checks pass in;
a null that passes means the checks cannot tell done from not done. Either way the ticket does not qualify.
They run outside the loop because through it the oracle would need a review (a model), and the null would
spend attempts up to the retry cap. `--pick` prints how many tickets were left out and why.

The report: `rail replay --report` compares arms on the same tickets, ticket by ticket: solve rate, cost per
solve, attempts, person waits by reason, person acts the replay stood in for, review rounds, and trend
numbers. It prints how many tickets and runs each number rests on.

Where results live: under the git directory, `.git/rail/replays/`, where the engine already keeps its cache
(`engine/rail/project.py`), so they cannot be committed by mistake. Each run's journal, stream, grade and the
result's diff.

Uses: the worker ladder and the reviewer's model, arms per rung, as the paused model tests planned (owner,
2026-11-20); a change to a skill, a brief or `reviewer.md`, the old page against the new on the same tickets,
which is how guide changes are kept ("Change it on evidence", `engine/docs/guides.md`); model arms in other
features' tests; the pilot of **The runner calls `rail work`**, with `rail work` as the arm.

Order of work, one pull request each with docs and `CHANGELOG.md`: first `rail replay NN` with the copy, the
ticket as filed, the run, the grade, the oracle and null grades, and the taint search; then `--pick`,
`--runs`, `.rail/replay.toml` arms and `--report`.

**Kept when.**
- Gate cases, no model, the worker is a script:
  - The copy has one commit, no remote, no file from the original change, and a `Ticket:` line for every
    earlier merged ticket. A ticket whose `after` names an earlier one starts without waiting.
  - `GH_TOKEN` is unset and `gh auth status` fails in the copy.
  - The ticket is filed with each part as the table says. A ticket with a changed Done Contract, open
    `ASSUMED:` rows at the start, or an `adopted` event is not taken by `--pick`.
  - The oracle grade passes and the null grade fails on a planted ticket. A planted ticket whose checks pass
    on the base is not taken.
  - A scripted worker that applies the original diff runs through the loop with a stub reviewer and merges. On
    a PERSON ticket, the replay's `rail accept NN` is counted.
  - A wait for a person ends the run with its code.
  - A planted WebFetch of the original pull request's URL marks the run `tainted`. A `go test` on a module
    path that contains the repository name does not.
  - The report counts the same tickets for every arm.
- Pilot, with a model: eight tickets from one project, the arm `as-is` and one other arm, two runs each.
  Recorded: the share of runs that solve; that no run is `tainted`; the tickets whose two runs differ;
  the cost against the original ticket's; each run that fails only on the original's tests, read by hand. Kept
  when at least three of the five tickets are solved in some run of `as-is`. A set where the current setup
  cannot do the work cannot compare arms.

Not covered: tickets whose checks need services or secrets the copy does not have (the oracle grade fails, so
they do not qualify); answers a person gave during the work, which are not in the ticket as filed; whether a
project's tickets are hard enough to separate strong arms (the pilot shows the solve rate).

**Waits for.** `rail work` (built). The owner restarting the paused model tests (the pilot). The owner taking
up the set-aside features again.

**Open decision.**
1. The default `--runs`: three (proposed).
2. Whether `[replay] tests` is asked for at `rail init`, or left for when a project first replays (proposed:
   the latter).
3. Whether replay results are ever committed, such as a summary per arm in `EVIDENCE.md`. Proposed: no, until
   the pilot shows the numbers are stable. (`EVIDENCE.md` was dropped from the Rail repository on 2026-11-26;
   a project's own file would be meant.)
4. Whether `accepted` should keep the Done Contract's text, so tickets whose contract changed could qualify
   too. Proposed: not until `--pick` shows too few tickets qualify.

**Assumed, not verified.**
- That a worker kept out of the forge cannot reach the finished change some other way, such as a package
  registry that already holds a later release of the project. The taint search catches only what it looks for.
- That the squash commit's parent, with the ticket's own `setup`, rebuilds an environment the checks pass in.
  The oracle grade tests this per ticket.
- That enough tickets keep their Done Contract and start with no open `ASSUMED:` rows to make a set.
- That two runs per ticket over eight tickets are enough to see an arm's effect. The pilot shows whether more
  tickets are needed.

#### Held-out scenarios

Size: M.

**What it does.** Scenario checks are written when the ticket is made and kept where the worker does not read
them, so that who writes the tests is not who writes the code. The ship fails on a red scenario. This follows
StrongDM's practice, for which no outcome data is published. It is built only if its test shows it catches
what **Old tests run against the new code** and **Wording about tests, for the reviewer and the worker** miss.

**How.**

- The contract writer (`TICKET_LINT`, run on `[worker] contract`) also writes one to three `Scenario:` lines:
  commands like `Check:` lines, that drive the behaviour from outside.
- They are stored on the ref `refs/rail/holdout/NN`, not in the ticket file, so the worker's brief and
  worktree never hold them.
- The guard denies a Bash command that names `refs/rail/holdout`. This is mistake prevention: a worker that
  goes looking can still find them, and the worker's run log shows whether it did.
- At ship the engine runs them after the `Check:` lines. A red scenario fails the ship with its name and exit
  code, not its text, so the brief does not hand the scenario to the worker.
- Files that change: `engine/docs/tickets.md`, `engine/docs/contract.md`, the guard's deny rules, the contract
  writer's prompt, the ship step.
- Against it: hiding tests costs the worker performance (ImpossibleBench); held-out tests gave "only minimal
  improvement" over a model judge on EvilGenie; a failure the worker cannot read is hard to fix, and a wrong
  scenario would spend attempts up to the cap. All reported, not read again.

**Kept when.** A model test, needs `rail replay`. Arms with and without held-out scenarios: kept when the
scenarios fail on some runs that **Old tests run against the new code**, the wording features and the review
let through, and the solve rate drops by less than the share of bad changes they catch.

**Waits for.** `rail replay`, which the owner has set aside (2026-11-26), and the worker's run log. The owner
restarting model tests.

**Open decision.** Drop held-out scenarios, or test them once `rail replay` exists. Proposed: leave them
unbuilt while replay is set aside.

**Assumed, not verified.**

- That a scenario written by the contract writer is right often enough that a failure the worker cannot read
  does not spend attempts on a wrong scenario. Not tried.

## Tried on GitHub itself, and not yet

The suite runs against a stand-in for GitHub. On 2026-11-26 the current Rail was set up in a real repository
from cloud sessions. What follows is what that showed; each "reported" line was run by a cloud session and not
run a second time.

Worked:

- `rail init`, and the `rail` check on GitHub's runner: `provision`, then the whole `verify`.
- `rail doctor` reading the repository's settings: squash merging, the required check, deletion of merged
  branches, the labels.
- Reading pull requests through the REST API (reported).
- Opening an issue with the label `rail:needs-you` and closing it (reported).
- A `COMMENT` review with one comment placed by file and line, with `commit_id`, on a pull request the same
  account opened (reported).
- Pushing a branch whose name does not start with `claude/` (reported).

Refused:

- Listing the repository's Actions secrets and its environments: the session's proxy answers 403. `rail doctor`
  then says it could not check them.
- Deleting a branch.

Not yet tried:

- A ticket carried from a labelled issue to its merge by a runner, on the current engine.
- The engine's own "Read these" comments on the lines of a pull request.
- The issues endpoint returning merged pull requests with a label when asked for closed items.
- GitHub folding a file marked `linguist-generated` in a pull request's diff.

## Left out on purpose

None of these is to be built. A project that wants one uses what Rail has.

- A browser layer of Rail's own: Playwright, the Chrome DevTools server and Maestro exist.
- Stacks, app templates or integrations for one platform: `[product]` and `[preview]` hold commands the
  project names.
- A webhook server, and deciding how many sessions run and when: the host's concern.
- Runs of the same ticket side by side with the best one kept. A ticket has one line of work.
- A formal-proof gate: a project that proves a component puts the prover in `verify` or a `Check:` line.
- A design review step by a person.
- An `upgrade` verb: a project takes Rail's changes through a source (**Taking Rail's changes into a project**).
- Reminders to rotate a credential.
- Short-lived apps with a retire-by date as a kind of ticket: Rail is for code with a future, and a project
  can drop an app with a ticket.
- Languages other than Python, TypeScript, Rust and Go, for now; Windows.
- Work across repositories. A Rail serves one repository: no ticket, wait, inbox or number spans two.
- Any earlier version of Rail. No feature reads, converts or keeps working with what an earlier Rail wrote.

## What the owner has decided

Stated here once, as facts the features rest on.

- A person bears responsibility for what can't be undone, and only for that. Review before merge stays: the
  machine's review runs on every AUTO change (2026-11-25).
- Rail is for software development. Python, TypeScript, Rust and Go come first (2026-11-25).
- Rail keeps no compatibility with its earlier versions. No decision weighs what it would cost a project that
  already holds a copy of Rail (2026-11-27).
- Rail is developed without Rail: its own repository has no `.rail/`, and no feature adds one (2026-11-26).
- A feature that needs model runs builds its part that needs none, and marks its wording as not tested
  (2026-11-26).
- Secrets reach a pull request's CI only as keys declared `ci = true` (built).
- The unit of planning is a feature, in the order of this page; the steps under "Next" are confirmed
  (2026-11-26). **Taking Rail's changes into a project** was one of them and is set aside (2026-11-27).
- `## Read these` and its line comments stay on the pull request of an AUTO ticket, for whoever chooses to
  read one. They ask nothing of anyone (2026-11-27).
- Where the worker judged its own case, a fresh run with no stake answers one closed question the engine
  raises (2026-11-27).
- A person acts once on a PERSON ticket, at the merge. Approval of a contract before the build is a setting,
  off unless a project turns it on for a kind (2026-11-27).
- A stuck ticket gets one diagnosis before it is dropped or waits (2026-11-27).
- A Rail serves one repository (2026-11-27).
- Anything may be put into a repository, and Rail drives what needs driving. What Rail knows about a
  repository is worked out from the tree on every change, not written once at `rail init`, and what no check
  reads is a fact that raises a question (2026-11-27).
- A model test runs many situations twice each, not a few four times, and is decided over the set
  (2026-11-27).
- A check that produces a fact is built before wording that asks a model for the same behaviour. The wording
  is added only when a model test shows it moves the number that check reports (2026-11-27).

## Dropped

The owner decided on 2026-11-26 not to build these.

- **The label `rail:look`** and its saved search for merged AUTO pull requests. It was built, and it is
  removed. An AUTO change can be undone, so Rail marks none for a person to read; an agent of the person's own
  can gather what they want to look at from the pull requests and the journal.
- **The reviewer's `attention` field**: lines a reviewer names for a person to read after the merge. With no
  label that sends a person there, it has no reader.
- **Support for GitHub's merge queue.** **One rebase at a time** is the answer to rebases that pile up, if they
  do.
- **One label for each ticket state**, kept current for a board. `proposals/team.md` still describes it in
  its section on the shared view; that page is brought up to date last.
- **A local sudo grant for `rail provision`.** On a person's own machine `rail provision` shows the command and
  the person runs it.

The owner decided on 2026-11-27 not to build these.

- **One inbox across repositories**: a saved search over the waits of many repositories. A Rail serves one
  repository.
- **A `Uses` column in the areas map**, and boundary sensors built from it. `uses` in `[[projects]]` is the only
  graph.
- **`[[profiles]]` beside `[[projects]]`.** One table, `[[projects]]`, takes its place.
- **An entry for each project written by `rail init`**, infrastructure folders found at init, and a profile
  for Terraform. Projects are derived on every change, and a new kind of thing is covered by a ticket.
- **A language added after init: what is left**: whether init writes a missing entry into the config. With
  derived projects no entry is missing.
- **Roles in place of model names**: a `[models]` table that the ladders and seats would name. The model names
  stay where they are in the config.
- **A blocking finding of the engine's that the worker answers**, for an old test that fails on the new code.
  The triage run answers it.
- **`.gitleaksignore` in `person_paths`.** A line in it raises a question for the triage run.
