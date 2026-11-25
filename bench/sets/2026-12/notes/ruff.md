# ruff (astral-sh/ruff, a reserve): bench settings

Files: `ruff.toml` (project, commands, Rail commands), `ruff.travel.json`. Shared Rust choices (cache paths, toolchain,
no build in setup, target/ per copy, the test-file runner) are in `rust-common.md`; this file says where ruff departs
or adds. Nothing was built or run against ruff; every command is marked `unverified` in the TOML. The test-file runner
(shared runner plus the ruff hook) and `test_package`/`verify` were run against a synthetic workspace shaped like ruff
(linter lib with insta-style snapshots and fixtures, an `mdtest` `harness = false` target, the formatter's `fixtures`
target with `required-features`, the CLI's `tests/cli/main.rs`), with local cargo 1.98; the file loads with the bench's
own `sets.load` (with a dummy situation) and every command passes `bash -n`.

## What I read

At the newest start (ruff-01, `eb4e0b24cb`, 2026-11) and the oldest (ruff-35, `d297b16535`, 2026-07):
`rust-toolchain.toml` (and at all 36 starts), `Cargo.toml` (workspace, profiles), `.gitignore`, `.cargo/config.toml`,
`.config/nextest.toml`, `.github/workflows/ci.yaml` (jobs cargo-fmt, cargo-clippy, cargo-test-linux),
`CONTRIBUTING.md` (testing, mdtest section), `crates/ruff_mdtest/{Cargo.toml,tests/mdtest.rs,src/lib.rs}`,
`crates/mdtest/src/lib.rs` (env vars), `crates/ruff_python_formatter/{Cargo.toml,tests/fixtures.rs}`,
`crates/ruff_linter/Cargo.toml`, `crates/ruff/Cargo.toml`, `crates/ruff_server/{Cargo.toml,src/format.rs}`,
`crates/ruff_dev/{Cargo.toml,src/generate_json_schema.rs}`, `crates/ty_python_semantic/tests/mdtest.rs`, the full
file trees at both commits, the `start..fix` file lists of all 36 candidates and the mod.rs patches of ruff-14/16/18/25.
Outside ruff: datatest-stable (`derive_test_name` = `{fn}::{path}`) and libtest-mimic's printer (pads names).

## Toolchain and pins

`rust-toolchain.toml` holds only `channel`, no components or targets. It moves within the window: 1.97.0 (ruff-35,
36), 1.97.1 (ruff-31..34), 1.98.0 (ruff-23..30), 1.99.0 (ruff-07..22), 1.100.0 (ruff-01..06). Five toolchains, about
1.5 GB in `$RUSTUP_HOME`. Workspace `rust-version` 1.95 (old) and 1.98 (new); edition 2024. `[profile.dev]` gains
`opt-level = 1` and `debug = "line-tables-only"` between the two starts (old: defaults, with `opt-level = 3` for insta,
similar and salsa), so newer starts compile somewhat slower and run tests faster. No git dependencies in Cargo.lock.
`fuzz/` is its own workspace (not a member). No Python or Node is needed for any Rust test the candidates touch
(CI uses uv only to get `cargo-insta`/`cargo-nextest` and for scripts).

## Commands

| Command | What | Status |
|---|---|---|
| `setup` | rust-common.md setup: toolchain from the pin, `cargo fetch --locked`, offline metadata check | unverified (rustup on PATH, install) |
| `test_files` | shared runner + ruff hook (below), `--all-features` for ruff_linter | unverified; synthetic-workspace tested |
| `test_package` | `cargo test -p NAME --tests --no-fail-fast`; ruff_linter runs with ruff_mdtest and `--all-features`; `.` and non-members fall back to that linter pair | unverified; synthetic-workspace tested |
| `package_of` | `nearest:Cargo.toml` | from the layout (every crate is `crates/NAME/Cargo.toml`) |
| `failed` | `^test (.+?)\s+\.\.\. FAILED` | checked with python on libtest and padded libtest-mimic lines |
| Rail `setup` | `cargo metadata --offline` (all crates resolve offline) | unverified |
| Rail `verify` | `cargo fmt --all --check` + tests of the crates changed against `$RAIL_BASE` | unverified; package part synthetic-tested (fmt skipped locally) |

### How the hidden tests run

The CI runs `cargo insta test --all-features --unreferenced reject --test-runner nextest` (ci.yaml, both starts). The
bench uses plain `cargo test` (no cargo-insta, no nextest on the machine) with `INSTA_UPDATE=no` and `CI=true`, which
makes a mismatched *or missing* snapshot fail the assertion and write nothing (no `.snap.new`); `INSTA_FORCE_PASS` is
unset. `MDTEST_UPDATE_SNAPSHOTS=0` keeps mdtest from rewriting inline `snapshot` blocks (crates/mdtest/src/lib.rs
reads it), `MDTEST_TEST_FILTER`, `MDTEST_EXTERNAL` (CI sets it: ty mdtests that download packages) and
`RUFF_UPDATE_SCHEMA` are unset. The ruff hook maps each listed file:

- `crates/ruff_linter/src/rules/PLUGIN/snapshots/ruff_linter__rules__PLUGIN__tests__NAME.snap` -> `cargo test -p
  ruff_linter --lib --all-features -- rules::PLUGIN::tests::`. Generally: insta names a snapshot
  `CRATE__MODULE__PATH__NAME`; the hook walks the segments after the crate (or test target) name while they are folders
  or `.rs` files under the crate root, then adds `tests` (the inline `mod tests`), so `cli__lint__x.snap` in
  `crates/ruff/tests/cli/snapshots/` -> `-p ruff --test cli -- lint::`. The snapshot's explicit name (`format!("{}_{}",
  rule.name(), path)`) can't be turned into one `#[test_case]` function, so the whole test module of the plugin runs
  (a few hundred cases at most, seconds once built).
