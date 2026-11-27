# Checks, tools and text: a plan

This page is a plan for the work that follows the steps of `proposals/features.md`. It answers one question:
how does Rail come to state what a merged change is, with a fact behind each statement, and need fewer lines
of text for a model each time a better model arrives. Nothing here is built. Tool facts were read on the
tools' own pages on 2026-11-27 by research runs and are marked: *run* (run on a machine), *read* (read in the
tool's docs or source), *reported* (from a summary or a second source), *not confirmed*. Almost nothing was
run. A feature here that already has a section in `proposals/features.md` is named in bold and only changed,
not repeated.

## The aim, as numbers

"It works" is measured, and `rail stats` shows each number:

| Number | Read from | Wanted |
|---|---|---|
| Escapes: merged tickets later reverted, or named by a `caused_by` ticket, per 100 merged | the journal | falls |
| Findings in the first review round, per ticket and by kind | review events | falls; a kind that stays high gets a check |
| Ship attempts before the first review | step events | falls |
| Waits for a person, by cause | wait events | no cause grows |
| Lines of text a model reads, per brief, guide and skill | a test that counts them | falls with each model |

No published number exists for the first three on agent-written changes (reported), so Rail's own journals
are the only source.

What a merged change states today is the list of its passed steps. This plan turns that list into a table of
statements, each with the check that produces it and the gate case that plants its violation. A statement
with no check is hope, and is not on the table.

| Statement about a merged change | Today | After this plan |
|---|---|---|
| Each `Check:` line is red on the base and green on the head | built | |
| The change stays inside its `scope_paths` and its size | built | |
| No added line breaks a structure rule or a sensor | built, with no sensor on | sensors on, per language |
| A test the change edits still passes in its old form, or a run with no stake said why not | built | |
| An exemption the author wrote was judged by a run with no stake | built | |
| A fresh run reviewed it and its blocking findings are answered | built | a finding that does not reproduce does not block |
| Nothing that holds for the whole program got worse: no new dead code, cycle, unused dependency | | **Findings new compared with the base** |
| The change's own tests fail without the change | | **The change's tests run against the base's code** |
| No fewer tests ran than on the base | | **The tests that ran are counted** |
| Each changed line is run by a test, and a planted fault on it is noticed | | changed-line coverage, then **Mutation score on changed lines** |
| A new dependency exists, is older than the cooldown and has no known advisory | | **A check on each new dependency** |
| No added line holds a hidden character | | **Hidden characters** |
| What a public interface, an API description or a migration breaks is named | | **Interface and schema differences** |
| The product behaves as on the base, except where the ticket says | | **A behaviour question** |

What stays outside any table: behaviour the Done Contract never stated. Tests written before the work and the
product step narrow it, and the escapes number measures what is left.

## Four carriers, in this order

1. **The engine** states a fact it computed: a diff, a count, a comparison of base and head.
2. **A tool** states a fact the engine reads: a located finding, an exit code.
3. **A fresh run with no stake** answers one closed question about a fact (`rail docs triage`), or reviews.
4. **Text** asks a model to behave some way.

A behaviour is carried by the lowest number that can carry it. The evidence for the order (reported): a
prompt against sloppy code lowered where decay starts and did not slow it, while lowering the solve rate and
raising cost; files of instructions for agents gave no gain or a loss at 20% more cost; agents fed located
findings from static tools fixed them; and agents take the cheap way past a check when one exists, so each
check needs its own guard. Not found: a measured effect of per-turn feedback about complex functions. The
line in **Complexity and duplication sensors on by default** that cites one is unconfirmed until read in the
paper.

## Text is counted, and tested for deletion

### Every line a model reads has a reason

Size: M.

**What it does.** Each paragraph or bullet a model reads is in a ledger with the failure it prevents, the
check that states the same thing as a fact, and how it was tested. A line with no entry fails the tests, so
adding text costs an entry and a reason, and deleting text costs nothing.

**How.**

