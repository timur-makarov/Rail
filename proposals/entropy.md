# Code that agents can keep changing: what could be built

This page is a proposal. None of it is implemented. It says how Rail could keep agent-written code from
decaying, how it could keep what each step learns from being lost, and how each part would be tested before it
is kept. Status: written 2026-11-25 from Rail's engine code and docs, published research up to November 2026
(sources at the end), and the owner's decisions of 2026-11-24. Nothing here was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

**Agent code decays from change to change, and correctness checks don't see it.**

- On SlopCodeBench, where agents extend their own code over many checkpoints, complexity concentrated in
  branchy functions rose in 77% of runs and verbose or duplicated code in 75.5%. Agent code eroded about 5x
  and grew verbose about 7x faster per change than the median human repository. (reported)
- A prompt that lists what to avoid lowered the level of slop by up to a third, but not the rate of decay,
  and cost 2.4 points of solve rate. (reported)
- Telling the agent after each turn which of its changed functions were too complex lowered erosion for all
  four models tested, with no correctness cost detected; agents re-edited 87-94% of the flagged functions.
  This is the strongest result found for holding quality over many changes. (reported)
- Agents stop reusing code over turns: half of multi-turn task chains held duplicated logic by turn 5, with
  pass rates unchanged. Agent pull requests carry about 1.87x the redundancy of human ones. (reported)

**Rail has no sensor for this.** The reviewer reports style only when a rule says so; the sweep looks for
duplication and logic in the wrong area only in changes that merged with no review; two structure rules exist.
(confirmed: `engine/reviewer.md:12-14`, `engine/rail/sweep.py:16-23, 170-174`, `seed/config.toml:80-90`)

**What makes code readable to the next agent is partly measured.** Misleading names cut code completion by
17-34%; a type checker that blocks a change helped where annotations alone did not; success falls steeply
with the number of files a change spans; stale TODOs sent agents on detours of about 70% more steps. The
effects shrink as models get stronger. (reported; see "Code for the next agent")

**Rail loses some of what its steps learn.** The implement brief carries the Done Contract and scope but not
`## Why` or the decided assumption rows; a fresh worker after a failure gets the failure output and consult's
advice but not what the last worker tried; a person's note reaches the briefs only until the next ship;
`rail context` shows the area map and a directory digest but nothing earlier tickets learned about the same
paths. (confirmed: `engine/rail/table.py:90-110, 148-155`, `state.py:180-183`, `areas.py:64-72`)

## Bad code, defined

Code is bad when it makes the next correct change slower or riskier than the problem requires. Each kind below
names that cost and the one place that handles it.

| Kind | Cost | Handled by |
|---|---|---|
| A new copy of logic, 50 tokens or more | the copies drift; the next change edits N places | sensor (stage 1) |
| A touched function made more complex while over a high cap | reader load and bug rate | sensor (stage 1) |
| Escape hatches: ignore and suppression comments | the checks stop seeing errors | structure rule (stage 1) |
| Dead code added: an import, variable, parameter, export or dependency nothing uses | false leads for readers | sensor (stage 2) |
| Escape hatches in code: `Any`, unchecked casts, `unwrap` in library code | the checks stop seeing errors | sensor (stage 2) |
| Masked errors: empty catch, except-pass, an ignored error return | failures become invisible | sensor (stage 2) |
| An import across areas the map forbids, or a new import cycle | changes spread across areas | sensor, from the map (stage 2) |
| Drift: erosion per area, duplicated share, dead code totals, long functions and files, deep nesting, many parameters, files changed per ticket | slow decay no single change shows | trend, read by the sweep |
| Pass-throughs, options no caller uses, leaky interfaces, misleading names, code that search can't find, a concept in the wrong area, a special case in a shared flow | design cost no tool measures | `rail-build` (prevent), the sweep (find) |

## Part 1: sensors (core)

A **sensor** is a ship step backed by a tool. A **violation** is one line of its output. ("Finding" stays the
word for a review finding, and `Check:` stays the word for a Done Contract line.)

```toml
[[sensors]]
id = "duplication"
paths = ["**/*"]                    # runs only when the change touches these
command = "jscpd --config \"$RAIL_SENSORS/jscpd.json\" --reporters xcode ."
ok_exit = [0]                       # no violations
violations_exit = [1]               # violations printed
fix = "Call the code that already does this, or move both copies into one function."
```

