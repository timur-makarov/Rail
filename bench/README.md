# The bench

The bench measures Rail against plain coding agents on real issues with hidden tests. The plan it is built from is
the fulltest `PLAN.md`, sections 3 to 5. It needs Python 3.11 and git, and nothing outside the standard library.

Run it as `bench/bench VERB ...` from anywhere. Everything it builds goes into the store: `$BENCH_STORE`, or
`store` in `bench/config.toml`, or `~/.rail-bench`.

## Add a project

1. Make `bench/sets/SET/PROJECT.toml`. SET is the month of the set, such as `2026-12`.
2. `[project]` names the repository (`repo`, a URL git can clone), its `language` (python, typescript, rust or go),
   the project's own package name (`package`, for the taint search), and `tests`, globs that match its test files.
3. `[commands]` says how to test it:
   - `setup` runs once when a sealed copy is built, with the network. Fetch every dependency here, into the copy or
     into `$BENCH_CACHE`, so the copy builds offline later.
   - `test_files` runs the given test files: `{files}` is replaced by them.
   - `test_package` runs one package's tests: `{package}` is replaced by it.
   - `package_of` says how a changed path gives its package: `root` (the whole project), `dir` (its folder), `top`
     (its first folder), `nearest:Cargo.toml` (the nearest folder above it holding that file), or
     `regex:PATTERN` (the pattern's first group).
   - `failed` is a regex whose first group names a failing test in the output, such as `^--- FAIL: (\S+)` for Go.
   - `env` is set for every command, such as `CARGO_NET_OFFLINE = "true"`.
4. `[rail.config]` is what the init task would write into the project's `.rail/config.toml`: its tables go on top of
   the config `rail init` wrote, table by table, so the seed's guides, rules and models stay unless it sets its own.
   Its `[rail.config.commands]` needs `setup` and `verify`.

The loader refuses a key it does not know, and says which.

## Add a situation

Add a `[[situation]]` table to the project file:

| Key | Holds |
|---|---|
| `id` | Stable, such as `ripgrep-07`. |
| `request` | The issue's title on the first line, then its first message, as first posted. |
| `start` | The commit before the fix. |
| `hidden_tests` | The test files the fix added or changed. They are kept outside the sealed copy. |
| `fix` | The fix's commit. Only the oracle grade uses it. |
| `closed` | The date the issue was closed, YYYY-MM-DD. |
| `kind` | crash, race, wrong-result, missing-behaviour or vague-request. |
| `extra` | Empty for now: hidden security tests and planted faults come later. |
| `half` | `work` or `held`. |
| `issue`, `pull` | The issue's URL and the fix's pull request number, for the taint search. |

Then admit it: `bench/bench admit bench/sets/SET/PROJECT.toml --id ID`. It builds the sealed copy and prints why a
situation fails: the hidden tests pass on the start commit (null), they fail with the fix or fail some of ten runs
(oracle), a package the fix touches fails, Rail's `setup` or `verify` fails on the start commit, or the request
links the fix.

## The sealed copy

A sealed copy is a new repository with one commit, the tree at `start`. It has no remote and no other ref, so the
fix is nowhere in it. The hidden tests and the fix sit beside it in the store, never inside. It is built once per
situation, under `store/sealed/SET/PROJECT/ID/`.

## The grade

`bench/bench grade PROJECT.toml --id ID --diff CHANGE.patch` grades a change, a git patch from the start commit. It
applies the change to a new copy, sets aside the change's test files that clash with the hidden ones (the same path;
with `clash = "dir"`, as for Go, any test file in a hidden test's folder), puts the hidden tests in place, and runs
three rounds. A round passes when the hidden tests pass and every package the change touches passes. Tests already
red on the start commit are left out. The change is right only when all three rounds pass.

## Add an arm

An arm is `bench/arms/NAME.toml`. It says, per role, the command, the model and the effort:

```toml
description = "What the arm is"

[worker]      # the agent that writes the change; Rail runs it through rail work
command = "claude -p --output-format stream-json --verbose ... --tools {tools} --max-budget-usd {budget}"
model = "claude-sonnet-5-5"
effort = "medium"

[contract]    # Rail's contract writer and the sweep's ticket filer: a model and effort; through the worker's command
[review]      # Rail's reviewer: command and model
[consult]     # Rail's consult: command and model

[files]       # files put in place of the copy's, such as ".claude/skills/x/SKILL.md" = "x.md"
```

A role left out keeps what Rail's seed config says. The bench fills `{model}`, `{effort}`, `{budget}` (the same
budget flag for every arm), `{tools}` (the fixed tool list, no web tools), `{bench}` and, in `env`, `{run}`.

