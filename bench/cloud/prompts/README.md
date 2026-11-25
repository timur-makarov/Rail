# Cloud sessions for set 2026-12: admission, hardness, pilot

Prompts for Claude Code cloud sessions (default cloud environment, started on the Rail repository). Each prompt is
standalone: paste it whole into a new session, after filling the parameter block at its top.

| Prompt | What it does | Model runs |
|---|---|---|
| `ADMIT-python.md`, `ADMIT-typescript.md`, `ADMIT-rust.md`, `ADMIT-go.md` | Installs the toolchain; makes each project's settings work on the machine (fixing and recording commands on the branch `bench-sets-<language>`); `bench admit` plus two offline checks on every candidate; reserves when a project ends under 20 admitted; ends with a table per project and the admitted ids. | none |
| `HARDNESS.md` (LANGUAGE at the top) | Pins Claude Code, finds the sign-in variables, checks the lock; three plain Haiku 5.5 runs on every admitted situation, locked, cost through the proxy; drops the easy ones (3 of 3 solved); draws fifteen per project (twelve work, three held) and pushes `CHOSEN.toml`. | Haiku 5.5 |
| `PILOT.md` (LANGUAGE at the top) | PLAN T9 cut to two arms: one situation per project, `rail-ladder` and `plain-opus`, three runs each; a run killed and resumed; every saved stage restored and compared; a restart from a stage; the lock as root; proxy against CLI tokens; `bench report`; the ten odd runs. The planted fault, the invited vulnerability and the chain are not built and are left out. | Sonnet, Opus, Fable (Rail arm); Opus (plain) |

They drive scripts in the Rail repository's `bench/cloud/` (branch `bench-sets`, draft pull request against
`integration`), described in `bench/cloud/README.md` there. The project files are `bench/sets/2026-12/*.toml`, with
notes per project in `bench/sets/2026-12/notes/`.

## Order

1. **Admission**, one session per language (four sessions; they may run at the same time). No model runs.
2. **Hardness**, per language, after that language's admission. It ends by **choosing fifteen per project**.
3. **Pilot**, per language, after that language's hardness.

The brief said "admit, then choose 15 per project, then hardness, then pilot". The owner's rule (2026-11-25) is that
the fifteen are chosen after admission *and* the hardness filter, and the filter can only drop situations, so the
choice comes at the end of the hardness step (`choose.py`), not before it. Hardness therefore runs on every admitted
situation of the projects in play, not on fifteen.

The same session can run all three prompts in turn (paste the next one when the last final message is in), or each
prompt can start a new session: every prompt rebuilds what it needs from the branches (`bench-sets-<language>` on
Rail, the results branch) and `/srv/rail-bench` if it is still there.

## What a person does

Before the first session:
- Check that the private repository `timur-makarov/rail-bench-results` exists (it may be empty). The sessions push to
  branch `<language>` there. If a session cannot push to it, it falls back to the branch
  `bench-results-<language>` on the Rail repository and says so at the top of its final message; later sessions find
  that fallback by themselves.
- Pick one Claude Code version for every child of the hardness, the pilot and later the main run (`CC_VERSION`),
  for example the `stable` tag of `npm view @anthropic-ai/claude-code dist-tags` on the day, and use it in every
  HARDNESS and PILOT prompt. Empty means: the hardness session takes the `stable` tag of its day and writes it to
  `session/claude-version` on its results branch; the pilot reads it from there.

Between the steps:
- After each ADMIT: read the table. A project with fewer than 20 admitted brings in a reserve inside the same session
  (python: sqlfluff, marimo; typescript: vitest, svelte; rust: ruff, rolldown; go: rclone, tailscale). If the
  final message says the owner must decide (no project of a pair reached 20), decide before HARDNESS: keep the
  project with fewer, or replace it with a reserve the session did not try (start `ADMIT-<language>.md` with
  `PROJECTS = <reserve>`).
- Look at the settings changes the session pushed (`git log origin/integration..origin/bench-sets-<language>` in
  Rail): they are what every later run of that project uses.
- After each HARDNESS: read the chosen ids and the cost. A project with fewer than fifteen left after the filter needs
  a reserve's admission first (`ADMIT-<language>.md` with `PROJECTS = <reserve>`), then `HARDNESS.md` with the same
  `PROJECTS`.
- After each PILOT: read the ten odd runs and the check table; correct the plan (PLAN section 9, step 5).
- At the end: merge the four `bench-sets-<language>` branches into `bench-sets`. They touch different project files
  and notes, except `bench/sets/2026-12/CHOSEN.toml`, which each branch adds with only its own projects: git reports
  an add/add conflict there, settled by hand by keeping every branch's tables.