- `crates/ruff_linter/resources/mdtest/REL.md` -> `cargo test -p ruff_mdtest --test mdtest -- mdtest::REL`
  (datatest-stable names tests `mdtest::<path under the root>`; the `mdtest::` prefix keeps `ruff/x.md` from matching
  `flake8-ruff/x.md`). Same for ty: `crates/ty_python_semantic/resources/mdtest/REL.md` -> `-p ty_python_semantic
  --test mdtest -- mdtest::REL`.
- `crates/ruff_python_formatter/tests/snapshots/format@...snap` / `black_compatibility@...snap` (datatest names, no
  module prefix) -> the crate's test target that defines `fn format(` / `fn black_compatibility(`, filter `format::` /
  `black_compatibility::` (the target `fixtures` needs the `serde` feature: the runner adds `--features serde` from
  `required-features`). Parser `valid_syntax@`/`invalid_syntax@` snapshots work the same way.
- A linter fixture `crates/ruff_linter/resources/test/fixtures/PLUGIN/...` runs `rules::PLUGIN::` unless a listed
  snapshot already runs that plugin; a formatter fixture under `fixtures/ruff|black/` runs `format::` /
  `black_compatibility::`. So a fixture that gains a case whose snapshot does not change (an "absence of diagnostic"
  test) still runs its plugin's tests.
