# The worker as a run the engine starts: what could be built

This page is a proposal. None of it is implemented. It says how the engine could start the worker the way it
starts the reviewer, so that every attempt has a recorded cost and a hard limit. Status: written 2026-11-25
from Rail's engine code and docs and the Claude Code docs; the owner chose this direction on 2026-11-25.
Nothing here was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

**The worker's cost is not recorded.** Only review runs carry `cost_usd`: the engine starts the reviewer with
`[review] command` and reads `total_cost_usd` from its JSON (`engine/rail/review.py:293`,
`engine/rail/steps.py:52-67`, confirmed). The worker is a subagent the runner starts, and the Agent tool
returns no token count, cost or duration to the runner (reported). So `rail stats` can't say what a ticket
cost, which ladder rung is cheaper per merged ticket, or what a test arm spent.

**One attempt has no limit.** The retry budget and cap count ships. A worker that never returns can work for
hours. The save hook writes a `saved` event at least every `[claim] save_minutes` (10), and `quiet_minutes`
counts it as a sign of life, so the claim never goes stale and no other session takes the ticket over
(`engine/rail/state.py:209-215`, confirmed). Nothing bounds a ticket's total spend either: each step has its
own cap of 5, and a ticket that fails at several steps in turn can run dozens of attempts, many on Opus
(`state.py:100-175`, confirmed; the count is inferred).

**The runner makes choices the engine should make.** Today the runner reads `action.model`, decides whether
to reuse a subagent, starts it, and tells it not to run `rail advance` (`engine/docs/cloud.md`, runner
prompt, confirmed). Each of these is a line of prompt the runner may follow or not.

## What changes

A new verb, `rail work NN`, runs one attempt at a ticket's agent work. The runner then runs `rail advance NN`,
as it does today after a subagent returns.

1. **It builds the brief `rail next` would give for ticket NN**, and runs only when that brief is an
   `agent_task` whose last step is `rail advance NN`: `TICKET_LINT`, `VERIFY_ASSUMPTIONS`, `IMPLEMENT`,
   `STEP_FAILED`, `ANSWER_FINDINGS`, `CONFLICT`, `REBASING` and `SPLIT`. For any other answer, such as
   `SETUP_FAILED` (whose brief says to run `rail next` again, `engine/rail/table.py:279-282`, confirmed), it
   runs nothing and returns the answer, and the runner does that brief as it does today.
2. **It runs `[worker] command` in the answer's `cwd`**: the ticket's worktree, or the project's root for a
   contract on a ticket not yet claimed. The brief goes on stdin with one line added: "When you are done, or
   can't go on, reply in one line. Don't run `rail advance`: the runner runs it after you exit." The command
   gets `RAIL_TICKET`, `RAIL_MODEL` and `RAIL_EFFORT` (the rung the answer names, `engine/docs/loop.md`),
   `RAIL_SESSION` (below), `ANTHROPIC_MODEL` as for the reviewer (`engine/docs/review.md`, confirmed), and
   `RAIL_WORKER=1`.
3. **Inside a worker run, the engine's moves refuse.** With `RAIL_WORKER` set, `rail advance`, `rail next`,
   `rail work` and `rail save` refuse with one sentence, so the worker can't ship, claim another ticket, take
   its own ticket over, or start a worker. The child is a different Claude Code session from the runner,
   and the claim belongs to the runner's session (`engine/rail/project.py:95`, confirmed), so without this
   its `rail next` would take the ticket over from its own runner (`engine/rail/cli.py:97-99, 323-329`,
   confirmed).
4. **It keeps the claim alive itself.** While the run lasts, `rail work` saves the worktree's in-scope changes
   and pushes them every `[claim] save_minutes`, as the save hook does today. It runs in the runner's Bash
   call, so the saves are the runner's session's. The child's own save hooks do nothing (step 3). A save
   during a rebase is skipped, as today (`cli.py:1458-1462`, confirmed).
5. **It records the run.** It reads the command's output as JSON lines when it is that: the last `result`
   line gives `total_cost_usd`, `session_id`, `num_turns` and `subtype`, and the lines before it give the run
   log (below). It writes a `worked` event: model, effort, cost, turns, minutes, session id, the run-log
   counts, and how the run ended (`done`, `turns`, `budget`, `timeout`, `error`). When the worktree is in a rebase, the
   event waits in the local cache until the rebase ends, because nothing may be written to the ticket then
   (`engine/docs/loop.md`, "While that rebase is open", confirmed).