A plain arm has `plain = true` and only a worker command. It gets the request, one fixed sentence and the
project's commands, once.

No arm resumes a worker session: a command with `--resume`, `--continue` or `RAIL_SESSION` is refused, so a run
restarted from a saved stage starts every worker fresh.

Before an arm joins a run, check it: `bench/bench check-arm NAME`. It runs one trivial situation end to end.

The arms here: `rail` (Rail as the pinned commit has it), `plain-sonnet`, `plain-opus`, `plain-haiku`, and the fake
arms `fake` and `fake-plain` the suite uses.

## Run

`bench/bench run PROJECT.toml --id ID --arm ARM [--runs N]` runs an arm on a situation N times. Each run has its own
folder, `store/runs/PROJECT.ID.ARM.N/`, with its own HOME and TMPDIR. A child gets only the variables `pass_env`
names, so no forge token reaches it. The driver ends a run after `run_minutes`.

A Rail run installs Rail with no agent, files the request as `rail intake` does, and follows `rail next --json` as
a script. A PERSON ticket's wait for a person is answered with `rail accept` and counted. `STUCK` (an AUTO ticket at
the retry cap) ends the run before Rail drops the ticket, so the change at the stop is still there to grade. Any
other wait ends the run, and its code says how.

A plain run counts as merged when the agent exits 0 with a success result whose last line is DONE.

When a run ends, the bench searches its streams for a leak (the issue's URL, the fix's pull request or commit, a
`gh` command, a fetch of the project) and grades it. A run that ended on a rate-limit or overload error is "to run
again": it is not graded, and the next `bench run` sets it aside and runs it afresh.

## Saved stages and restart

A Rail run saves a stage after intake, after the contract is accepted, after each worker run, after each review
round, and at the end. A stage holds the whole copy: every ref, the worktrees and `.git/rail/`. Build folders are
left out and come back from the sealed copy. A stage is packed in pieces under `piece_mb`.

A killed driver loses nothing: run the same `bench run` again and it goes on from the last stage. It never grades a
half run.

`bench/bench run --from RUN --stage NAME --arm ARM` starts a new run from the state saved before stage NAME of RUN,
and goes on with ARM's roles. So two arms can be compared from the same contract.

## Cost and the network

Each role (worker, contract, review, consult) has its own cost proxy. The proxy logs only the path, the status
and the tokens of each call. It never logs a header or a body. It refuses Claude Code's
`/v1/code/agent-proxy/ws` tunnel. A consult the worker asks for is counted as the worker's. A `rail work` run
whose brief Rail gives `[worker] contract`'s model (the contract, and the sweep's tickets) is the contract role's.

On Linux as root, each child runs in a network of its own that reaches only the proxies. Elsewhere the run goes on
unlocked, and its result says so. `network_lock = "required"` refuses to run unlocked.

## Report

`bench/bench report [--arms A,B] [--seed N]` prints, per arm, the numbers of PLAN section 5 on the situations every
compared arm has a scored run on. Ranges come from resampling whole situations within each project, with the stated
seed. Every rate has its counts beside it. Tainted runs and runs to run again are left out and counted. Unlocked
runs are shown apart. Fill `[cutoffs]` in `bench/config.toml` so a situation closed before a model's training cutoff
is left out.

## Not built yet

- Planted faults and invited vulnerabilities: a situation's `extra` key, refused until they are built (`bench/sets.py`).
- The chain run and other vendors' arms: a new driver beside `drive_rail` and `drive_plain` in `bench/driver.py`.
- Mining issues into situations: a tool that writes `[[situation]]` tables for `bench admit` to check.