- `.rs` test files and a hidden `rules/PLUGIN/mod.rs` go through the shared runner (`mod.rs` -> `rules::PLUGIN::`).
- `--all-features` only for ruff_linter (CI's flag; its `test-rules` feature gates tests). Not for others:
  ruff_server's `test-uv` feature turns on tests that run `uv` (network).

### test_package and the `.` fallback

`cargo metadata` turns the folder into the crate name. ruff_linter runs together with ruff_mdtest (`-p ruff_linter -p
ruff_mdtest --all-features --tests`): the linter's behaviour tests are split between its own snapshot tests and the
mdtests, and a rule change can break either. `.` (a changed root file: `ruff.schema.json` in ruff-22, `hawk.toml` in
ruff-13, `docs/*.md` in ruff-36, Cargo.lock) and folders that are not workspace members (`fuzz/`) fall back to that
same linter pair: bounded (about 10 min cold) and the core of the project. Not covered: the `ruff.schema.json`
up-to-date check is a test in `ruff_dev`, which depends on ty and would roughly double the build; an agent that changes
an option without regenerating the schema is not caught by the grade.

### Rail

`setup` only checks that the worktree's crates resolve offline (toolchain and registry live in the shared cache; no
`node_modules` or venv needed). It departs from rust-common.md 6 (`cargo fetch --offline`): `cargo metadata --offline`
is the check I am sure fails on a missing crate. `verify`: `cargo fmt --all --check` (CI's own job; about 10 s; passes
on main), then the crates holding a changed path (`git diff --name-only $RAIL_BASE` plus untracked), with ruff_mdtest
added when ruff_linter changes, ruff_linter/ruff_mdtest with `--all-features` and the rest without. Left out for time:
clippy (CI: `cargo clippy --workspace --all-targets --all-features`, `-D warnings`; a second full build), doc tests,
the schema check. `verify_timeout_secs = 2400`: a cold linter build plus its tests is about 10 to 14 min on 4 cores,
more if the CLI crate also changed.

## Copy size and times (estimates, not measured)

- Source tree at the newest start: 97 MB (11 342 files, GitHub tree sizes); a sealed copy with its one-commit `.git`
  about 150 MB. Setup writes nothing into the copy (registry and toolchains in the shared cache, ~0.6 GB of crates).
- Cold build of `ruff_linter`'s lib tests on 4 cores: about 6 to 10 min (about 350 dependency crates, ruff_linter is
  large); adding `ruff_mdtest` about 1 to 2 min more (ruff_linter is built twice: with `--all-features` for its own
  tests and as ruff_mdtest's dependency). The CLI tests (`-p ruff --test cli`) build the `ruff` binary: about 8 to 12
  min cold. ruff-36 builds ruff, ruff_mdtest and ruff_server: about 15 min. After the build, a plugin's snapshot
  tests and a few mdtests run in seconds; ten oracle runs add little.
- A debug target/ (line-tables-only): about 3 to 5 GB for the linter pair, 5 to 7 GB with the CLI or server.
- Admission of one situation (four cold builds): about 30 to 50 min.

## Traps

- **Fixtures must travel.** Most candidates list only the `.snap`; the fixture `.py` it is made from is in `fix.diff`
  as "source". The oracle would pass and every agent would fail (it cannot add the unseen fixture cases the snapshot
  shows). `ruff.travel.json` makes `crates/*/resources/test/**` travel; recomputed, 22 of 36 situations gain a fixture
  (and ruff-14/16/18/25 a mod.rs).
- **mod.rs.** `rules/PLUGIN/mod.rs` holds both the `#[test_case(Rule::X, Path::new("X.py"))]` registrations and
  `mod`/`pub(crate) mod` declarations. What the bench does with a hidden file: `sealed.build` leaves it out of
  `fix.diff` entirely and `put_hidden` copies the fix's whole file over the copy in the null run, the oracle and every
  grade; the grade first sets aside the arm's own version (`clashing`, same path). So: (a) a new fixture's test exists
  only through mod.rs (ruff-18, ruff-25): mod.rs must travel or the hidden snapshot has no test and nothing can pass;
  (b) whatever non-test change the fix made in mod.rs is handed to every arm and to the null run, and is never applied
  as source (ruff-16: `mod helpers` -> `pub(crate) mod helpers`, harmless but free); if the hidden mod.rs declared a new
  module the fix adds (`mod new_thing;`), the null run fails to compile and the agent must create a file of exactly that
  name; (c) the agent's own edits of that mod.rs (its own `#[test_case]` lines, a new `mod`, a changed settings default
  in a test) are discarded at grading, which breaks the build if the agent's code depends on them. Recommendation:
  keep mod.rs in `hidden_tests` only when the fix changes it inside `mod tests` (ruff-14 comment-only, ruff-18,
  ruff-25); drop it for ruff-16. `rules/PLUGIN/rules/**` never travels (`never`).