6. **It returns** the `worked` event and the answer `rail advance NN` should now get. It doesn't run the
   ship: a worker run and a ship each fit one Bash call of the runner (see Limits).

The command stays agent-neutral, as `[review] command` is: every Claude flag lives in the command string, and
the engine only reads JSON keys when they are there (owner, 2026-11-24). A command whose output has no cost
gets a `worked` event with no cost.

```toml
[worker]
command = '''claude -p --output-format stream-json --verbose --model "$RAIL_MODEL" --effort "$RAIL_EFFORT" --permission-mode auto --permission-prompts none --max-turns 300 --max-budget-usd 15 ${RAIL_SESSION:+--resume "$RAIL_SESSION"}'''
timeout_minutes = 90        # one worker run, wall clock; keep it under the Bash tool's BASH_MAX_TIMEOUT_MS
ticket_usd = 40             # recorded runs of one ticket (worker and review) since a person last acted; 0: off
daily_usd = 0               # recorded runs of every ticket in the last 24 hours; 0: off
```

The flags were read on the Claude Code docs on 2026-11-25 (reported): `--max-turns` and `--max-budget-usd`
work in print mode and end the run with the result subtypes `error_max_turns` and `error_max_budget_usd`;
`total_cost_usd` is in the JSON on those results too; the response that crosses the budget still completes,
so a run can spend somewhat more than the cap; `--effort` takes `low` to `max`; `--model` overrides
`ANTHROPIC_MODEL`; `--permission-mode auto` works with `-p`, and `--permission-prompts none` turns a call
nobody can approve into a denial the model reads, with no exit; a `-p` run loads the project's
`.claude/settings.json` hooks unless `--bare` is given. The worker command uses neither `--bare` nor
`--safe-mode`, so the guard hook runs (inferred from the docs and the owner's 2026-11-24 test of
`--safe-mode`).

### One worker per ticket

The runner today reuses the subagent already working a ticket while `action.model` stays the same, so the
repository is read once per ticket (`cloud.md`, confirmed). `rail work` keeps that with sessions: the `worked`
event stores the session id; the next `rail work` on the ticket passes it as `RAIL_SESSION` when the model
and effort are the same and the last run ended `done`. Claude Code continues a session with `--resume <id>`,
and the id stays the same without `--fork-session` (reported). A session lives on the machine that ran it, so
on a new machine the resume fails; the engine then runs the command once more with `RAIL_SESSION` empty
(inferred). A run that ended by turns, budget or timeout is not resumed: its context is the one that ran away.

### Limits

| Limit | Where | What happens |
|---|---|---|
| Turns per run | `--max-turns` in the command | The run ends; `rail work` records `turns`. The runner runs `rail advance`, which ships what is there and counts as usual |
| Spend per run | `--max-budget-usd` in the command | The same, recorded as `budget` |
| Wall clock per run | `[worker] timeout_minutes` | The engine ends the process and records `timeout` with no cost. The same as above |
| Spend per ticket | `[worker] ticket_usd` | When the ticket's recorded cost since a person last acted passes it, the ticket waits for a person (`BUDGET`), with the cost by role and model. The row sits above every other agent row, in every state, `new` included; `rail accept NN` and `rail:go` continue it with a fresh count, as they give a fresh retry cap |
| Spend per day | `[worker] daily_usd` | `rail next` rests (`BUDGET_DAY`) and `rail work` refuses until the last 24 hours fall under it; no ticket changes state |

A `BUDGET` wait is a stop, like the retry cap: the ticket is spending past what any ticket should, and a
person decides whether it goes on. The per-run limits stay in the command, where any CLI can set its own; the
engine owns only the wall clock and the sums it computes from the journals. A recorded cost is the CLI's
client-side estimate, not the bill (reported). The sums leave out consult, which records no cost today, and a
session a person drives.

**The runner's Bash calls.** The repository's settings give the Bash tool a 30-minute default and a 2-hour
ceiling (`seed/settings.json` `BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`, confirmed). A worker run of 90
minutes needs the runner to pass a timeout above it, which the runner prompt says; `rail doctor` warns when
`timeout_minutes` is not under the ceiling. A ship stays a separate call, as today. A session whose repository
settings don't load (several repositories, a project thread, `engine/docs/cloud.md` "Session shapes") has the
Bash tool's own defaults; `rail provision` would write the two variables into the machine's settings with the
hooks (inferred: it writes the hooks there today).

