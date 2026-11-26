# Python, TypeScript, Rust and Go first: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and are
no longer described here: language detection from the tracked manifests, the `[[profiles]]` entries, each
language's suppression-marker rule, migration paths, generated files and test paths, and the registries added
to the sandbox's domains (`rail docs languages`, `rail docs rules`); the default `setup` and `verify` for each
language, with the manager chosen by lockfile, one folder per profile in a monorepo, and the init task's text
(`rail docs languages`); Go's generated-code comment in the size count (`rail docs languages`); the outcome
counts split by language (`rail docs stats`); and one small real project per language that goes from `rail init`
to a merged ticket (`rail docs languages` lists which lines it runs). Nothing below is implemented, and nothing
below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given. Tool names and command lines marked **not checked** come from my own knowledge;
the fixture tests (Tests, case 3) check each one before it ships.

## Why

**The owner's position (2026-11-25):** Rail is Python, TypeScript, Rust and Go first, not language-neutral.
Anything that blocks those four setups from being as useful as possible is unsupported. A design choice that
makes one of the four worse for the sake of neutrality is not made.

What init writes today stops at the project's files. Four things the four languages need are still missing
(confirmed in `engine/rail/init.py`, `engine/rail/doctor.py` and `seed/config.toml`):

- **Nothing installs the tools.** Init writes `setup` and `verify`, and leaves `provision` empty, so the
  scanners and linters `verify` names are on a cloud machine or a CI runner only when an agent writes the
  line. Nothing checks a toolchain or its pin: `rail doctor` knows the sensors' tools and `[tools.NAME]`
  declarations, no language's compiler.
- **No score for tests, and no named tools for good ones.** `seed/config.toml` has no `[commands] mutation`,
  and the seed's skills name no property, fuzz or driving-check tool per language.
- **A monorepo gets one command per folder and nothing more.** Workspace layouts and an affected-aware
  `verify` are only a sentence in the init task.
- **A language added after init is not picked up.** An existing `.rail/config.toml` is never touched, so a Go
  service added next year gets no profile.

**Why these four.** The research behind this page found TypeScript first among GitHub contributors and among
new repositories with an agent signal, Python first in usage surveys and for work done with AI tools, Rust
growing fastest from a smaller base, and Go flat (reported). Agent stack choices follow the repository more
than the prompt, so a profile per language, not one global stack, is what the research supports (reported).
Choices are measured for TypeScript and Python; Go and Rust choices are measured only for a narrow set of
libraries (reported).

## Part 1: provision and the toolchain pin

Each profile's `profile.toml` (`profiles/LANG/profile.toml`) gains what installs its tools, and `rail init`
writes it into a new config's `[commands] provision`, next to the `setup` and `verify` it already writes. Every
line is **not checked** until its fixture runs it (Tests, case 3).

| | Python | TypeScript | Rust | Go |
|---|---|---|---|---|
| Toolchain pin `rail doctor` looks for | `.python-version` or `requires-python` | `packageManager` in `package.json`, and `engines.node` | `rust-toolchain.toml` | the `go` and `toolchain` lines of `go.mod` |
| Provision | uv, then the tools `uv tool install` pins | Node via the pin, corepack for the manager | rustup with the pinned toolchain, `cargo install --locked` for cargo-deny | the Go toolchain from the pin, golangci-lint and govulncheck pinned |
| Installing runs package code? | a wheel runs none; building an sdist runs its build backend. `setup` adds `--no-build`, wheels only (not checked) | built: `setup` passes `--ignore-scripts` | yes, always: `build.rs` and procedural macros run at every build, with no switch | no: fetching and building run no package code (cgo compiles C the package ships, not scripts) |

Only the Python `--no-build` is left to write in that last row; the others are described to say why Rust has
no switch. The profile's tools (ruff, basedpyright, pip-audit, oxlint, cargo-deny, golangci-lint, govulncheck,
gitleaks) get one install line each, pinned to a version. Init never writes a `provision` into an existing
config.