1. **One step, last.** `sensors` runs after `checks`, at the end of ship (`engine/rail/steps.py:190`), so the
   Done Contract and `verify` speak first. It counts toward the retry budget and cap like any step.
2. **Only new code fails.** Each violation line reads `path:start[-end]: message`. The engine parses the hunks
   of the change's diff and keeps a violation whose lines overlap an added line, the principle structure rules
   follow ("old code never fails", `engine/docs/rules.md:3-4`). This needs new code: `rules.added` returns the
   added lines' text without their numbers (`engine/rail/rules.py:22-36`, confirmed). Lines git can mark as
   moved are dropped; reading that from git is listed under "Assumed, not verified". Old violations and
   whole-program findings in untouched files go to the trend.
3. **A touched legacy function doesn't block.** The complexity sensor uses lizard, which reads source text in
   all four languages and needs no build. It runs on the old and new text of each touched file. It reports a
   function when its span overlaps added lines, it is over the cap after the change, and its cyclomatic count
   grew. Growth in the cyclomatic count stands in for "the change added branches" (inferred proxy).
4. **The engine passes the base commit's configs.** `$RAIL_SENSORS` points at a copy of `.rail/sensors/` taken
   from the base commit, and `$RAIL_MAP` at the base's `ARCHITECTURE.md`. A ticket that edits them changes
   nothing for its own ship. `[[sensors]]` lives in `.rail/config.toml`, which is already in `person_paths`
   (`seed/config.toml:8`, confirmed); `.rail/sensors/**` joins it (Decision 3). Configs a project owns for
   its own tools (`tsconfig.json`, Cargo `[lints]`) stay editable; loosening them is what the reviewer already
   looks for ("a check weakened, skipped or deleted so that it passes", `engine/rail/review.py:42-44`,
   confirmed).
5. **Exits.** An exit the sensor doesn't declare is `could_not_run`, with the tool's output in the brief. Its
   brief needs its own text: today `could_not_run` says to install the tool (`table.py:150-152`), which is
   wrong for a crash or a config error. A tool missing on a person's own machine is `could_not_run` like any
   other command (`engine/docs/retries.md:29-33`); `rail doctor` lists the tools each sensor needs.
6. **A wrong sensor has a way out.** A comment `SENSOR(NN): why` on a line, or on the line above it, with the
   ticket's number, makes the engine drop that line's violations. No tool suppression is needed, so
   `no-new-suppressions` is unchanged. A structure rule refuses `SENSOR:` without a number, as it does for
   `SHORTCUT` (`seed/config.toml:86-90`). The reviewer's brief asks it to judge each new marker's reason;
   `rail stats` and the sweep count markers. Without the marker, a false violation with no fix in scope fails
   three times: the retry budget (2), consult, one more attempt, then a person (`engine/docs/retries.md:11-13`,
   confirmed).
7. **Output.** Each sensor names a one-line format and turns off its tool's caps on repeated findings
   (golangci-lint shows 3 of a kind and 50 per linter by default; reported). The engine strips colour codes
   and skips generated files and lockfiles, as the size check does.

**Stage 1 is language-neutral:** lizard (complexity growth), jscpd (new copies), and each language's
suppression markers added to `no-new-suppressions` (text, no tool). These match the strongest evidence (a
complexity signal in the loop; agents duplicating code) and need no profile.

## Part 2: language profiles (stage 2)

A **profile** is a language's further sensors, their tool configs, and its suppression markers. ("Pack" stays
the word for an optional feature that only adds hints, `engine/docs/packs.md:10-11`.) `rail init` detects
`pyproject.toml` or `setup.cfg`, `package.json` with `tsconfig.json`, `Cargo.toml` and `go.mod`. For each match
it writes the profile's `[[sensors]]` entries into `config.toml`, copies tool configs to `.rail/sensors/LANG/`,
adds the language's markers to `no-new-suppressions`, and adds a `provision` line that installs pinned tool
versions. A monorepo gets one profile per language, each limited by `paths`. After init every file is the
project's.

