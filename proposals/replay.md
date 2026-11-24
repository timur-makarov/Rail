# Merged tickets as a test set: what could be built

This page is a proposal. None of it is implemented. It says how Rail could run a merged ticket again, on a clean
copy of the code as it stood before the merge, with a different model, effort, prompt or setting, and grade
the result. Status: written 2026-11-25 from Rail's engine code and docs and the Boundary talk with Warp's
founder (sources at the end). Nothing here was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

Rail has choices that only runs can settle: the worker ladder's models and efforts (`seed/config.toml`
`[worker]`), the reviewer's model, every change to a skill or a brief, and the arms in the entropy, worker
and oversight proposals. Test tasks written for the purpose are few, cost a person's time, and may not look
like the project's real work. Each merged ticket is already a graded task (inferred from what the journal and
the base branch keep):

- the request and the contract: `## Request`, `## Why`, the Done Contract, `scope_paths`;
- the code it started from: the parent of its squash commit on the base branch;
- what "done" meant: the `Check:` lines of its contract, and the change that passed them;
- what it cost and how it went: its journal (steps, attempts, review rounds, waits, and with
  `proposals/worker.md` the worker's cost).

Warp builds the same thing from recorded runs: a run's model, environment and starting commit make it a task
to replay, and a set of real tasks becomes a team's own benchmark. They warn that the replayed agent must not
see the finished work, or it copies it (reported, Boundary talk, 28:53-30:13).

## What changes

A new verb, `rail replay`:

```text
rail replay NN [--arm NAME] [--runs K]     # one merged ticket
rail replay --pick N [--arm NAME] [--runs K]  # N tickets from the merged ones that qualify
rail replay --report                       # compare the arms run so far
```

An **arm** is a named set of overrides in `.rail/replay.toml`: `.rail/config.toml` keys that the current
engine knows (the ladder, the reviewer's model, `[worker] command`), and files to put in place of the copy's
(a skill page, `reviewer.md`). The arm `as-is` changes nothing. An arm can't change engine code: a choice that
needs new engine code (such as the entropy proposal's `sensors` step) becomes an arm once that code is in the
project's engine and a config key turns it on.

### The copy the worker sees

1. **The code.** A new repository, outside the project, holding one commit: the tree of the squash commit's
   parent. It has no remote, no other commit and no branch but the base, so the finished change is nowhere in
   it (inferred: a fresh `git init` with one commit has no history to read). The commit's message has a
   `Ticket: NN` line for every ticket merged on the base before that parent, so the engine sees those tickets
   as merged, not dropped. Without them, a ticket whose `after` names one would wait as `AFTER_DROPPED`
   (`engine/rail/project.py:155-166`, `engine/rail/state.py:262-263`, confirmed).
2. **The engine.** The project runs its own engine from `.rail/engine/` (`bin/rail`, confirmed), and the
   parent's may be older than the arms need: the config loader refuses keys it doesn't know
   (`engine/rail/config.py:52-53`, confirmed), and an engine from before `rail work` can't run a worker.
   So the copy takes `.rail/engine/`, `.rail/bin/` and `.claude/` from the project's current base, and
   `.rail/config.toml` from the parent, with the arm's overrides on top. A ticket whose old config the current
   engine refuses doesn't qualify. Replay measures the current setup on old tasks, not the old setup.
3. **The ticket.** A ticket qualifies only when its Done Contract never changed: the merged file's Done
   Contract hashes to the `done` of its first `accepted` event. That event keeps the hash, not the text
   (`engine/rail/cli.py:656-659`, confirmed), and the engine finds the first text from the ticket's branch
   (`engine/rail/review.py:225-229`, confirmed), which is deleted after the merge. With the hashes equal, the
   merged text is the first text, and the worker is graded on the checks it was given. Each part of the
   ticket file:

   | Part | In the copy |
   |---|---|
   | `## Request`, `## Why`, `## Grilling`, `## Out of scope`, the Done Contract | Kept from the merged file |
   | `scope_paths` | From the first `accepted` event |
   | `tier`, `after`, `reversibility`, `rollback` | Kept from the merged file's front matter |
   | `caused_by`, `external_id` | Dropped: they point at the project's forge |
   | `## Assumptions` | Left empty. The merged section holds the worker's `VERIFIED:` answers, and the open `ASSUMED:` rows are lost with the branch. A ticket whose `requested` event has `assumed` above 0 doesn't qualify |
   | `## Look at`, `## Tried`, anything else the work wrote | Dropped |

   The replay accepts the contract with `rail accept NN` for a PERSON ticket, standing in for the person who
   approved it then.
4. **The forge and the network.** The replay runs with no remote, so Rail works locally and merges with
   `rail advance` (`engine/docs/loop.md`, "With no remote", confirmed). `GH_TOKEN` and `GITHUB_TOKEN` are
   unset, and `GH_CONFIG_DIR` points at an empty folder, since `gh` keeps its own stored login. `RAIL_CLOUD=0`,
   so no `rail provision` runs. The sandbox's `allowedDomains` limits Bash, not the web tools
   (reported, Claude Code docs; Rail's sandbox is in `engine/docs/guards.md:86-97`), so the replay brief says the forge is out of bounds, and the
   run is searched afterwards (below).

### The run

The replay acts as the runner. It calls `rail next` and acts on each answer until the ticket merges in the
copy, waits for a person, or is dropped:

- an answer whose action is a `rail` command (`rail advance`, `rail next`) runs as given;
- a `rail work` answer runs the arm's worker command, through `rail work` (`proposals/worker.md`);
- a PERSON ticket's merge wait is answered with `rail accept NN`, as in step 3 above, and counted in the
  report as a person's act the replay stood in for;
- any other answer for a person or for an agent outside `rail work` (`SETUP_FAILED`, `RED_BASE`, a finding
  that waits for a person) ends the run, and its code is the outcome.

`--runs K` (3 by default) repeats each ticket, each on a new copy. The worker command's whole stream is kept
for the run, uncut.

### The taint search

Every tool input in the stream (Bash commands, WebFetch URLs, WebSearch queries, file paths) is searched for:
the original pull request's URL, `OWNER/REPO/pull/`, `OWNER/REPO/commit/`, the squash commit's hash (its
first 7 characters or more), and `gh` commands. A hit marks the run `tainted`, and the report leaves it out.
The bare repository name is not searched: Go module paths and scoped npm names contain it, so ordinary
commands would match.

### The grade

Each run is graded on a new copy of its result:

1. **The checks.** Each `Check:` line of the ticket's contract, run as ship runs it. These are the checks the
   worker was given (step 3 above).
2. **The tests the original added.** With `[replay] tests` set (globs such as `tests/**` or `**/*_test.go`),
   the files the original change added or changed under those globs are copied over the result first, so the
   checks also run the original's own tests. Without it, the run is graded with the worker's own tests, and
   the report says so: that grade is weaker. The original's tests can name things a valid solution names
   differently; the pilot reads by hand every run that fails only on them.
3. **What the run cost and did:** merged or not, attempts by step, review rounds and findings, person waits by
   reason, person acts the replay stood in for, the worker's and reviewer's cost, minutes, changed lines, and
   with the entropy proposal the trend numbers on the changed files.

A run **solves** the ticket when it merged and every check passed in step 1, with step 2's tests when they are
set. The entropy proposal's "strict solve rate" on replayed tickets is this share.

### Which tickets qualify

`--pick` takes merged tickets, newest first, that:

- have at least one `Check:` line that was red on the base at the first claim (`base_checks`,
  `engine/docs/journal.md`, confirmed);
- kept their Done Contract, had no open `ASSUMED:` rows at the start, and run under the current engine
  (steps 2 and 3 above);
- have no `adopted` event: an adopted ticket's contract and scope were written from finished work
  (`engine/rail/adopt.py:83-107`, confirmed);
- were not reverted, and are not named in a later `caused_by`, so the change that passed was right;
- pass the oracle and null grades below on the current machine.

**Oracle and null grades.** Outside the loop, with no model: the grade's steps 1 and 2 run on a copy with the
original squash's product diff applied (the oracle), and on the copy as it is (the null). The oracle must
pass and the null must fail. An oracle that fails means the copy can't rebuild an environment the checks pass
in; a null that passes means the checks can't tell done from not done. Either way the ticket doesn't qualify.
They run outside the loop because through it the oracle would need a review (a model), and the null would
spend attempts up to the retry cap; outside it, each is one run of the checks.

### The report

`rail replay --report` compares arms on the same tickets, ticket by ticket, as the entropy proposal's model
arms do (`proposals/entropy.md`, Tests 3): solve rate, cost per solve, attempts, person waits by reason,
person acts the replay stood in for, review rounds, and the trend numbers. It prints how many tickets and
runs each number rests on.

Results live under the git directory, `.git/rail/replays/`, where the engine already keeps its cache
(`engine/rail/project.py:233-235`, confirmed), so they can't be committed by mistake: each run's journal,
stream, grade and the result's diff.

## Uses

- The worker ladder and the reviewer's model: arms per rung, as the paused model tests planned (owner,
  2026-11-20).
- A change to a skill, a brief or `reviewer.md`: the old page against the new on the same tickets, which is
  how guide changes are kept today ("Change it on evidence", `engine/docs/guides.md:62`, confirmed).
- The model arms of `proposals/entropy.md` (Tests 3), on the project's own tickets beside SlopCodeBench, once
  each part's engine code is in the project's engine.
- The pilot in `proposals/worker.md`, with `rail work` as the arm.

## Tests, each before its part is kept

1. **Gate cases, no model.** The worker is a script.
   - The copy has one commit, no remote, no file from the original change, and a `Ticket:` line for every
     earlier merged ticket. A ticket whose `after` names an earlier one starts without waiting.
   - `GH_TOKEN` is unset and `gh auth status` fails in the copy.
   - The ticket is filed with each part as the table says. A ticket with a changed Done Contract, open
     `ASSUMED:` rows at the start, or an `adopted` event is not taken by `--pick`.
   - The oracle grade passes and the null grade fails on a planted ticket. A planted ticket whose checks pass
     on the base is not taken.
   - A scripted worker that applies the original diff runs through the loop with a stub reviewer and merges.
     On a PERSON ticket, the replay's `rail accept NN` is counted.
   - A wait for a person ends the run with its code.
   - A planted WebFetch of the original pull request's URL marks the run `tainted`. A `go test` on a module
     path that contains the repository name doesn't.
   - The report counts the same tickets for every arm.
   Kept when every case behaves as written.
2. **Pilot, with a model.** Five tickets from one project, the arm `as-is` and one other arm, three runs each.
   Recorded: the share of runs that solve; that no run is `tainted`; the spread of the three runs per ticket;
   the cost against the original ticket's; each run that fails only on the original's tests, read by hand.
   Kept when at least three of the five tickets are solved in some run of `as-is`. A set where the current
   setup can't do the work can't compare arms. This uses models, so it waits for the owner to restart the
   paused model tests.

Not covered: tickets whose checks need services or secrets the copy doesn't have (the oracle grade fails, so
they don't qualify); answers a person gave during the work, which aren't in the ticket as filed; whether a
project's tickets are hard enough to separate strong arms (the pilot shows the solve rate).

## Assumed, not verified

- That a worker kept out of the forge can't reach the finished change some other way, such as a package
  registry that already holds a later release of the project. The taint search catches only what it looks
  for.
- That the squash commit's parent, with the ticket's own `setup`, rebuilds an environment the checks pass in.
  The oracle grade tests this per ticket.
- That enough tickets keep their Done Contract and start with no open `ASSUMED:` rows to make a set. `--pick`
  prints how many were left out and why.
- That three runs per ticket are enough to see an arm's effect. The pilot's spread shows whether more are
  needed.

## Order of work

One pull request each, with docs and `CHANGELOG.md`. Step 1 needs `rail work` from `proposals/worker.md`.

1. `rail replay NN` with the copy, the ticket as filed, the run, the grade, the oracle and null grades, and the
   taint search.
2. `--pick`, `--runs`, `.rail/replay.toml` arms, `--report`.

## Decisions

**Open:**

1. The default `--runs`: three (proposed).
2. Whether `[replay] tests` is asked for at `rail init`, or left for when a project first replays (proposed:
   the latter).
3. Whether replay results are ever committed, such as a summary per arm in `EVIDENCE.md`. Proposed: no,
   until the pilot shows the numbers are stable.
4. Whether `accepted` should keep the Done Contract's text, so tickets whose contract changed could qualify
   too. Proposed: not until `--pick` shows too few tickets qualify.

## Sources

Rail, confirmed: `bin/rail`, `engine/rail/cli.py`, `engine/rail/config.py`, `engine/rail/project.py`,
`engine/rail/review.py`, `engine/rail/state.py`, `engine/rail/adopt.py`, `engine/docs/journal.md`,
`engine/docs/loop.md`, `engine/docs/guards.md`, `engine/docs/guides.md`, `seed/config.toml`.

Reported: "How to Build an AI Software Factory That Ships Faster", Boundary's AI That Works, with Warp's
founder, https://www.youtube.com/watch?v=XUEfIxkdT2Q, transcript read on usetranscribe.io on 2026-11-25.