**`rail doctor` gains a line per profile:** the toolchain is on PATH and matches the pin; each tool the
profile's `verify` names is installed; the pin file exists (missing: a ticket for the machine, since adding a
pin is reversible work an agent can do); the registry domains are in the sandbox list when the sandbox is on. A
missing tool on a cloud machine points at `provision`; on a person's machine it names the install, which is
the person's to run. Each profile tool could be a declared `[tools.NAME]` with its own probe (`rail docs
tools`); until then doctor checks `command -v`.

## Part 2: monorepos

What exists (confirmed in `engine/rail/init.py`, `tests/test_languages.py`): manifests below the root give one
profile per language with the folders that hold them (`web/**`, `{api,worker}/**`), a nested manifest
inside another's folder counts for the top-most folder only, each part of `verify` and `setup` runs in each
folder (`(cd web && pnpm test)`), and Cargo's `cargo test --locked` at a workspace root runs every member.

What is not built:

**Workspaces.** uv workspaces, pnpm workspaces and `go.work` are layouts the profiles would recognise: one
profile per workspace root, with the commands written to run across the workspace (`uv sync --all-packages`,
`pnpm -r`, `go test` over each module of `go.work`; not checked). Today `uv sync --locked` at a uv workspace's
root syncs the root package only, and a `go.work` repository is read as one profile per folder that holds a
`go.mod`, each with its own commands.

**An affected-aware `verify`.** The init task only asks the agent to make `verify` affected-aware in a
monorepo; nothing in the engine or the profiles does. Per language, only pnpm has a built-in filter for
packages changed since a ref (`--filter "...[$RAIL_BASE]"`, not checked); Go caches test results for unchanged
packages (not checked); for Python and Rust the whole workspace runs. The proposal: the pnpm filter in the
TypeScript default when a `pnpm-workspace.yaml` is tracked, and nothing for the other three until the time per
step shows `verify` is too slow (`rail docs stats`, "WHERE THE TIME GOES", shows it).

**Worktrees.** Each ticket gets its own worktree (`.claude/worktrees/NN`), and `setup` runs in each. uv and
pnpm link from a shared cache, and Go shares its module and build caches, so a new worktree is cheap for three
of the four (not checked). Rust builds `target/` from nothing in each worktree. Sharing one `CARGO_TARGET_DIR`
across worktrees makes concurrent builds wait on Cargo's lock on that folder (not checked). The proposal:
measure first; if Rust `setup` and `verify` dominate, the Rust profile adds a compiler cache (sccache) to
`provision` (Decision 1).

## Part 3: a language added after init

`rail init` writes profiles only into a config it creates. Run again on a repository that has one, it lists
what it found ("`.rail/config.toml` was there already, so nothing was written to it") and merges the registry
domains into `.claude/settings.json`. It prints no entry, command or rule to paste, and `rail doctor` doesn't
compare the tracked manifests with the `[[profiles]]` entries. A Go service added later gets no suppression
rule, no `[size] exclude`, no migration path, no `[tests] paths` and no `setup` or `verify` lines, unless the
person writes them from `rail docs languages`.

The proposal (not in the page this one was cut from; it follows from the rule that an existing config is never
touched): `rail doctor` names a tracked manifest whose language has no `[[profiles]]` entry, and prints the
entries, rules and commands init would write for it, for a person to paste into the config or into a ticket
(`.rail/config.toml` is a person's path, so the change is a person's to approve). The init task's text for a
re-run says the same. The existing config stays untouched (Decision 3).

## Part 4: mutation commands

The mutation score is a number for the tests on the changed lines: how many mutants of the changed code the
tests kill. It needs `[commands] mutation`, a command that prints one JSON line `{"killed": K, "survived": S,
"timeout": T}`. `proposals/checks.md` Part 6 owns the key and the score; neither is built. Each profile would
ship a short wrapper, written by
`rail init` to `.rail/profiles/LANG/mutation` (the project's file afterwards), that scopes the run to the diff
against `$RAIL_BASE`, runs the tool, reads its report and prints the line; mutants that don't build are left
out of all three counts. With no changed source file it prints zeros without running the tool. Each tool's
report format is not checked.

| | Python | TypeScript | Rust | Go |
|---|---|---|---|---|
| Mutation on changed code | mutmut 3, scoped by module patterns built from the diff | StrykerJS, scoped by `--mutate` with the changed files | cargo-mutants `--in-diff` | gremlins `--diff "$RAIL_BASE"` |

Read on 2026-11-25: cargo-mutants and StrykerJS on their whole docs pages (confirmed); mutmut, gremlins and
gremlins#301 in search excerpts of their primary pages, not read in full (reported):

- **cargo-mutants** `--in-diff DIFF_FILE` tests only mutants overlapping the diff's changed regions, ignores
  non-Rust files, and runs nothing for a diff that only changes tests (mutants.rs, "Testing code changed in a
  diff").
- **mutmut 3** has no line or diff mode. Its `run` takes wildcard patterns over mutant names, at module level;
  mutating only covered lines is a setting (`mutate_only_covered_lines`). A diff-scoped run is a small script
  that turns changed files into module patterns (PyPI page for mutmut 3.8.1; a September 2026 write-up reports
  that a pattern matching nothing raises an error, reported).
- **StrykerJS** `--incremental` reuses a previous run's report file and re-tests what changed since; it is not
  a diff against a base. Restricting `--mutate` to the changed files is the diff-scoped form (Stryker docs,
  "Incremental"; the `--mutate` form is not checked).
- **gremlins** has `--diff REF`, which tests only mutants in code changed against a ref, and mutates only lines
  the tests cover. It is still 0.x, made for "smallish" modules, and an open bug (go-gremlins/gremlins#301,
  August 2026) skips the later edits of a hunk that holds two, silently. Go's score is the weakest of the four
  until that is fixed; the score is a trend, not a gate, so a low reading fails nothing.

The Python and TypeScript wrappers mutate whole changed modules or files, so their counts include unchanged
code in those files; cargo-mutants and gremlins mutate changed regions or lines.

## Part 5: tests that catch mistakes, and driving checks, per language

The seed has no guidance on property tests, idempotency, differential checks, fuzzing, a real database or
migrations up, down and up (`proposals/entropy.md` Part 4 proposes it as `rail-build`), and no recipe per
surface in `rail-verify` (`proposals/product.md` owns the surfaces). When they land, this page names the tool
each language uses, so the guidance has a concrete command:

| | Python | TypeScript | Rust | Go |
|---|---|---|---|---|
| Property tests | Hypothesis | fast-check | proptest | rapid (`pgregory.net/rapid`), or the standard library's `testing/quick` |
| Fuzzing | Hypothesis (no separate fuzzer by default) | fast-check | cargo-fuzz (needs nightly Rust) | `go test -fuzz` (built in) |
| Real database in tests | testcontainers | testcontainers | testcontainers (Rust crate) | testcontainers-go |

| Surface | Python | TypeScript | Rust | Go |
|---|---|---|---|---|
| Web interface | Playwright (its Python package) | Playwright Test | Playwright Test against the built server | Playwright Test against the built server |
| HTTP API | requests from pytest against the running server; Schemathesis on the schema | requests from Vitest against the running server | the built server and a client in an integration test | the built binary, and `net/http` requests from a test |
| Command line | the installed entry point run in a temporary folder from pytest | the built CLI run from Vitest | assert_cmd on the built binary | testscript (`rogpeppe/go-internal`) |
| Agent-facing (MCP) | the official Python SDK's client | the official TypeScript SDK's client, or MCP Inspector | the official Rust SDK | the official Go SDK |

All tool names are not checked. A web interface is driven by Playwright whatever language serves it, so a Go or
Rust project with a web surface needs Node on the machine: its profile's `provision` adds Node only when the
project has a web surface (inferred). The driving-check paths join `[tests] paths`, so the base-version rule
for tests covers driving checks too. Rust unit tests live in `#[cfg(test)]` modules inside source files, so for
Rust that rule covers only integration tests (inferred). The Blender and video examples stay out of the
per-language tables.

## Docs and files that change

- `profiles/{python,typescript,rust,go}/profile.toml`: the provision lines and pins; each language's `mutation`
  wrapper beside them.
- `engine/rail/init.py`: `provision` and `mutation` written into a new config; the Python `--no-build`; the
  re-run text. `engine/rail/config.py`: the `[commands] mutation` key.
- `engine/rail/doctor.py`: the per-profile lines, and the manifest with no profile.
- `engine/docs/languages.md` and `engine/docs/stats.md`: the same changes.
- `seed/skills/rail-verify/SKILL.md`: the per-language driving-check tools of Part 5.
- `tests/projects/LANG/` and `tests/test_languages.py`: the cases below.
- `proposals/entropy.md` Part 2: a pointer to this page, since the two share `profile.toml` and the detection.

## Tests, each before its part is kept

1. **Doctor and provision, no model, no toolchains.** On fixture trees:
   - init writes a `provision` into a new config for each profile found, and none into an existing one;
   - `rail doctor` reports a missing toolchain, tool and pin, and the registry domains missing from the
     sandbox list;
   - `rail doctor` names a tracked `go.mod` in a repository whose config has no `go` profile, prints the
     entries, rules and commands init would write, and changes no file;
   - a tree with a `pnpm-workspace.yaml` gets the filtered `verify`, and a tree with `go.work` or a uv
     workspace gets the workspace commands.
   Kept when every case behaves as written.
2. **The re-run text, no model.** The init task on a repository whose config exists names the profiles missing
   from it. Kept when the brief holds them for each fixture.
3. **Each fixture end to end, no model, four toolchains.** Run, in a cloud session with all four toolchains,
   what the fixtures don't run yet: `provision` installs what the profile names; the audits (pip-audit, pnpm
   audit, cargo-deny, govulncheck), the secret scan (gitleaks), basedpyright and oxlint each fail on a planted
   mistake (a lockfile pinned to a version with a known advisory, a fake secret in a commit, a type error, a
   lint error) and pass again when it is removed; the lines for Poetry, pip, npm, Yarn and Bun, if they are
   kept (Decision 4); and the fixture's driving check from Part 5 (the API, web page or CLI of its shape)
   passes, and fails when the behaviour it drives is broken. This is the check on every command line marked
   not checked above. Kept when every case passes; a part whose planted mistake doesn't fail is fixed or
   dropped before it ships.
4. **Mutation commands, no model.** On each fixture, a ticket that changes one function: the profile's
   mutation command runs only mutants in that function, and a test removed from that function's suite lowers
   the score. Each wrapper prints exactly one line of JSON with the integer keys `killed`, `survived` and
   `timeout` and exits 0, and prints zeros without running the tool when no source file changed. For Go, a
   ticket with two edits in one hunk shows whether gremlins#301 still skips the second.
   Kept per language when both hold; a language whose command fails is left without a mutation score until it
   passes.
5. **Init with a model.** Four real repositories, one per language, none prepared for Rail; init with profiles
   against init as the seed first wrote it, 4 runs each. Graded: each part of `verify` (tests, lint, types,
   format, secret scan, audit) present and shown to fail on a planted mistake; the same `verify` across the 4
   runs. Kept when the profile arm covers at least as many parts as the other arm in every repository and gives
   the same commands in at least 3 of 4 runs. This uses models, so the wording of the init task stays untested
   until it runs.
6. **In use.** After 20 merged tickets per language, the split by language in `rail stats`: a language whose
   revert or cost per merged ticket is twice the others' gets a ticket on its profile.

Not covered: languages other than the four; Windows (Rail is macOS and Linux); how good a default is beyond
"it bites" (the model test and the stats measure that).

## Assumed, not verified

- That GitHub's Ubuntu runners and Claude Code cloud machines have a C compiler for Go's `-race`, and enough
  disk for four toolchains.
- That Cargo's lock on a shared target folder makes concurrent worktree builds wait, and that sccache helps.
- That gitleaks' `git` subcommand takes `--log-opts` as written (the fixtures haven't run it).
- That each mutation tool's report can be turned into the three counts (killed, survived, timeout).
- That uv's `--no-build` and pnpm's default on lifecycle scripts behave as Part 1 says.
- Every command line and tool name marked not checked; tests 3 and 4 check them.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. `provision` and the pins in each profile, and `rail doctor`'s per-profile lines (test 1).
2. Run what the fixtures don't yet (test 3), in a cloud session with all four toolchains; fix or drop the
   lines whose planted mistake doesn't fail.
3. A language added after init: doctor's manifest-with-no-profile line and the re-run text (tests 1 and 2).
4. Workspaces and the affected-aware `verify` for pnpm (test 1); the rest of Part 2 only if the time per step
   shows the need.
5. The mutation wrappers (test 4), after `proposals/checks.md` Part 6 builds `[commands] mutation`.
6. Part 5's tool names in the seed's skills, once the guidance on tests and the surface recipes exist.
7. Init with a model and the in-use measure (tests 5 and 6), when the model tests run again.

## Decisions

**Made by the owner (2026-11-25):** Rail is Python, TypeScript, Rust and Go first, not language-neutral;
anything that blocks those four from being as useful as possible is unsupported.

**Made by the owner (2026-11-26):** Rail is not run on its own repository, so no step here adds a Rail CI for
it; a step that needs model runs builds its deterministic part first and marks its wording untested.

**Open:**

1. Rust builds across worktrees: measure first, then sccache if needed (proposed); or sccache from the start.
2. Language-specific review lines in the reviewer's brief: none at first; a repeated finding in one language
   becomes a sensor or a rule, not a review line (proposed).
3. A language added after init: `rail doctor` names it and prints what init would write, and nothing is
   written to the config (proposed); or `rail init` appends the missing profile's entries to an existing
   config, which breaks the rule that init never touches a project's own file.
4. Package managers other than uv and pnpm: their commands stay, with no fixture (proposed, as built); or
   fixtures for each; or uv and pnpm only, the rest unsupported.

## Sources

Rail, confirmed: `engine/rail/init.py`, `config.py`, `doctor.py`, `stats.py`; `engine/docs/languages.md`;
`profiles/*/profile.toml`; `seed/config.toml`; `tests/test_languages.py`; `proposals/entropy.md` Parts 2 and 4.

Research, reported: the language trend, the Go and Rust choices, and the reference stack in the research
behind this page.

Tool documentation, read on 2026-11-25: cargo-mutants, "Testing code changed in a diff",
https://mutants.rs/in-diff.html; StrykerJS, "Incremental", https://stryker-mutator.io/docs/stryker-js/incremental/;
mutmut 3.8.1 on PyPI, gremlins, "Unleash", https://gremlins.dev/next/usage/commands/unleash/, its README, and
issue go-gremlins/gremlins#301 (these three in search excerpts only, reported). Reported: "Mutation Testing for
AI-Generated Tests: The CI Gate", particula.tech, 2026-09-02 (mutmut's error on an empty pattern).