| | Dead code | Escape hatches and masked errors | Boundaries | Types |
|---|---|---|---|---|
| Python | Ruff F401, F841, ARG; deptry DEP001-DEP004 | Ruff S110, BLE001, E722, PGH003, ANN401 | import-linter | the project's checker, else basedpyright |
| TypeScript | knip (files, exports, dependencies) | oxlint, type-aware: no-explicit-any, ts-comment bans, empty catch, floating promises | dependency-cruiser | tsc (strict by default since TypeScript 6) |
| Rust | rustc dead_code; cargo-shear | clippy, pinned, `clippy.toml` through `CLIPPY_CONF_DIR`: unwrap_used and expect_used in library crates, let_underscore_must_use, map_err_ignore | crates and `pub(crate)`; cargo-deny bans | rustc |
| Go | golangci-lint v2 unused, unparam; deadcode; `go mod tidy -diff` | errcheck with check-blank, forcetypeassert, nolintlint with require-explanation | depguard or go-arch-lint | the compiler; go vet |

The boundary sensor builds its tool's config at run time from `$RAIL_MAP` (Part 3), so no generated file goes
stale. Suppression markers per language include `# type: ignore`, `# pyright: ignore`, `@ts-expect-error`,
`biome-ignore`, `oxlint-disable`, `#[allow(` and `//nolint`; the `SENSOR(NN)` marker is the one way past a
sensor.

Tool facts checked on primary sources on 2026-11-24 and 2026-11-25 (reported): Ruff has no baseline mode;
oxlint has an undocumented bulk-suppression file; Clippy reads `clippy.toml` from `CLIPPY_CONF_DIR` first and
calls the file unstable, so the profile pins Clippy; Clippy thresholds can't be set in `Cargo.toml`; jscpd v5
installs by pip, cargo, Homebrew or a standalone binary, needs no Node, and prints one clone per line with
`--reporters xcode`. Rail needs no baseline mode, because it keeps only violations on added lines.

**Thresholds.** A sensor fails a ship only on code that is almost never right. The usual textbook values feed
the trend.

| Measure | Counts | Usual defaults | Sensor | Trend |
|---|---|---|---|---|
| Cyclomatic complexity (lizard) | paths: 1 + each branch, loop, case, `and`/`or` | 10 (McCabe, Ruff), 15 (lizard), 20 (ESLint) | 20, and grew | over 10 counts toward erosion |
| Cognitive complexity | how hard a function is to follow; nested branches weigh more | 15 (Sonar, complexipy), 25 (Clippy), 30 (gocognit) | none | over 15, where the language has a tool |
| Nesting depth | blocks inside blocks | 4 (ESLint), 5 (nestif, Ruff) | none | over 5 |
| Parameters | arguments of one function | 3 (ESLint), 5 (Ruff), 7 (Clippy) | none | over 5 |
| Function length | lines | 50 (ESLint), 60 (funlen), 100 (Clippy) | none | over 100 |
| File length | lines | 300 (ESLint), 1000 (pylint) | none | over 1000 |
| Duplication (jscpd) | a repeated run of tokens | 50 tokens / 5 lines | 50 tokens, new copies | duplicated share |

Why few, high sensors: a false violation that repeats reaches a person after three attempts; tight limits get
gamed (agents removed an architecture violation by deleting the new file in 44 of 125 runs in one study;
reported); some complex functions are legitimate. Why no length sensor: max-lines rules pushed complexity
elsewhere (Böckeler), and longer files scored better on code questions in LongCodeBench (reported). Erosion is
SlopCodeBench's measure: the share of complexity (cyclomatic x square root of lines) held by functions above
10. The replay test tunes every value.

**Left out:** Semgrep's rules (their licence bars use in products and SaaS), CodeScene (paid), in-crate layering
tools for Rust (young), per-language prose pages (models know the idioms; each sensor's `fix` line carries the
advice).

## Part 3: the map drives boundaries (stage 2)

`## Areas` in `ARCHITECTURE.md` gains an optional fourth column, `Uses`: the areas this one may import. The
boundary sensor reads the map from the base commit and builds its tool's rules from it. A path no row maps, and
a row with no `Uses`, is unrestricted, so a ticket that adds a directory (and must add its row, `doclint.py:131-135`,
confirmed) fails nothing. A new row's rules apply from the next ticket. The parts that need code: `areas.py`
reads the column (today it keeps three, `areas.py:18-25`, confirmed), doc-lint checks that every name in `Uses`
is an area, and the review brief shows the column (`review.py:244`). An agent may change `Uses` on an AUTO
ticket; the reviewer's brief asks it to judge any change to the column.

