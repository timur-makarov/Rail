# The worker as a run the engine starts: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and are
no longer described here: `rail work NN` with `RAIL_WORKER`, the refusals inside a run, the saves during a run,
the session reuse and the `worked` event with its run log and counts (`rail docs loop`, `rail docs journal`);
the `[worker] command`, `timeout_minutes`, `ticket_usd` and `daily_usd` keys with the `BUDGET` wait and the
`BUDGET_DAY` rest, and the cost in a dropped ticket's drop mark (`rail docs retries`, `rail docs journal`); the
patterns in the worker runs that the sweep turns into tickets (`rail docs sweep`); and the worker lines in
`rail stats` (`rail docs stats`). Nothing below is implemented, and nothing below was run with a model.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

**The runner still makes choices the engine should make.** `rail work` starts the worker, but the runner
prompt (`rail docs cloud`, "Run with no session open", and `README.md`) still tells the runner to read
`action.model`, decide whether to reuse a subagent, start it, and tell it not to run `rail advance`
(confirmed). Each of these is a line of prompt the runner may follow or not, and the cost of a worker started
that way is not recorded. `seed/AGENTS.md` says the same to a session nobody drives.

**The engine's defaults were not tried on real tickets.** The turn, dollar and minute limits in the seed are
a first guess (confirmed in `seed/config.toml`), and the Claude Code flags behind them were read on the
docs, not run through a runner.

## What changes

### What the runner does

The runner prompt (`engine/docs/cloud.md`, `README.md`) changes at step 2: "If `action.kind` is `agent_task`
for a ticket, run `rail work NN --json` with a timeout of 120 minutes. When it ran a worker, run `rail advance
NN --json`. If it ran nothing, do the brief it returned with a subagent, then run `rail advance NN --json`."
The runner no longer picks models or reuses subagents for a ticket's work. A session a person drives is
unchanged: it does the brief itself, and its cost is not recorded (`rail stats` says the worker cost covers
`rail work` runs only).

A source's brief (`rail source NAME`) is not a ticket's and stays as it is.

### The runner's Bash calls

The repository's settings give the Bash tool a 30-minute default and a 2-hour ceiling (`seed/settings.json`
`BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`, confirmed), and `rail doctor` warns when
`[worker] timeout_minutes` is not under the ceiling (confirmed). What is left: a worker run of 90 minutes needs
the runner to pass a timeout above it, which the runner prompt above says. A session whose repository settings
don't load (several repositories, a project thread, `rail docs cloud` "Session shapes") has the Bash tool's
own defaults, so `rail provision` would write the two variables into the machine's settings with the hooks
(inferred: it writes the hooks there today; it writes no Bash variable now, confirmed).

### Docs and files that change

- `engine/docs/cloud.md` and `README.md`: the runner prompt, and the paragraph after it ("One worker carries a
  ticket ..."), which describes subagents.
- `seed/AGENTS.md`: its lines on starting a subagent and running `rail advance` for the brief.
- `seed/config.toml` and `engine/rail/config.py`: the `[worker]` command and limit values, once the pilot
  below has set them.
- `engine/rail/cli.py` (`rail provision`): the two Bash variables.
- The skills that say "run `rail advance`" (`rail-build`, `rail-findings`, `rail-conflict`) stay as they are:
  a session a person drives still runs it, and inside a worker run the added brief line and the refusal say
  otherwise.

### What `rail stats` adds

Built: the worker cost per merged ticket, the outcomes by the model and effort of the last worker run, the
runs by how they ended, the resumed runs against the fresh ones, and the cost of the merged tickets a person
acted on. Left: the cost of dropped tickets, shown as its own line (the drop mark keeps the sum, confirmed
in `tests/test_work.py`; whether `rail stats` reads it was not found), and the worker cost per merged ticket
by tier (the outcomes are by tier, the cost is not). Then the model arms of `proposals/entropy.md` (test 3)
measure the worker's cost.

## Tests, each before its part is kept

1. **Pilot, with a model.** Three real tickets in a cloud session through the runner with `rail work`: one
   that merges, one that fails a check once, one with a review finding. Recorded: a `worked` event per run
   with a cost; the guard hook ran inside the worker (a canary: the ticket asks the worker to run a command
   the guard denies, and the denial is in its transcript); the claim stayed with the runner through a run
   longer than 30 minutes (the third ticket's worker is asked to wait); a resumed session kept its context
   (the second run doesn't re-read files the first read). Kept when all of these hold on all three tickets.
   This uses models and a cloud session, so it waits for the owner to restart the paused model tests.
2. **Runner prompt, deterministic part.** A fixture that checks the prompt in `engine/docs/cloud.md` and
   `README.md` names `rail work NN --json` and the 120-minute timeout, and that `rail provision` writes the two
   Bash variables into the machine's settings. The wording itself is untested until the pilot.

Not covered: the cost of a session a person drives, and of consult; another vendor's CLI (the command is open
to it, and no one has run one); whether the default values suit real tickets. The pilot's numbers set them.

## Assumed, not verified

- That a child `claude -p` in a worktree applies the worktree's `.claude/settings.json` allow rules. The docs
  say project allow rules apply only once the folder is trusted, and that `-p` shows no trust dialog; how the
  two meet was not found (reported). The pilot shows it.
- That `RAIL_WORKER`, set by `rail work`, reaches the child's Bash tool and its hooks (inferred: a child
  process inherits its parent's environment, and Claude Code passes its own to the commands it runs).
- That auto mode is available for `-p` on the account the runner uses (the docs list the eligible models and
  plans; reported).
- That the child's own Bash calls run in the sandbox when `rail work` itself is excluded from it, on a
  person's machine (inferred: the child applies its own settings).
- That a resume on a new machine fails the way the engine expects (the engine then runs once more fresh;
  `rail docs loop`): the fake worker in the tests stands in for the CLI.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. `rail provision` writes the two Bash variables; the dropped-ticket and by-tier lines in `rail stats`.
2. The pilot, then the runner prompt in `engine/docs/cloud.md` and `README.md`, `seed/AGENTS.md`, and the
   seed's command values.

## Decisions

**Made by the owner (2026-11-25):** the engine starts the worker as a `claude -p` run, as it does the reviewer.

**Open:**

1. The default values: 300 turns, $15 and 90 minutes per run, $40 per ticket, no daily limit. They are in the
   seed now; the pilot decides whether they stay.
2. Whether `daily_usd` is on by default for an unattended runner.
3. Whether `rail next` should answer with `script: rail work NN` itself, so the runner needs one rule fewer.
   Proposed: no, while a session a person drives still does the brief itself and needs `agent_task`.

## Sources

- Claude Code docs, read 2026-11-25: print mode, `--max-turns`, `--max-budget-usd`, `--effort`, `--model`,
  `--permission-mode auto`, `--permission-prompts none`, `--resume`, `--output-format stream-json`, project
  settings and trust (reported).
- Rail's engine and docs: `engine/rail/work.py`, `engine/rail/cli.py`, `engine/rail/state.py`,
  `engine/rail/doctor.py`, `engine/docs/loop.md`, `engine/docs/cloud.md`, `engine/docs/journal.md`,
  `engine/docs/retries.md` (confirmed).