### What the runner does

The runner prompt (`cloud.md`, `README.md`) changes at step 2: "If `action.kind` is `agent_task` for a
ticket, run `rail work NN --json` with a timeout of 120 minutes. When it ran a worker, run `rail advance NN
--json`. If it ran nothing, do the brief it returned with a subagent, then run `rail advance NN --json`." The
runner no longer picks models or reuses subagents for a ticket's work. A session a person drives is
unchanged: it does the brief itself, and its cost is not recorded (`rail stats` says the worker cost covers
`rail work` runs only).

A source's brief (`rail source NAME`) is not a ticket's and stays as it is.

### What the runs teach

Boundary and Warp grade a sample of past agent runs for dead ends and for "relearning": a worker that tries
six commands to find how the tests run, when a skill or `AGENTS.md` should have told it (reported, Boundary
talk, 31:15-32:22). Rail could do the same from each run's own record, with no model.

- **The run log.** From the stream's tool-call lines `rail work` keeps one line per tool call: the tool,
  the command or path, and whether it failed or was denied. Each run appends to the ticket's log, cut at 200
  characters a line and 500 lines a run. The log stays in the local cache (`.git/rail/cache/work/NN`, where
  the engine keeps its other notes, `engine/rail/project.py:233-235`, confirmed) and is never committed:
  command lines can carry tokens, and a committed one would be pushed and merged, in a folder only the engine
  may write (`.rail/journal/**`, `engine/docs/guards.md:91-92`, confirmed), so no one could take it out. The
  stream's format is documented, and the session transcript's is not (reported: the Claude Code docs say the
  transcript format is internal and changes between versions).
- **What is counted per run,** into the `worked` event, which is committed: Bash commands that failed before
  the first one of the same program passed; commands the shell couldn't find (exit 127); tool calls denied by
  a rule or the guard; files read more than twice. Each counted item keeps a short key (the program, the
  denied tool and rule, the path), so the sweep can match items across tickets without the log. The program
  is the first word after dropping leading `NAME=value` words, a leading `cd DIR &&`, and the runners
  `uv run`, `npx`, `pnpm exec`, `poetry run` and `bundle exec`; `uv run pytest -x` is `pytest`. In a rebase the
  event waits in the cache like the rest (above), and the log is already there.
- **What the sweep does with it.** It reads the `worked` events of the tickets merged since the last sweep,
  from the base, as it reads their other events (`engine/rail/sweep.py:96-99`, confirmed). A key that recurs
  in three or more tickets goes into the sweep's summary as a pattern, and a pattern counts as something found,
  so the sweep's ticket gets a task even when nothing merged unreviewed (today it merges with no task,
  `engine/docs/sweep.md:36-38`, confirmed). The agent files one ticket per pattern, as it does for a finding:
  a `setup` or `provision` line, a line in the project's part of `AGENTS.md`, or a guide's text. A ticket that
  changes `.claude/**` or `.rail/config.toml` is PERSON, as today. This is a row of the entropy proposal's
  Part 6 (nothing learned is lost).

`rail replay` (`proposals/replay.md`) keeps a replayed worker's whole stream for its own search, and doesn't
use this log.

### What `rail stats` adds

Worker cost per merged ticket, by tier; cost by model and rung; cost of tickets that waited for a person and
of dropped ones (the drop mark keeps the ticket's cost sum, since a dropped ticket's journal goes with its
branch, `engine/docs/journal.md`, confirmed); runs ended by turns, budget or timeout; resumed against new
sessions. The entropy proposal's model arms (`proposals/entropy.md`, test 3) then measure the worker's cost.

## Docs and files that change

