# The triage step

Where a worker would judge its own case, a run with no stake in the answer judges it. The engine states a fact
it produced itself, such as a test that fails or a line the change added. A fresh run that did not write the
change answers one closed question about that fact, with one of a few fixed answers. The engine then does what
the answer means. The refuter works this way for one question, whether a finding holds (`rail docs review`);
triage is that step with a table of question types, so a new question costs a table entry and its test.

Only closed questions go here. Whether a change is good stays the reviewer's question.

## How a question runs

- **Raised at ship.** When every ship step has passed, each type looks for its fact in the patch. A fact found
  is a `question` event with the type, the `patch_id` and the fact (`rail docs journal`). One fact raises one
  question for a patch: shipping the same patch again raises nothing. One type, `stuck`, is not about a patch:
  it is raised for a ticket at its retry cap, and what this list says about patches does not hold for it ("A
  ticket at its retry cap", below).
- **Answered before any review.** A shipped ticket with an open question is `reviewing`, and `rail next`
  answers `TRIAGE` with `rail advance NN`. `advance` starts one run for each open question, then the review
  runs the patch needs, so no review is spent on a patch that is about to change. A ticket whose change needs
  no reviewer (`[review] skip_paths`) still gets its questions answered.
- **The run** starts as a review run starts: in the ticket's worktree, with the brief on stdin, tools that read
  and run, and no push. The brief holds the question, the answers with what each means, the fact, and only
  what the type says to show: never the whole change. `[triage] command` and `[triage] model` name the command
  and the model; empty means `[review]`'s. The command gets `RAIL_REVIEW_PROMPT` (the path of the triage
  prompt), `RAIL_REVIEW_SCHEMA` (the path of the schema its JSON answer must match: `answer`, `reason`, and
  `evidence` where the answer asks for it) and `RAIL_TRIAGE` (the type). The worktree is put back afterwards.
- **An answer that lets the change through** is an `answered` event, and the ticket goes on. Where the type
  asks such an answer for evidence, the engine checks what it can: a quoted contract line is in the ticket, a
  named file is in the change. The event's `evidence_ok` says how the check went.
- **An answer that stops the change** fails the step `triage`. The ticket is `implementing` again, and the
  worker's brief (`STEP_FAILED`) holds the question, the fact, the answer with what it means, the run's reason
  and what to do; `action.facts.triage` has the same as values. The failure counts toward the retry budget
  like any failed step (`rail docs retries`), and two stops by the same answer to the same type are the same
  failure. Nothing goes to the refuter: a second run on the first one's answer is not added.
- **An answer that holds the ticket for a person** fails `triage` too, and the ticket then waits for a person
  under the wait the answer names. Only `secret` has one (`SECRET_FOUND`, below).
- **The next patch** is asked again only if the fact still holds. The same patch shipped again keeps its
  stopping answer, and `triage` fails with no run, unless `rail amend` changed the contract since: the contract
  is part of what was asked, so the question is raised once more.
- **A line the author wrote** is asked about once. Where the fact is such a line and not what the patch does
  (a comment, a row of the ticket, a line of `.gitleaksignore`), an answer that lets it through stands for the
  ticket's later patches too, while the line stays as it is and until `rail amend` changes the contract.
- **No answer.** A run that passes `timeout_secs`, answers with something the schema does not allow, or names
  evidence that is not where it says, fails `triage` with `counted: false`: it is the run's fault, and no
  attempt of the author's is spent. The run is started once more. Two in a row wait for a person
  (`STUCK_REVIEW`, as for a review with no verdict), who looks at why and continues with `rail accept NN`.
- **CI** fails at `triage` while a question about the head's patch is open, or answered with what stops the
  change, as it fails at `review` while the review is not complete.

## The question types

The table is `QUESTIONS` in `.rail/engine/rail/triage.py`. An entry holds the type's id, the fact that raises
it, the question, what the brief shows, two to five answers with what each means and whether the ticket then
goes on, stops or waits for a person, and, for an answer that lets the change through, the evidence it must
name and the engine's check of it.