A structure rule can already forbid one import text in a set of files (`engine/docs/rules.md:7-13`). The map
column adds a single place where boundaries are written, read by tools that understand each language's imports.

## Part 4: `rail-build` and `rail-debug` (craft)

Section 5 of `rail-build` keeps its reuse list and gains lines only for what no sensor checks. Proposed text,
replacing the `Abstraction`, `Place` and `You notice a problem` lines:

> - **Repeated code:** a run of 50 tokens or more that already exists fails the duplication sensor. Call the
>   code that exists, or move both copies into one function. Shorter repetition, such as wiring, may stay.
> - **Interfaces:** before you add or change an interface (an exported function or type, a CLI flag, a config
>   key, a file format, an endpoint), find its callers. Give it the parameters and options they use, and what
>   the Done Contract asks for.
> - **Pass-throughs:** a new function or module hides work from its callers. When it only hands a call on, call
>   the target directly.
> - **Names:** one name for one concept, the same in every layer. A name says what the thing is or does; long
>   and specific is fine.
> - **Found by search:** write each use of a name so that grep finds it: spell identifiers out where they are
>   used, and register a handler where the registry is. Where the codebase registers by decorator or init
>   function, follow its pattern.
> - **Place:** put code in the area whose `Holds` names its concept. Logic for one feature lives with that
>   feature, not as a branch inside a shared flow. When several callers share a fault, fix the shared code.
> - **You notice a problem the ticket didn't ask about:** leave it, and write a `Noticed:` line in `## Look at`.

Section 7 step 4 adds: "Write a `Noticed:` line for each problem outside the ticket." Section 3 loses its
`rail context` line once the brief carries the context history (Part 6). Counted: 97 lines today, 7 bullets
for 3 (about +12 lines), section 3 and 7 changes (about -1): about 108 lines, slightly over the guide rule's
"about a hundred" (`engine/docs/guides.md:61`).

`rail-debug` gains two lines. Step 4: "Write each explanation you ruled out under `## Tried` in the ticket."
Step 7: "A sensor is wrong on one line: mark it `SENSOR(NN): why`. Wrong in general: open a ticket that
changes `.rail/sensors/`." This sits beside the existing rule for a wrong `Check:` (`rail amend`), which stays:
a `Check:` is the contract, a sensor is not.

How the pages are written stays as `guides.md` says, and the research supports it: no persona ("you are the
best engineer" showed no gain in any study found), no capitals for emphasis (Anthropic: emphasis makes the
models over-apply a rule), a reason with each rule, the wanted behaviour stated, and effort set by the worker
ladder rather than "think hard". Anthropic's page for Fable 5.2 reports that the sentence "You are the owner and
long-term maintainer of this codebase" made it merge duplicated code in about 75% of runs against under 10%,
at 70-80% more output and some unrequested changes (reported). It is a test arm only: it was measured on
Fable, and Rail's workers run on Sonnet 5.5 and Opus 5.5.

## Part 5: the design sweep (core)

1. **It reads reviewed merges too.** Every `[sweep] every` merged tickets (20), whatever their review, the
   sweep's reviewer pass reads the current code of the areas that changed since the last sweep. Today a sweep
   with nothing unreviewed runs no model (`sweep.py:170-174`, confirmed); this adds one model run per 20
   tickets.