- **Snapshots pin upstream's exact output**: messages, fix titles, fix edits, formatter output. Situations where the
  fix's text is a choice (ruff-05, -08 parenthesized-range edits; ruff-12 the unsafe-fix marker; ruff-13 the BOM
  diff rendering; ruff-24 quote flipping; ruff-32 hyperlink padding) may be unfair, not inadmissible.
- **Agents' `.snap.new` files**: the env leaves insta at its default for agents (so they get `.snap.new` to inspect);
  `.gitignore` ignores only `*.rs.pending-snap`, so a `.snap.new` an agent leaves becomes part of its diff. Harmless to
  the grade (never read with `INSTA_UPDATE=no`), but noise; `INSTA_UPDATE=no` in env would stop it at the cost of the
  agents' workflow.
- The formatter's `black_compatibility` test deletes its snapshot file when Ruff and Black agree (fixtures.rs): a
  formatter change can show up as a deleted tracked `.snap` in an agent's diff.
- `CARGO_MANIFEST_DIR` is baked into test binaries (`test_resource_path`, insta paths, mdtest's `env!`); fine with a
  per-copy target/ (rust-common.md 3).
- Network at test time: none with the chosen features. `MDTEST_EXTERNAL` (CI sets it) and ruff_server's `test-uv` need
  the network; both are kept off.
- Tests red at the start: none expected (main is green in CI on 16-core runners, `nextest` with a 60 s per-test
  stop-gap); no known flaky suite among the touched crates, but nextest's 60 s terminate-after hints that some tests can
  hang; plain `cargo test` has no per-test timeout, so a hang ends only at `timeout_minutes = 45`.

## Candidates unlikely to pass admission (or to be fair)

- ruff-16: hidden refurb/mod.rs carries a source change; drop it from `hidden_tests` (see mod.rs above), else admitted
  with the change given away.
- ruff-09: `ruff check --verbose` with a closed stderr pipe; how a closed pipe behaves (SIGPIPE vs EPIPE) under the
  bench's runner may differ from CI; the oracle's ten runs may be flaky.
- ruff-36: three crates (CLI, mdtest, in-process LSP server) and nine changed files; heavy build (about 15 min cold) and
  the server e2e test may be timing-sensitive.
- ruff-13 and ruff-32: inline CLI snapshots pin exact rendering (BOM line, hyperlink escape padding); `CI=true` and the
  bench's environment (no TTY) should match CI, but check the oracle first.
- ruff-22: changes `ruff.schema.json` (package `.`), which only `ruff_dev`'s schema test checks, and that is not run.

## For the admission session to try first

1. Check `command -v rustup` and that `cargo --version` inside a ruff copy prints the pinned version with the env's
   `RUSTUP_HOME`; run `setup` on ruff-01 (1.100.0) and ruff-35 (1.97.0).
2. Admit ruff-01 (one snapshot + fixture) with `hidden_tests` recomputed from `ruff.travel.json`; read the runner's
   `bench:` lines: one call `-p ruff_linter --lib --all-features -- rules::fastapi::tests::`, the null run failing on
   the snapshot assertion, and no `.snap.new` in the copy.
3. Admit ruff-35 (one mdtest file): `-p ruff_mdtest --test mdtest -- mdtest::ruff/logging-eager-conversion.md`;
   confirm the libtest-mimic `FAILED` line is caught by `failed` (names are padded).
4. Admit ruff-18 (new fixture registered in mod.rs) and ruff-24 (formatter `format::` filter, `--features serde`).
5. Run Rail `verify` once with a one-line change in `crates/ruff_linter/src/` committed on a branch, to time the cold
   package part and see that ruff_linter + ruff_mdtest pass at the start commit.
6. Time one cold `test_package crates/ruff_linter` to replace the estimates above.