- What is counted: `engine/guides/*.md` (175 lines today), `engine/reviewer.md` (44), `seed/skills/*/SKILL.md`
  (252), `seed/AGENTS.md` (18), and the instruction lines of the briefs built in `engine/rail/table.py`,
  `engine/rail/review.py` and `engine/rail/triage.py`. A fact the engine puts into a brief (the action, a
  command, a failing check's output) is data and is not counted.
- `engine/text.toml`: one entry per paragraph or bullet, found by its file and first words. Fields: `why` (the
  situation that goes wrong without it), `check` (the check that reports the same thing, or empty), `tested`
  (a model test's result, or `not tested`).
- `tests/test_docs.py` fails for a counted line with no entry, and prints the count for each file. The count
  goes into the `CHANGELOG.md` line of any commit that changes it.
- A line leaves in one of three ways: its `check` is built and has run on real changes, and no model test
  shows the line still moves the check's number (the rule the page already has, "wording comes after the
  check"); the deletion test below removes it; or no hard situation can be written for it, which means nobody
  can show it matters.

**Kept when.** Gate cases, no model: a new bullet in a guide with no entry fails the test; an entry whose
line is gone fails the test; the printed count matches the files.

**Waits for.** Nothing.

### The deletion test

Size: M.

**What it does.** When the model in `[worker]` or `[review]` changes, the text is tested for removal before
anything is added. The test starts from everything removed and puts back only what the runs show is needed.

**How.**

- Arm A is the text as it stands. Arm B is the floor: the engine's facts and commands, and no counted line.
  Both run the held situations of every model test the lines have, by the rules of "How a model test is run".
- If B is no worse than A on the hard situations, the near misses and the plain ones, every counted line is
  deleted.
- If B is worse, the ledger's entries are split in two by `why`, half are put back, and the run repeats on
  the half that failed, as a failing batch is bisected. An entry stays only when the runs without it are
  worse.
- A single run of an agent on a task swings by two to six points (reported), so the comparison is over the
  set of situations and never over one run.

**Kept when.** With a stand-in worker that fails a situation unless one named line is present: the test keeps
that line and deletes the others.

**Waits for.** **A runner for model tests**, and situations for each `why`.

## What the engine gains

### Every independent fact in one ship

Size: M.

**What it does.** A ship that fails reports every failure it can find, not only the first. Today `CHECKS` in
`engine/rail/steps.py` stops at the first failing step, so a worker learns one kind of problem per attempt
and sensors, which run last, speak only after everything else passes.

**How.** The steps that read the diff or the text (`ticket-lint`, `assumptions`, `scope`, `rules`,
`migration`, `size`, `doc-lint`, and each sensor that needs no build) all run, and all their failures go into
one `STEP_FAILED` brief. The parts of `verify` (format, lint, types, tests, audit) each run and each report.
`checks` runs when `verify`'s tests passed. One failed ship is one attempt, whatever the number of failures.
Two ships with the same set of failures are the same failure for the retry budget.

**Kept when.** Gate cases: a change that breaks a rule, a sensor and a type check gets one brief with all
three and spends one attempt; fixing two of the three is a different failure from the first.

**Waits for.** Nothing.

### A fix step

Size: S.

**What it does.** Before `verify`, the engine runs each language's formatter and safe fixes on the files the
change touched and commits the result. A wrong indent or an unused import never costs an attempt or a model's
turn.

**How.** A manager in a profile gains `fix`, run with the changed files:

| | Command | Note |
|---|---|---|
| Python | `ruff format FILES` and `ruff check --fix FILES` | `--fix` applies safe fixes only; unsafe ones need `--unsafe-fixes` (read) |
| TypeScript | `oxlint --fix FILES`, and the project's formatter where it has one | `--fix` is safe fixes only (read). The TypeScript profile has no `format` part today |
| Go | `gofmt -w FILES` | `golangci-lint fmt` where the project configures formatters (read) |
| Rust | `cargo fmt` | `cargo clippy --fix` is left out: it builds, and its flags were not confirmed |

Only files in the change are rewritten. The commit is the engine's and comes before any check, so every
check sees the fixed text.

**Kept when.** Gate cases with stand-in commands: a change with a formatting mistake ships with no failed
step; a file outside the change is untouched; a `fix` command that fails records `could_not_run` and the
ship goes on to `verify`.

**Open decision.** The TypeScript formatter `rail init` writes: the project's own, and none otherwise
(proposed), until the formatter of the linter the owner chose reaches 1.0 (it is 0.x; reported).

### Sensors read structured output

Size: M.

**What it does.** A sensor may declare `format = "sarif"` or `format = "cargo"`, beside today's lines of
`path:line: message`. The engine then knows each finding's rule, so a `fix` line and the numbers in
`rail stats` are per rule, and a finding with several places is one finding.

**How.**

- SARIF 2.1.0 is what these tools write themselves (read, except where marked): oxlint (`-f sarif`), Biome,
  golangci-lint (`--output.sarif.path`), gosec, zizmor, osv-scanner, ast-grep, jscpd, complexipy, gitleaks;
  Ruff (reported; `--output-format concise` gives lines today).
- `cargo` reads `--message-format=json` of rustc and Clippy. No converter is installed for it.
- With a structured format the engine decides from the findings, not from the exit code: zizmor and
  govulncheck exit 0 in their machine formats, and Clippy exits 101 both for a finding and for a build that
  failed (read). Output that does not parse is `could_not_run`.

**Kept when.** Gate cases on recorded outputs of each tool named above: the same findings come out as from
the tool's line format where it has one; a truncated file is `could_not_run`.

**Waits for.** Nothing to build it; the recorded outputs need the tools on a machine.

### Findings new compared with the base

Size: L.

**What it does.** A sensor may declare `compare = "base"`. The engine runs it on the base and on the head and
fails the ship only for findings the head has and the base lacks. This is for facts about the whole program
that sit on no added line: a function nothing calls any more, an import cycle, an unused dependency, a field
used from outside its module. "Only violations on added lines" cannot see them, and it is where the tools
that judge design have to plug in.

**How.**

- The base run is made in a scratch worktree and kept by base commit, sensor and the sensor's config, so the
  tickets on one base share it.
- A finding's key: its rule, its path (followed through a rename), and a hash of the text at its place with
  whitespace dropped and the following text up to 100 characters added, plus a counter for repeats in one
  file. This is how GitHub's code scanning matches results between runs, and none of the tools above was
  found to write a fingerprint of its own (read). A finding with no meaningful line (a cycle) is keyed by its
  rule and its sorted members.
- A tool's own base mode is used where matching needs what only the tool knows: jscpd
  `--baseline-from-ref REF` for clones (read; how it matches was not confirmed).
- Findings the base has and the head lacks are recorded as fixed, for the trend.

**Kept when.** Gate cases with a stand-in tool: a finding in both runs fails nothing, also when lines above
it were added; a finding only on the head fails; a file renamed with its finding fails nothing; the base run
is made once for two tickets on one base.

**Waits for.** **Sensors read structured output**.

### The change's tests run against the base's code

Size: M.

**What it does.** The mirror of **Old tests run against the new code**, which is built. After a ship passes,
the engine puts the base's version of every changed file outside `[tests] paths` back, keeps the change's
tests, and runs the checks. A command that is still green shows that the new tests do not need the change.
That is a fact for the worker: a test that passes without the work proves nothing about it.

**How.** In `steps.py` beside `base_tests`: once per `patch_id`, recorded as a `base_code` event with `green`
or `red` per command. A command that is green both ways, in a ticket that adds or edits tests, fails the step
`tests-prove` with the command named. It does not apply where the contract keeps behaviour the same (a
refactor, a dependency update), which the ticket says. A build that fails without the change counts as red.

**Kept when.** Gate cases: a change whose new test asserts nothing about the new code fails `tests-prove`; a
change whose new test fails on the base's code passes; a refactor ticket is not asked.

**Assumed, not verified.** That a red result from a build failure is good enough evidence. It shows that the
test names the new code, and not that it checks it; changed-line mutation shows the rest.

### The tests that ran are counted

Size: M.

**What it does.** The engine reads how many tests passed, failed and were skipped on the base and on the
head. A head that runs fewer, or skips more, raises the `old-test` question for the difference. Today a
deleted test that would still pass raises nothing.

**How.** Each profile's test part writes JUnit XML, which the four runners share: `pytest --junitxml`,
Vitest's and Jest's `junit` reporter, `gotestsum --junitfile`, `cargo nextest` with `report-skipped = "all"`
(nextest and gotestsum read; the others not confirmed). The base's counts come from the `base_tests` run or
one run per base commit.

**Kept when.** Gate cases with recorded reports: a deleted passing test raises the question; a test moved to
another file raises nothing; a new skip raises it.

### Guards against the cheap way past a check

Size: S.

Each check gets the guard that stops the cheapest way of making it pass. Built: no new suppression, a
`SENSOR(NN)` marker is judged, an edited test is run in its old form. To add:

- **Removed after it was named.** When a `rules` or `sensors` failure names a file the ticket added and the
  next patch deletes that file, the reviewer's brief says so. In one study agents cleared an architecture
  finding this way in 44 of 125 runs (reported).
- **Files nothing refers to.** A seed rule of the kind `only_in` refuses an added Markdown file outside the
  project's docs paths and any added file under a dot folder Rail does not know. The reviewer's brief lists
  the added files no other file names. `rail advance` stages everything in the worktree, so a scratch file
  inside `scope_paths` is committed today.
- **Skips in every language.** The Go and Rust profiles forbid `t.Skip(` and `#[ignore]`. Python gains
  `pytest.mark.skip` and `pytest.skip(`; TypeScript gains oxlint's `no-focused-tests` and
  `no-disabled-tests` (read).

### Hidden characters

Size: S.

**What it does.** The engine refuses added lines that hold characters a reader cannot see, with no tool. A
hidden instruction in `REVIEW.md`, `AGENTS.md` or a skill reaches the next model that reads the file.

**How.** In `rules.py`, on added lines of text files. Refused: the direction controls U+202A to U+202E,
U+2066 to U+2069, U+200E, U+200F and U+061C; the zero-width characters U+200B to U+200D, U+2060 to U+2064,
U+00AD, U+180E, and U+FEFF anywhere but a file's start; the tag characters U+E0000 to U+E007F; control
characters other than tab and the line ends. It fails in code and in every file a model reads (`AGENTS.md`,
`CLAUDE.md`, `REVIEW.md`, skills, `.claude/**`, `.mcp.json`, `.rail/**`). In other text, where a translation
may hold such marks, the line goes onto the "Read these" list.

**Assumed, not verified.** The ranges are from the Unicode standard from memory, not fetched.

### `rail check`, and facts after an edit

Size: M.

**What it does.** `rail check` runs the steps that read the diff, and the sensors that need no build, on the
working tree as it stands, and prints the facts. It spends no attempt. The hook that already runs after tool
use adds the same facts for the files edited since it last ran.

**Kept when.** Gate cases for the command. From the journals: ship attempts before the first review fall
after it is on. No published result shows that feedback during the work helps, so this is the last engine
change to build and the first to remove if the number does not move.

## Tools, by job

A tool enters a profile by the bar the page already sets (**Sensor sets per language**): a gate case that
plants its violation, and the past-commit test (it fails at most 5% of commits people wrote, 8 of 10 failures
read by hand are real, it runs well inside the timeout). This plan adds the way out: `rail stats` shows per
sensor and rule its failures, the exemptions a triage run let stand, and its time. A rule with more
exemptions let stand than findings fixed over 50 tickets is switched off.

The picks. "Today" is what the profiles run now.

| Job | Python | TypeScript | Go | Rust |
|---|---|---|---|---|
| Format and lint in `verify` (today) | Ruff | oxlint | gofmt, go vet, golangci-lint | rustfmt, Clippy |
| Types (today) | basedpyright | tsc | the compiler | rustc |
| Masked errors and escape hatches, on added lines | Ruff BLE001, S110, S112, E722, PGH003, ANN401 | oxlint with `--type-aware`: no-explicit-any, ban-ts-comment, no-empty, no-floating-promises | golangci-lint: errcheck with check-blank, forcetypeassert, nolintlint, errorlint, nilerr | Clippy: unwrap_used, expect_used, let_underscore_must_use, map_err_ignore, todo, unimplemented, dbg_macro |
| Dead code, compared with the base | vulture; deptry for dependencies | knip | deadcode; `go mod tidy -diff` | rustc dead_code; cargo-shear |
| Code only tests reach, compared with the base | vulture on the source, then with the tests: the difference | knip's production mode (not confirmed) | staticcheck with `-tests=false` | a build without tests reports it as dead_code (from memory) |
| Complexity and duplication | lizard and jscpd for all four, as **Complexity and duplication sensors on by default** says | | | |
| Boundaries, on the project's own rules | import-linter | dependency-cruiser | depguard | cargo-deny bans |
| Tests that cannot fail | a rule of Rail's own (below) | oxlint `expect-expect` | a rule of Rail's own | a rule of Rail's own |
| Changed lines no test runs | diff-cover, over each runner's coverage file | | | |
| Planted faults on changed lines | mutmut 3, survivors kept to the diff's lines | StrykerJS, `--mutate FILE:FROM-TO` built from the diff | gremlins | cargo-mutants `--in-diff` |
| Dependencies with advisories | osv-scanner | osv-scanner | govulncheck (today) | cargo-deny (today) |
| Security rules, on added lines | Ruff `S` | none | gosec, inside golangci-lint | none |
| Interface differences | griffe, for a library | none | none | cargo-semver-checks, for a library crate |

For every language: gitleaks (today); zizmor and pinact on a change to a workflow; ast-grep for the rules
Rail owns; oasdiff, `buf breaking` and squawk where the repository tracks an OpenAPI file, protobuf files or
SQL migrations.

Notes that change what the page says today:

- **One external config per language.** The stricter rules run from Rail's own config on added lines, beside
  the project's own lint in `verify`: `golangci-lint run -c FILE` and `CLIPPY_CONF_DIR` with `-W` flags
  (read). No project file is edited to make a sensor stricter.
- **osv-scanner takes the place of pip-audit and of `pnpm audit` and `npm audit`.** It reads `uv.lock`,
  `pnpm-lock.yaml`, `go.mod` and `Cargo.lock`, has an offline mode after a database download, and exits 1 on
  findings and 127 on an error (read). pip-audit cannot read `uv.lock` (read), which is why the uv profile
  exports a requirements list first. govulncheck stays for Go because it reports only code that is reached;
  cargo-deny stays for its bans, licences and sources.
- **Complexity stays with lizard** for one behaviour in four languages, although each language has a rule of
  its own. Its licence reads MIT on its package page and Apache-2.0 in a source header; settle which before
  it ships in the seed.
- **jscpd is at version 5**, written in Rust, with SARIF and `--baseline-from-ref` (read).
- **gremlins.** Its README shows no diff flag (read), where the page names `--diff REF` from a search
  excerpt. Go has no confirmed way to mutate only changed lines; until one is run on a machine, changed-line
  coverage is Go's signal.
- **cargo-mutants** exits 0 when all mutants are caught, 2 for survivors, 3 for timeouts, 4 when the tests
  fail before any mutant (read). The wrapper reads these and `mutants.out/`.
- **gitleaks is in maintenance**, with security fixes only (read). Its author's successor has no stable
  release yet. Nothing changes now; look again when it has one.
- **golangci-lint is GPL-3.0** (read). Rail runs it as a program and copies nothing of it.
- **TypeScript 7.0 is released** and its `tsc` is the fast one (reported), so `tsc --noEmit` needs no change.
- **A candidate to take three TypeScript tools' place:** fallow (dead code, cycles, duplication; SARIF; exits
  0, 1 and 2; `audit --base REF` fails only on what a change introduces; read). It is younger than knip. It
  enters by the past-commit test against knip, not by default.

Tools this plan adds to `tests/tools.sh` and the profiles' `provision` lines: vulture, deptry, diff-cover,
knip, staticcheck, deadcode, gotestsum, cargo-shear, cargo-nextest, cargo-llvm-cov, osv-scanner, zizmor,
pinact, ast-grep. cargo-semver-checks, griffe, oasdiff, buf and squawk are installed only where a project has
what they read.

Left out, with the reason:

| Tool | Reason |
|---|---|
| CodeQL | Its licence bars private code without a paid plan (read) |
| Semgrep's rules | Their licence bars shipping them in a framework (read). The engine's fork has no rule set confirmed as free to ship |
| trufflehog | AGPL, and its checks need the network |
| Scanners of agent configuration that need an account token | The four checks worth having (hidden characters, permission bypass in settings, an unpinned `npx` or `uvx` server, `curl \| sh` in a hook) are rules of Rail's own |
| cargo-udeps | Needs a nightly toolchain |
| eslint-plugin-security | Its README calls its own results noisy |
| The linters aimed at agent-written code (a dozen, most weeks or months old, one a prose skill and not a checker) | None publishes how often it is wrong. Their rule ideas are taken below |
| A design-depth linter for Rust (days old) | Its findings need **Findings new compared with the base**; look again once that is built |
| A cleanup run that deletes dead code and keeps what passes | That is a ticket the sweep files, not a ship step. Its rule "a cut stays only if as many tests ran" is **The tests that ran are counted** |

## Rules Rail owns

Size: M.

**What it does.** A small set of rules for kinds of bad code that no linter covers in all four languages,
written once and tested, so the build guide and the reviewer's brief need not ask for them in words.

**How.** Two engines, the lighter first:

- **Text, with `[[rules]]`, which is built:** an elision comment (`rest of the code`, `existing code
  unchanged`), text of a chat left in a file, a debug print in the language's usual form.
- **Syntax, with ast-grep** (MIT; Python, TypeScript, Go and Rust built in; rules in YAML with their own
  tests by `ast-grep test`; SARIF out; read): a handler that catches an error and returns a default or only
  logs; a function whose body only passes its arguments on; a test with no assertion, or one that compares a
  literal with itself.
- Not written as rules, because no tool was found that can: a test that mocks the thing it tests, an expected
  value special-cased to the test's input, a comment that repeats the code. Mutation on changed lines and
  tests written before the work cover the first two; the third stays with the reviewer.

**Kept when.** Each rule has its planted case and passes the past-commit test like any sensor.

**Waits for.** A trial first: the three syntax rules written for one language and run. Whether ast-grep's
`inside`, `has` and `follows` express them was not run.

## Tests and behaviour

In the order of cost:

1. **The change's tests run against the base's code** and **The tests that ran are counted** (above). No
   tool beyond the test runners.
2. **Changed lines no test runs.** diff-cover (Apache-2.0) reads Cobertura and LCov files and a diff, and
   writes JSON (read). The fact goes to the worker with the lines named. It is the cheap signal and the weak
   one: a line that runs is not a line that is checked.
3. **Mutation score on changed lines**, as the page has it, with one change: once the wrappers run, the
   surviving mutants go into the worker's brief as facts on the next round that happens anyway, and into the
   reviewer's brief. A bar that fails a ship still waits for 50 scored tickets.
4. **Interface and schema differences.** Where the repository tracks what they read, the tool's result is a
   fact that sets the kind `data-shape`, so the ticket is PERSON by a tool's word and not only by a path or a
   reviewer: oasdiff `breaking BASE HEAD --fail-on ERR` (exit 1; read), `buf breaking` (not confirmed), squawk
   for Postgres migrations (read), cargo-semver-checks `--baseline-rev` (exits 100 on a break, 101 when it
   could not finish; read).
5. **A behaviour question.** The product step keeps what it saw on each surface. Run on the base and on the
   head, a difference is a fact, and the triage question `behaviour` asks whether the ticket asked for it:
   `contract` (the quoted line is in the ticket) or `not-asked` (fails `triage`). In a ticket that keeps
   behaviour the same, any difference fails with no question. In one study three in ten patches that passed
   their tests behaved differently from the right one (reported).
6. **Tests written before the work.** A fresh run writes tests from the Done Contract alone, before any
   worker reads the ticket, and the worker cannot edit them without the `old-test` question. One agent solved
   94% of a benchmark with tests people wrote and 70% with tests it wrote itself (reported); no study was
   found that compares tests written by another run. This needs a model test of its own before it is kept.

## Security and supply chain

- **A check on each new dependency.** Size: M. When a change adds a name to a manifest or lockfile, the
  engine asks the registry whether it exists and when it and the version were first published (deps.dev's
  API gives both for PyPI, npm, crates.io and Go; read; its limits were not confirmed). A name that does not
  exist fails the ship. One younger than the cooldown goes onto the "Read these" list and makes the ticket
  PERSON. About one in twenty package names a model suggests does not exist, and the same wrong names recur
  (reported), so they can be registered by someone else. The host joins the environment's allowed hosts.
- **Cooldowns, written by `rail init` into the project's own files** (reported, each key read on the tool's
  page): uv `exclude-newer`; pnpm `minimumReleaseAge` in `pnpm-workspace.yaml`; npm `min-release-age`; Yarn
  `npmMinimalAgeGate`; Bun `minimumReleaseAge`; Cargo `registry.global-min-publish-age`. Go has none, so the
  check above covers it. A structure rule refuses a change that removes the line.