2. **It gets the numbers.** The trend commands (lizard, jscpd, and each profile's own) report per area the
   trend measures in Part 2, sensor-rule counts over the whole tree, and `SENSOR(NN)` markers. From the
   journals the engine adds, per area, files and areas changed per merged ticket, failed steps and review
   rounds. (The worker's cost is not recorded today; only review runs carry `cost_usd`, `steps.py:52-67`,
   confirmed.) The sweep stores the numbers in a `trend` event, so the next sweep and `rail stats` see the
   change.
3. **It files refactor tickets.** Each names a kind from "Bad code, defined", with evidence (tool output, or
   two `file:line` places) and its cost. Its `Check:` lines are the tests plus a threshold command that fails
   before the refactor and passes after. At most `[sweep] max_refactor_open` (3) refactor tickets are open at
   once, as sources cap theirs with `max_open` (`engine/docs/sources.md:10`); the rest stay in the summary
   with their numbers. A refactor over `[size] cap` is offered a split like any ticket. A kind that keeps
   returning gets a "make it a check" ticket; when that check is a sensor or rule in `.rail/config.toml`, the
   ticket is PERSON, as such tickets are today.
4. **It collects what tickets left behind** (Part 6).
5. **The findability probe (optional, Decision 4).** For up to five tickets merged since the last sweep, a
   fresh agent gets only the ticket's `## Why` and the repository at the ticket's base, and names the files it
   would change. The score is its overlap with the files the ticket changed. A falling score per area means the
   next agent can no longer find its way there. Inferred: the merged diff is the answer key, so no person
   grades it. It adds up to five model runs per sweep.

## Part 6: nothing learned is lost (core)

Information survives when it is written down outside any context window, kept in one known place, sent by the
engine to the next agent that needs it, marked confirmed, inferred or decided, and closed: done, a ticket, a
check, or dropped. Sending matters: tools that were only available went unused, and repository overviews did
not help agents find files (reported). The engine builds every brief, so it can send each agent only what
applies to its paths and its situation.

| Stage | Learned | Today (confirmed) | Change |
|---|---|---|---|
| Request | Intent, constraints, the person's answers | In the ticket; the implement brief names the ticket file but carries neither `## Why` nor the decided rows (`table.py:90-110`) | The implement brief carries `## Why` and the `VERIFIED: decided` rows |
| Building | What was tried, what was ruled out | The worker's context only | A `## Tried` section in the ticket, one line per attempt, sent in the next `STEP_FAILED` and `IMPLEMENT` brief. Consult's brief strips it as it strips `## Look at` (`consult.py:31-32`); the reviewer sees the whole ticket today, `## Look at` included (`review.py:240`) |
| Earlier tickets on the same paths | Decided rows, "not tested" lines, open markers | Merged ticket files and journals on the base branch | `rail context NN` lists, for the ticket's paths, the last five merged tickets: title, the first line of `## Why`, decided rows, "not tested" lines, open `SHORTCUT` and `TODO` markers. The implement brief includes it |
| Out-of-scope problems | Bugs and smells noticed in passing | A `## Look at` line, if any; nothing collects it | `Noticed:` lines. The sweep collects them, and the "not tested" lines |
| Review | Findings and answers | The sweep collects parked findings and the checks of fixed ones (`sweep.py:97-121`) | The sweep also collects declined findings, grouped by kind |
| A person's word | `rail accept` notes, pull request comments | The briefs until the next ship (`state.py:180-183`) | The sweep collects every note since the last sweep and files a ticket for each that reads as a standing rule |
| Repeated failures | Failure signatures | Counted within one ticket | The sweep flags a signature that recurs across tickets and files a check or an `AGENTS.md` line |
| Work left for later | `TODO` and `FIXME` comments | Free text | A structure rule: a `TODO` or `FIXME` names the open ticket that will do it, `TODO(NN)`, filed with `rail add`. The sweep files a removal ticket when that ticket merged or was dropped and the comment is still there. (`SHORTCUT(NN)` names the current ticket; `TODO(NN)` names a later one) |

Left out on purpose: a free-form reasoning log. Each change above is a section or an event with one reader and
one way to close.

## Code for the next agent

What research says matters to an agent that reads code (reported; sources at the end):

1. **Names.** Obfuscated names cut model code understanding by 10-30 points across studies; a misleading name
   did more damage than a meaningless one. Agents find code by search: Cursor turned down embeddings indexing
   in favour of grep in July 2026.
2. **A checker in the loop, not annotations alone.** A blocking type checker raised correct outcomes from 1 to
   11 of 12 seeded bugs in one study; type hints with no checker made no difference in 766 runs in another.
3. **Locality.** About 48% of one-file fixes under five lines were solved, under 10% at three or more files.
4. **Fresh text.** Stale TODOs and outdated comments misled agents.
5. **Less magic.** Practitioners agree on explicit wiring and search-friendly names; no controlled study yet.

Human-centric habits to drop: terse names, clever one-liners, small files to fit a screen, sharing glue code to
save typing, inheritance and decorator magic, identifiers built from strings, style argued in review, long
overview docs, comments that narrate history. Kept for people: one name per concept, one home for every rule,
data format and schema, boundaries people own (the map), tests that read as a specification, a reviewable diff
size, structured logs.

Where this proposal covers them: names and search (Part 4 and the sweep), checkers (Part 2), locality (the
trend and the probe), fresh text (Part 6), boundaries (Part 3). Names and interface design have no sensor; the
next-change numbers in Part 5 and the probe are how their effect is seen.

## Tests, each before its part is kept

Decision rules are fixed here, before any run. Sample sizes are small: with about 24 tickets per arm, a rate is
known to about 20 points either way (1.96 x the square root of 0.25/24, inferred). The model arms therefore run
the same tickets in every arm, so each ticket is compared with itself, and the rules below ask only for large
differences.

1. **Gate cases, no model.** Per sensor and language: a planted violation fails; a clean change passes; code
   that only moved passes; a touched legacy function the change doesn't make more complex passes; a
   `SENSOR(NN)` line passes and `SENSOR:` without a number fails; a sensor config edited on the ticket's branch
   has no effect; a new directory with a new map row passes the boundary sensor; a `TODO` without a number
   fails. Kept when every case behaves as written.
2. **Replay, no model.** For each language, the last 200 merged commits of two active open-source projects pass
   through stage 1 and the profile. Recorded: the share of commits that would fail, per sensor and for the
   profile as a whole; the minutes added; ten failures per sensor read by hand. A sensor stays in the default
   when it fails at most 5% of human commits, at least 8 of the 10 read failures are a real instance of its
   kind, and the whole profile fails at most 15% of commits and runs in under a third of `timeout_secs` (900).
   Thresholds are tuned here first. The boundary sensor is checked on one project per language for which a map
   is written by hand.
3. **Model arms.** A: Rail as now. B: A plus stage 1. C: B plus the profiles. D: C plus the Part 4 text. E: D
   plus the design sweep and Part 6. Plus D with the Fable 5.2 ownership sentence added to the brief, on the
   same worker models. Work: SlopCodeBench problems (Python, graded with its `scb-check`) and one multi-ticket
   project per other language, graded with lizard and jscpd. Measured per arm: erosion and verbosity growth,
   strict solve rate, review rounds, person waits by cause, waits whose failing step is `sensors`, and review
   cost. A part is kept when, against the arm before it: erosion growth is lower by a third or more; the solve
   rate is not lower by more than 10 points; person waits are not higher; and no ticket waits for a person
   because of `sensors`. The ownership sentence is kept on the same rule, and when it adds no more scope
   amends or split offers than arm D.
4. **Probe pilot.** Four runs on one area as it is, and four on a copy with identifiers renamed to
   placeholders and one module's logic spread over three files. Kept when the damaged copy scores lower in at
   least 3 of the 4 pairs.
5. **Part 6, from the journals.** Before and after, over the same number of merged tickets: failure signatures
   that recur across tickets, and how many collected items ended as a merged ticket or check. A collection that
   leads to nothing in five sweeps is removed. The trend itself has no rule: it is kept while the sweep reads
   it.

Not covered: how well a person can audit agent-first code; languages other than the four; effects that take
more than a few dozen tickets to show; the cost of the worker, which is not recorded.

## Assumed, not verified

- That git's moved-line detection can be read reliably from a diff: it is a feature of coloured output
  (`--color-moved`), and `rules.added` asks for `--no-color` on purpose (`rules.py:23`, confirmed).
- That each tool's one-line format holds for every rule a profile turns on (jscpd's `xcode` reporter was read in
  source; the others in docs), and that each tool's exit codes are as the profile declares them.