- `engine/docs/loop.md` ("The engine starts no agent") and `engine/docs/github-runner.md` ("Rail starts no
  agents"): the engine starts the worker as it starts the reviewer and consult.
- `engine/docs/cloud.md` and `README.md`: the runner prompt. `seed/AGENTS.md`: its lines on starting a
  subagent and running `rail advance`.
- `engine/docs/retries.md` and `engine/docs/states.md`: the `BUDGET` wait. `engine/docs/journal.md`: the
  `worked` event with its counts and keys, and the cost in the drop mark. `engine/docs/stats.md`: the new
  lines.
- `engine/rail/config.py` defaults, `engine/rail/docs.py` (`rail docs config`), `seed/config.toml`: the
  `[worker]` keys; the `[claim] stale_minutes` comment, which today says to keep it above the longest command.
- `engine/docs/guards.md` and `seed/settings.json`: `rail work` in the allow rules and in `excludedCommands`
  (inferred: it writes the journal, as `rail advance` does).
- `engine/rail/cli.py`: the `worker()` docstring. `engine/docs/sweep.md`: patterns in the summary and
  in "something found". `engine/rail/sweep.py`: reading the `worked` counts.
- The skills that say "run `rail advance`" (`rail-build`, `rail-findings`, `rail-conflict`) stay as they are:
  a session a person drives still runs it, and inside a worker run the added brief line and the refusal say
  otherwise.

## Tests, each before its part is kept

1. **Gate cases, no model.** A fake worker command, like `tests/fake_reviewer.py`, that prints chosen JSON,
   sleeps and exits:
   - a `worked` event is written with cost, turns, session and end;
   - `rail work` runs only for the codes in step 1, and returns `SETUP_FAILED` untouched;
   - inside a run, `rail advance`, `rail next`, `rail work` and `rail save` refuse;
   - a run longer than `stale_minutes` keeps its claim, and another session's `rail next` leaves the ticket
     alone;
   - a run over `timeout_minutes` is ended and recorded;
   - the second run on the same rung gets `RAIL_SESSION`, a run after a `budget` end doesn't, and a failed
     resume runs once more fresh;
   - a run that ends inside a rebase writes its event once the rebase ends;
   - `ticket_usd` makes a `BUDGET` wait on an implementing ticket and on a `new` one, and `rail accept`
     clears both;
   - `daily_usd` makes `next` rest and `work` refuse;
   - a command with no JSON gives a `worked` event with no cost;
   - a stream with tool calls gives a run log in the cache, cut at its caps per run, appended by the second
     run, and never in a commit; the counts and keys land in the `worked` event; `FOO=1 uv run pytest` and
     `cd app && pytest` both count as `pytest`;
   - a run that ends inside a rebase keeps its log and counts, and the event is written once the rebase ends;
   - a sweep over fixture journals where one command fails in three tickets, and nothing merged unreviewed,
     gets a task, and its summary names the pattern;
   - a dropped ticket's cost is in its drop mark.
   Kept when every case behaves as written.
2. **Pilot, with a model.** Three real tickets in a cloud session through the runner with `rail work`: one
   that merges, one that fails a check once, one with a review finding. Recorded: a `worked` event per run
   with a cost; the guard hook ran inside the worker (a canary: the ticket asks the worker to run a command
   the guard denies, and the denial is in its transcript); the claim stayed with the runner through a run
   longer than 30 minutes (the third ticket's worker is asked to wait); a resumed session kept its context
   (the second run doesn't re-read files the first read). Kept when all of these hold on all three tickets.
   This uses models, so it waits for the owner to restart the paused model tests.

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
- That `--output-format stream-json` in print mode needs `--verbose`, and that its tool-call lines name the
  tool, its input and whether it failed (read on the docs for the SDK's message stream, which the CLI is said
  to share; reported).
- The JSON keys and exit codes when a limit ends a run: the subtypes and `total_cost_usd` are documented for
  the SDK result message, and the CLI is said to share it (reported, not read for the CLI itself).
- That the child's own Bash calls run in the sandbox when `rail work` itself is excluded from it, on a
  person's machine (inferred: the child applies its own settings).

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. `rail work`, `RAIL_WORKER` and the refusals, the saves during a run, the `worked` event, `[worker] command`
   and `timeout_minutes`, the run log, the gate cases.
2. `ticket_usd`, `daily_usd`, the `BUDGET` and `BUDGET_DAY` answers, the cost in the drop mark, the
   `rail stats` lines.
3. The run-log counts in the sweep.
4. After the pilot: the runner prompt in `cloud.md` and `README.md`, and the seed's command values.

## Decisions

**Made by the owner (2026-11-25):** the engine starts the worker as a `claude -p` run, as it does the reviewer.

**Open:**

1. The default values: 300 turns, $15 and 90 minutes per run, $40 per ticket, no daily limit.
2. Whether `daily_usd` is on by default for an unattended runner.
3. Whether `rail next` should answer with `script: rail work NN` itself, so the runner needs one rule fewer.
   Proposed: no, while a session a person drives still does the brief itself and needs `agent_task`.