- **Workflows.** zizmor in offline mode on a change to `.github/workflows/**` (its exits 11 to 14 give the
  highest severity found, and it exits 0 when writing SARIF; read), and `pinact run --check` for actions not
  pinned to a commit. Such a change is PERSON today under `runs-with-secrets`; the findings go onto its
  "Read these" list.
- **Security rules on added lines:** Ruff `S` and gosec, as sensors. A security scanner and a model's review
  find different bugs (reported), and keeping only added lines is what holds a scanner's noise down.

## Review

One change: **what reproduces, decides.** The engine already runs a finding's command again and records
`reproduced`. A blocking finding whose command does not reproduce becomes advisory, with that fact shown. One
that reproduces is not answered by the author's word alone. Size: S.

Not built, for want of evidence: several reviewers with one focus each, reviewers from another model family,
many reviewers at once. No study was found that measures the first; a fresh run of the same model was the
part with evidence, and Rail has it.

## Order

**First: the engine alone. No new tool, no model.**

1. **Every line a model reads has a reason** (the ledger and the count).
2. **Every independent fact in one ship.**
3. **A fix step.**
4. **The change's tests run against the base's code.**
5. **The tests that ran are counted.**
6. **Guards against the cheap way past a check**, and **Hidden characters**.
7. **What reproduces, decides.**
8. Cooldowns written by `rail init`.