- That lizard parses all four languages well enough to compare one function before and after.
- That oxlint's type-aware mode is stable enough for a default; it is young.
- That basedpyright on a project with no types doesn't flood the added lines of every change.
- The rule names and values in Part 2: read on the tools' docs or source by a research agent, not run.
- That CI checkouts hold the base commit's blobs for `$RAIL_SENSORS` and `$RAIL_MAP`.
- That the implement brief stays short with `## Why`, the decided rows and five tickets of history added.
- The cost of the design sweep's model run over the areas that changed in 20 tickets.

## Order of work

One pull request each, with docs and `CHANGELOG.md`. Nothing becomes a default before its test.

1. Engine: `[[sensors]]`, the `sensors` step, hunk-line parsing, `$RAIL_SENSORS` and `$RAIL_MAP` from the
   base, `SENSOR(NN)` and its rule, the `could_not_run` brief for a sensor, the reviewer's line on markers,
   `rail doctor` listing sensor tools; gate cases (test 1). No sensor is on by default.
2. Stage 1 (lizard, jscpd, suppression markers) and its replay (test 2); then on by default.
3. Part 6, the engine changes: `## Why` and decided rows in the brief, `## Tried`, `Noticed:`, `TODO(NN)`,
   the context history. Test 5 starts here.