| Type | Raised when | Answers that let the change through | Answers that stop it |
|---|---|---|---|
| `old-test` | A command that passed at ship fails with the base branch's version of the test files the change edits | `contract`, `moved` | `lost` |
| `sensor-exempt` | The change adds a `SENSOR(NN): why` comment that excuses a sensor's violation | `holds` | `does-not-hold` |
| `decided` | The ticket gains a `VERIFIED: decided, not checked:` row | `choice` | `checkable`, `contract` |
| `secret` | The change adds a line to `.gitleaksignore` | `not-a-secret` | `secret`, which waits for a person |

### `old-test`: old tests run against the new code

The `Check:` lines are frozen at acceptance, and the test files they run are not. A change can pass by bending
its own checks: an assertion removed, a test deleted. So when every ship step has passed, and the change edits
or deletes a file the base branch has that matches `[tests] paths`, the engine runs the checks once more with
the base's version of those files:

1. In the ticket's worktree it checks out the base's version of each such file. A renamed file counts under
   its old path, wherever it went, and a deleted one is put back. A test file the change adds is the author's
   own and is left alone.
2. It runs `verify` and each `Check:` line, as ship runs them.
3. It puts the worktree back as the change has it. Ignored files, such as installed dependencies, stay.
4. It records a `base_tests` event: the patch, the files, and for each command `green`, `red`, `could_not_run`
   or `timed_out` (`rail docs journal`).

It runs once for a patch, so a clean rebase does not run it again, and it fails no step by itself. It runs at
ship only, not in `rail ci`: CI repeats what can fail a ship. An empty `[tests] paths` switches it off. `rail
init` fills the list from the language profiles (`rail docs languages`); add the files that hold the runner's
settings, such as `vitest.config.*` or `conftest.py`, when a profile lacks them.

A command that was green with the change's tests and is `red` with the base's raises one `old-test` question
for the patch. The run is shown the diff of those test files, where to read the old version whole, each such
command with the end of its output, and the ticket's `## Why` and Done Contract. It is not shown the rest of
the change.

| Answer | Means | Evidence the engine checks | What the engine does |
|---|---|---|---|
| `contract` | The contract asks for this change in behaviour | The quoted Done Contract line or `## Why` sentence is in the ticket | Records it; the ticket goes on |
| `moved` | The behaviour is kept; the test was moved, renamed or rewritten | The named file is in the change and matches `[tests] paths` | Records it; the ticket goes on |
| `lost` | Behaviour is lost that the contract does not ask for | None | Fails `triage`; the worker keeps the behaviour, or amends the contract so that it asks for the change |