If a session ends its turn while work is left (it should not), or its machine was reclaimed, send it: "Go on: read
your progress file (/srv/rail-bench/session/PROGRESS-ADMIT.md, -HARDNESS.md or -PILOT.md, the one of the prompt you
are running) and continue at the first step not done. If /srv/rail-bench is gone, start at step 1; the results branch
has what was kept." Admission records kept on the results branch can be copied back into
`/srv/rail-bench/admission/<project>/` so finished situations are not admitted again; `restore_store.py` rebuilds
their sealed copies.

To split a long language over two sessions (Rust is the likely one), start each with `PROJECTS` naming one project
and its own `RESULTS_BRANCH` (for example `rust-turso` and `rust-nushell`); the settings branch follows
(`bench-sets-rust-turso`). Each then has its own `IN-PLAY.txt`, `CHOSEN.toml` and pilot, and each writes
`notes/toolchain-rust.sh`: keep one of the two when merging.

## Rough sizes (estimates; nothing has run)

- Admission: every situation is built once (setup, with the network), then tested in five fresh copies (null, the
  oracle's ten runs of the hidden tests and the touched packages, Rail's setup and verify, the offline hidden tests,
  Rail in a worktree offline). Tens of minutes per situation for Python, TypeScript and Go; Rust builds `target/`
  five times per situation and may take an hour each. A project's admission is likely 10-30 hours, Rust's more. A
  prompt cuts the offline checks after the first 15 situations of a project projected over 12 hours, and says so.
- Hardness: three Haiku runs per admitted situation, each graded three rounds: with 25-35 admitted per project, about
  150-200 runs per language, two at a time. Days, not hours, for Rust. An owner choice that would halve it, not
  taken: stop a situation's runs after its first failure (it can no longer be easy).
- Pilot: twelve runs per language (Rail runs up to two hours each), two `check-arm` runs, one restart, the checks.
- Disk: 30 GB per machine. ha-core, typescript-go (inodes), the TypeScript copies and every Rust `target/` are the
  risks; the prompts prune finished runs' copies, park admitted sealed copies and rebuild them later.
- Usage: every child counts against the account's seven-day limit, shared by every session running at once. The
  sessions stop at 90% (`usage_check.py`).

## Known faults the prompts work around (reported with the pull request)

- The bench keeps every run's working copy after its grade; `prune_runs.py` deletes graded runs' copies after every
  job. Saved stages are whole copies; the pilot keeps only `stages.jsonl` in the results (`keep.py --no-stages`).
- The bench runs the projects' setups, tests and grades with the caller's whole environment (`sealed.project_env`
  starts from `os.environ`), so with the session's GitHub, cloud and messaging tokens; `jobs.py` (and `jobs.py exec`
  for foreground commands) drops them.
- The mirrors fetch every ref (`+refs/*:refs/*`), GitHub's pull-request refs included, on every build: larger mirrors
  and slower builds than needed.
- `grade.red_at_start` caches start-commit package runs in the sealed folder; a change to `test_package`, `failed` or
  `package_of` needs those `red/` folders deleted (the admission prompts say so).
- `bench admit` checks Rail's setup and verify in the copy's root with the network on; `admit_one.py` adds the check
  in a `.claude/worktrees/` worktree with the network cut, and the hidden tests offline, and writes the overall
  verdict into `admission.toml`.
- The bench does not hide its own folders (sealed copies with hidden tests and fixes) from a child; the taint search
  only detects a leak afterwards. The lock check records it.
- `[commands] env` values are taken literally, so paths name the store `/srv/rail-bench` (`BENCH_STORE` must be that).
- An arm names one worker rung only; the two-rung ladder of the Rail arm is in each project file.
- A setup change needs the project's sealed folders deleted by hand (`sealed.build` keeps an existing copy).
- The report reads admission from the sealed folders, so they must be there (restored) when it runs.

## Unknown until the sessions run

1. Whether a cloud session can push to `timur-makarov/rail-bench-results` (the probe decides; else the fallback).
2. Every command of the sixteen project files: written from CI files and docs, never run.
3. Which variables let a scrubbed child with a fresh HOME sign in (`signin_probe.py` finds them).
4. Whether a child's Bash tool reads `BASH_ENV` (Go projects; the literal `GOMODCACHE` and `GOCACHE` cover all but
   tailscale's link to its Go fork, which only `go-env.sh` makes); the lock check shows it.
5. Time and disk per situation, and whether the inode count of the disk carries typescript-go and ha-core.
6. Whether four sessions may run at once, and how fast they use the shared seven-day limit.
7. How often a paused machine is reclaimed (files lost); the prompts keep results every two hours.
8. Whether the stream-json output carries `claude_code_version` (the pilot looks).
9. Whether a rate-limit or overload error really ends a run as "to run again" (only if one happens).
10. Whether `rustup` is on the machine's PATH (the Rust admission installs it if not).
11. PLAN T8 (`rail work` in a cloud session on three real tickets) comes before T9; these prompts do not run it.