**Second: with the tools on a machine.**

9. **Sensors read structured output**, then **Findings new compared with the base**.
10. **Complexity and duplication sensors on by default**, then **Sensor sets per language**, with the picks
    and notes above, through the past-commit test.
11. Code only tests reach, and dead code, as base-compared sensors.
12. osv-scanner in the profiles; zizmor and pinact; security rules as sensors.
13. Changed-line coverage, then the mutation wrappers.
14. **Rules Rail owns**, after its trial.
15. **A check on each new dependency**; **Interface and schema differences**.
16. **`rail check`, and facts after an edit.**

**Third: when the owner restarts the model tests.**

17. **A runner for model tests**, then **The deletion test** on the text as it stands.
18. **A behaviour question**; a question `prepare`, asked when the facts about a ticket's scope (dead code,
    a function over the cap, a clone reaching out of scope) say the change does not fit the code, with the
    answers `fits` and `prepare`, the second of which files a refactor ticket the first waits for.
19. **Tests written before the work.**

**Fourth: when real tickets have run.** The numbers at the top of this page decide what is kept: a kind of
finding that stays high gets a check, a rule that is mostly exempted leaves, and each new model starts with
the deletion test.

## Open decisions

- Where the ledger's test draws the line between an instruction and a fact inside a brief built in code.
- The TypeScript formatter (above).
- Whether `tests-prove` fails the ship (proposed) or is a fact for the reviewer.
- Whether a new dependency younger than the cooldown makes the ticket PERSON (proposed) or fails it.
- Whether osv-scanner takes pip-audit's place at once (proposed) or runs beside it for a time.

## Not verified

- No tool on this page was run for it. Exit codes, flags and output formats are as read in docs; the ones
  not found there are marked.
- Versions and dates were read from release pages that often show no year.
- That the hash of a finding's text matches the same finding across a base and a head in each language. The
  recipe is GitHub's; Rail's use of it was not tried.
- That JUnit files from the four runners count skipped tests the same way.
- That knip's production mode, and a Rust build without tests, report code that only tests reach.
- That ast-grep can express the three syntax rules.
- That deps.dev answers without a key at the rate a busy repository needs.
- Every figure marked *reported*: read in a summary of the study, not in the study.