What this costs was measured on the history of three open-source repositories, one for each of three language
profiles (`tests/history/old_tests.py` in Rail's own repository, with the results beside it; the commits were
written by people, and a commit's message stood for the contract):

| Repository | Commits read | Edit a test file the parent had | Of those that could run: red with the old tests |
|---|---|---|---|
| more-itertools (Python) | 400 | 151 (38%) | 21 of 151 (14%) |
| pflag (Go) | 240 | 112 (47%) | 5 of 37 (14%) |
| ufo (TypeScript) | 300 | 72 (24%) | 9 of 61 (15%) |

So between a quarter and a half of such changes pay for one more run of the checks, and about one in seven of
those pays for a triage run. The 35 red results, each read and sorted by hand: `contract` 26, `moved` 5,
`lost` 4. Three of the five `moved` results failed for the old test file's own reason and not for a behaviour:
the tests had moved to a new file, a newer `go vet` refused the old file, the project had changed its test
runner. The sorted results are the answer key for this type's model test, which has not run.

The reviewer is told what the change did to its own checks (`rail docs review`). Not covered: a test that
needs a service or a secret the ticket's machine lacks fails with both versions and raises nothing; and Rust's
unit tests live inside source files, so there only the integration tests under `tests/` are covered.

### An exemption the author writes

Three lines an author can write excuse the change from a check. The engine used to take each at its word. Each
now raises a question, and each is asked once for the line (see "A line the author wrote" above).

**`sensor-exempt`.** A `SENSOR(NN): why` comment makes the engine drop a sensor's violations on its line and
the line below (`rail docs sensors`). The `sensors` step records what each comment excused, and a comment the
change adds that excused something raises one question. A comment the base branch already had raises nothing,
and neither does one that excuses nothing. The run is shown the sensor's lines, what the sensor asks for, the
file around the comment, and the ticket's `## Why` and Done Contract.

| Answer | Means | Evidence the engine checks | What the engine does |
|---|---|---|---|
| `holds` | The sensor misreads the line, or the contract requires the line as it is | Where the contract requires it: the quoted Done Contract line or `## Why` sentence is in the ticket. None where the sensor misreads the line | Records it; the ticket goes on |
| `does-not-hold` | The sensor is right about the line, and the contract does not require it | None | Fails `triage`; the worker takes the comment out and mends the line |

**`decided`.** A `VERIFIED: decided, not checked:` row says that nobody could check an assumption, so its
author chose (`rail docs tickets`). Each such row the ticket has at ship, and the base branch's copy of the
ticket lacks, raises one question. The run is shown the row, the ticket's `## Why` and Done Contract, and the
ticket's scope.

| Answer | Means | Evidence | What the engine does |
|---|---|---|---|
| `choice` | Nothing in the repository or its dependencies settles it, and no Done Contract item depends on it | None | Records it; the ticket goes on |
| `checkable` | It can be checked | Where: the file, the command or the document that settles it | Fails `triage`; the worker checks it and writes in the row how |
| `contract` | A Done Contract item depends on it | That item, word for word | Fails `triage`; the worker states the choice in that item, takes the row out of `## Assumptions` and runs `rail amend NN "why"`, so the choice stands where the reviewer reads it |

**`secret`.** A line of `.gitleaksignore` takes one finding out of the secret scan (`rail docs languages`). It
is the answer to a false finding: the scan reads every commit of the branch and a branch is never rewritten,
so changing the line that was found does not help. Each line the change adds to the file raises one question.
The file is in every ticket's scope, whatever `scope_paths` says. The run is shown what the line's fingerprint
names (the scan's rule, the file and line, the commit) and the file at that commit around the finding. The
string itself is shown only as the scan redacts it: the engine asks gitleaks for that one commit's report, and
where gitleaks is not on the machine or reports nothing, it shows the lines above the finding and leaves the
finding and what follows it out.

| Answer | Means | Evidence the engine checks | What the engine does |
|---|---|---|---|
| `not-a-secret` | The string is no credential: an example, a fixture, a public id | It says what the string is | Records it; the ticket goes on |
| `secret` | The string is, or may be, a real credential | None | Fails `triage`; the ticket waits for a person (`SECRET_FOUND`) |

A real secret on a pushed branch counts as leaked. The person rotates it where it was issued and continues
with `rail accept NN` or the label `rail:go`. The engine then starts the ticket's branch again from the base
branch (`RESTART`, which `rail next` does): the scan would fail on the old branch's commits for good. The new
branch is named after the old one with `--2` at its end (then `--3`), and holds one commit on the base's tip
with the ticket and its journal. None of the work comes along, since the work is where the secret is; work
nobody committed is put into a git stash on that machine. The old branch is deleted and its pull request
closed, and the ticket gets a new pull request. A cloud session's git access can't delete a branch: there the
old branch stays on the remote, and every clone reads the branch with the highest ending. A `restarted` event
records the move (`rail docs journal`), and the worker's next brief says that the work is to do again with no
credential in any file. Another clone that still has a worktree on the old branch removes it by hand.

Checked with gitleaks 8.24.2: a line in `.gitleaksignore` takes its finding out of `gitleaks git`. Assumed, not
verified: that a redacted finding with the lines around it is enough to tell an example from a secret.

## A ticket at its retry cap

The type `stuck` is not about a patch. `rail next` raises it once for a ticket that reaches its retry cap, or
its budget after consult, before the ticket is dropped or waits, and its run uses the contract writer's model
(`[worker] contract`). Its five answers are `contract`, `too-large`, `approach`, `machine` and `cannot-tell`,
and each names what the engine does next, not whether a change goes through: `rail docs retries` has the
table. A run with no answer is started once more; after two the ticket is handled as with `cannot-tell`, and
no wait for a person follows from the runs themselves.

## What to read in the numbers

`rail stats` has a `TRIAGE` table (`rail docs stats`): for each type the questions asked about the merged
tickets' patches, the runs, the runs that gave no answer, what the runs reported they cost, and each answer's
share. The sweep (`rail docs sweep`) names a type whose last 20 answered questions got the same answer 19
times or more. Such a type is no longer a question: it is a rule the engine can apply with no run, and the
sweep's ticket makes it one or removes the type.

The prompt and the briefs of this step have not been tested with a model run.