4. The profiles, one pull request per language, each with its replay; then on by default.
5. The `Uses` column: `areas.py`, doc-lint, the review brief, the boundary sensors.
6. The design sweep: reviewed merges, the `trend` event, refactor tickets, the collections.
7. After the model arms (test 3): the `rail-build` and `rail-debug` text.
8. The probe, after its pilot (test 4), if Decision 4 keeps it.

Tests 3 and 4 use models and wait until the owner restarts the paused model tests.

## Decisions

**Made by the owner (2026-11-24):** no design review step; oxlint for TypeScript; the `Uses` column; a marker
for a wrong sensor (now `SENSOR(NN): why`, read by the engine, so `no-new-suppressions` needs no exemption).

**Open:**

1. The refactor cap as "open at once" (`max_refactor_open`, proposed) or "per sweep".
2. The touched-legacy rule: fail only when a function over its cap gets more complex (proposed), or whenever a
   touched function is over its cap.
3. `.rail/sensors/**` in `person_paths`. Proposed: yes, as `.rail/config.toml` already is, since both hold the
   gates. `ARCHITECTURE.md` stays out: every ticket that adds a directory must edit it.
4. The probe: build it after its pilot, or not at all.

## Sources

Rail, confirmed: `engine/reviewer.md`; `engine/rail/review.py`; `engine/rail/sweep.py`; `engine/rail/table.py`;
`engine/rail/state.py`; `engine/rail/areas.py`; `engine/rail/rules.py`; `engine/rail/steps.py`;
`engine/rail/doclint.py`; `engine/rail/consult.py`; `engine/docs/`; `seed/config.toml`;
`seed/skills/rail-build/SKILL.md`; `seed/skills/rail-debug/SKILL.md`.

Research, reported:

- SlopCodeBench, Orlanski et al., arXiv 2603.24755 (v2, 2026-05-07); https://www.scbench.ai/;
  github.com/SprocketLab/slop-code-bench; scb-check.
- Metrics in the loop, Chapados, Gagné, Dziri, arXiv 2611.23817 (2026-11-18).
- RepoReuse, arXiv 2609.35357; "More Code, Less Reuse", arXiv 2601.21276.
- SWE-Maintain, arXiv 2610.14768: the debt that hurts the next task is failing tests more than structure.
- He et al., "Speed at the Cost of Quality", MSR 2026: after Cursor adoption, static warnings +30% and
  cognitive complexity +42%.
- "Fixed or Deleted?", arXiv 2611.29162.
- Böckeler, "Harness engineering" (2026-04-02) and "Maintainability sensors" (2026-05-27), martinfowler.com.
- OpenAI, "Harness engineering" (2026-02-11).
- Names: arXiv 2510.03178, 2504.10557, 2609.26388. Types: fedur.co/blog/type-hints-and-coding-agents
  (2026-10-23); github.com/ianbarber/lsps-for-llms. Locality: SWE-bench-Live, arXiv 2505.23419. Stale text:
  Google Developers Blog, "Agent Distraction" (2026-11-06). Code health: Borg, Tornhill et al., arXiv
  2601.02200. LongCodeBench, arXiv 2505.07897.
- Context files: Gloaguen et al., arXiv 2602.11988 (v3, 2026-09-29).
- Review framing: Mitropoulos et al., arXiv 2603.18740; self-attribution, arXiv 2603.04582; critics, arXiv
  2610.34577.
- Personas: arXiv 2311.10054, 2512.05858. Rule counts: arXiv 2507.11538, 2607.19257.
- Anthropic: prompting best practices and the Opus 5.5, Fable 5.2 and Sonnet 5.5 pages,
  platform.claude.com/docs/en/build-with-claude/prompt-engineering/; Claude Code best practices,
  code.claude.com/docs/en/best-practices.
- Tools: docs and repositories of Ruff, complexipy, deptry, import-linter, basedpyright, oxlint, knip,
  dependency-cruiser, Clippy, cargo-shear, cargo-deny, golangci-lint, deadcode, jscpd, lizard.
