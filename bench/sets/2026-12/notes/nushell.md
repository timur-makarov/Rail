# nushell on the bench

Shared Rust choices (env, toolchain install, fetch-only setup, target/ per copy, the test-file runner, test_package,
Rail's shape) are in `rust-common.md`; this file says what is nushell's own. Files: `nushell.toml`,
`nushell.travel.json`. Nothing here was run on a machine; the runner and the bash were tested on a synthetic workspace
with cargo 1.98 (see "What was checked").

## What I read

At the newest start `1a76df9156` (nushell-01, 2026-11-24) and the oldest `57a036c4b0` (nushell-30, 2026-07-04; the
candidate file's "oldest by PR date" nushell-26 `063caa9a65` was read too):

- `.github/workflows/ci.yml` (both ends; the job layout changed but the commands did not: `cargo fmt --all --check`,
  `cargo build --workspace --all-targets --profile ci`, `cargo test --workspace --all-targets`, `cargo test --doc`,
  std-lib tests with the built `nu`; env `NU_TEST_SKIP_DEPS_BUILD=true`), `.cargo/ci.toml` (`--cfg ci`),
  `.cargo/config.toml` (aliases, Windows/mac rustflags only), `CONTRIBUTING.md`, `rustfmt.toml`, `.gitignore`,
  `rust-toolchain.toml` at all 30 start commits.
- Root `Cargo.toml` (workspace members, `[package] nu` with `autotests = false` and one `[[test]] tests/main.rs
  harness = false`, `[[bin]] nu`, features, `[patch.crates-io] reedline = { git, branch = "main" }` at both ends),
  every `crates/*/Cargo.toml` for `harness`/`[[test]]`/`autotests`, `crates/nu-command/Cargo.toml` features.
- `crates/nu-test-support/src/harness/{mod,deps,args}.rs`, `nu-test-support-macros/src/test.rs`,
  `deprecated/macros.rs` and `fs.rs` (at the oldest starts), and kitest v0.6.0's formatter and filter
  (cptpiepmatz/kitest).
- The `tests/main.rs` of the root, nu-command, nu-protocol, nu-cli, nu-tui; the trees at both ends.
- Every candidate's hidden test file at its fix commit (macros used, feature gates, timing and permission code), the
  30 file lists, the Cargo.lock diff of nushell-15.
- Step times and the test output of one green CI run (run 45682831150, job "Linux / root").

## How nushell's tests run (the facts the commands rest on)

- **A custom test harness.** The root package and most crates (nu-command, nu-protocol, nu-cli, nu-cmd-extra,
  nu-color-config, nu-tui, nu-dap; the libs of nu-command, nu-engine, nu-config, nu-heavy-utils, nu-cli, ...) build
  their tests with `harness = false` and nu-test-support's kitest harness. nu-parser and nu-test-support keep libtest
  (`tests/*.rs` targets). kitest prints libtest's lines (`running N tests`, `test NAME ... ok|FAILED|ignored`, plus
  `timed out`, plus `group G, running N tests` headers), takes several positional filters as substrings, `--skip`,
  `--exact`. Test names are the module path without the crate plus the fn (`repl::test_hiding::hides_x`,
  `commands::table::headers::f::case_3_collapsed`), seen in the CI log. So `cargo test -p nu-command --test tests --
  commands::ls::` is exactly what CONTRIBUTING.md documents.
- **One test binary per crate.** `crates/nu-command/tests/commands/ls.rs` is module `commands::ls` of target `tests`
  of nu-command; `tests/shell/mod.rs` is module `shell` of the root package's target `tests`; nu-parser's
  `tests/test_parser.rs` is its own target `test_parser`. Every hidden test of the 30 candidates maps this way (table
  below).
- **The `nu` binary.** Tests in the root package get it from cargo (`CARGO_BIN_EXE_nu`). Elsewhere, new-style tests
  declare `#[deps(NU)]` / `#[deps(NU_PLUGIN_INC)]` / testbins, and the harness runs `cargo build --package X` itself
  before running them, unless `NU_TEST_SKIP_DEPS_BUILD` is set (CI sets it and builds the workspace first; the bench
  does not set it). Old-style tests using the deprecated `nu!(...)` / `nu_with_std!` / `nu_with_plugins!` macros
  (still in e.g. `commands/ls.rs` and `commands/run.rs` in July) spawn `target/debug/nu` and put `target/debug` on PATH
  for testbins, building nothing: `test_files` and `test_package` build `-p nu` (and `-p testbins` when that crate
  exists; it is absent at the three oldest starts, where testbins are `nu --testbin`) first when a listed file (or the
  package folder) uses those macros. `nu_with_plugins!` additionally builds the plugin crates (not polars).
- **Plugins**: the root package's `plugins::`/`plugin_persistence::` tests need the small plugin binaries; the harness
  builds them on demand. `nu_plugin_polars` is never needed by a candidate (its tests are its own crate's).
- **Features**: `cargo test -p nu-command` gets nu-command's default features (os, network, rustls-tls, sqlite), not
  the workspace-unified set CI gets through the root package (adds plugin, trash-support). No hidden test is gated on
  a feature it would lose (gates seen: sqlite, plugin and mcp in root-package files, which get the root's defaults).
- **Test environment**: tests write into `tests/fixtures/nuplayground` (gitignored) and temp dirs; locale is forced by
  the harness (`NU_TEST_LOCALE_OVERRIDE`); HTTP tests use mockito (local); `cfg(ci)` only makes three job tests
  serial. No test reads `CI`; there is no insta. kitest runs 4 x CPUs threads (16 on the machine).

## Commands and whether each is verified

| Command | Source | Status |
|---|---|---|
| `setup` | rust-common.md; pins read from the copy | unverified (never run; rustup on PATH assumed) |
| `test_files` | CONTRIBUTING.md (`--test tests -- commands::X`), Cargo.toml, nu-test-support harness | unverified (never run on nushell; runner + hook + bash tested on a synthetic workspace) |
| `test_package` | CONTRIBUTING.md (`cargo test --workspace`) narrowed per member | unverified |
| `failed` | kitest v0.6.0 `pretty.rs` + CI log lines | checked against the formatter source and the log; regex tested on sample lines |
| Rail `setup` | rust-common.md | unverified; uses `cargo metadata --offline`, not `cargo fetch --offline` (see report) |
| Rail `verify` | ci.yml lint + root jobs, made affected-aware | unverified on nushell; bash/python tested on a synthetic workspace (clean tree passes, change maps to members) |

The hook (in the embedded runner): a `mod.rs` of a folder module (`tests/shell/mod.rs`, `tests/modules/mod.rs`,
`tests/parsing/mod.rs`) has tests of its own and declares submodules full of other tests; the shared runner's module
filter `shell::` would run all of `tests/shell/**` (hundreds of process-spawning tests, some of which could be red on
the machine). The hook filters by the file's own top-level fns (`shell::NAME`). A `mod.rs` with no test
(`commands/mod.rs`, `commands/date/mod.rs`) travels and is not run, as in the shared runner.

`.` from `package_of` is the root package `nu` (root `Cargo.toml` is a package): `cargo test -p nu --tests` (its 2,800
tests: repl, shell, modules, parsing, plugins; builds nu, testbins and the small plugins). A non-member folder (a
`fuzz/` crate) prints that it has nothing to run and exits 0.

## Toolchain and pins

`rust-toolchain.toml` (`profile = "default"`, a channel, no components or targets): `1.95.0` at the July starts,
`1.96.1` (mid-Aug to early Sep), `1.97.1` (Sep-Oct), `1.98.1` at the November starts. Four toolchains for nushell
alone; setup reads the pin from each copy. MSRV is separate (`check-msrv.nu`), not used. Cargo.lock holds one git
dependency (reedline from `[patch.crates-io]`, branch main, pinned by the lock): `cargo fetch` needs git access at
setup and puts it in `$CARGO_HOME/git`.

## Sizes and times (estimates, unverified)

- **Copy**: the tree is 20.7 MB of blobs at the newest start (2,659 files) plus the copy's `.git`: about 30-40 MB idle.
- **target/**: a debug build of the nu binary plus one crate's tests, `line-tables-only`, no incremental: estimate
  4-7 GB; `-p nu --tests` with plugins and testbins somewhat more.
- **Cold build** on 4 cores: the nu binary is most of the workspace (Cargo.lock lists 1,029 packages for all platforms and plugins, rusqlite's bundled SQLite,
  rustls/ring, libgit2 only for gstat): estimate 10-15 min for `nu` + one test target. CI's "Build" step of the
  whole workspace takes 2 min 14 s, but on IncrediBuild-distributed runners with dependencies cached, so not
  comparable. `timeout_minutes = 60`.
- **Test runs** once built: one module's tests, seconds to a minute; `-p nu-command --tests` (lib + tests, several
  thousand tests) a few minutes; `-p nu --tests` (2,823 tests) 2-4 minutes. The whole workspace ran 14,205 tests in under
  2 min on CI.
- **Admission of one situation**: four cold builds, so roughly 50-80 min.
- **Rail verify** after a change in nu-command: fmt (seconds) + cold build of nu-command's tests + nu for `#[deps(NU)]`
  + run: about 15 min; `verify_timeout_secs = 3000`.

## Traps

- **Nested cargo from the test harness.** With `NU_TEST_SKIP_DEPS_BUILD` unset, a test binary runs `cargo build
  --package nu` (and testbins, plugins) while `cargo test` is still running. That is upstream's documented local path
  (cargo releases its build lock before running test binaries), inherits our env (offline, `CARGO_INCREMENTAL=0`), and
  is a no-op after the first of the ten oracle runs. Unverified on the machine.
- **Old-style `nu!` without a built nu** fails with "Could not canonicalize dummy binaries path" or a stale binary;
  handled by the content check in `test_files`/`test_package`/`verify`. If a hidden test uses a helper that calls the
  deprecated runner without the macro text in the file, the build is skipped: watch for that message in admission.
- **Feature unification**: a nu-command unit or integration test gated on `plugin` or `trash-support` would be
  compiled out under `-p nu-command` (none in the candidates).
- **Timing-sensitive tests**: nu-tui's tests assert `timeit {...} < 1sec` with sleeps (nushell-04); nu-cli's
  last_result tests use millisecond snapshots (nushell-23); par_each (nushell-18, a race). With 16 harness threads on 4
  cores these may flake in the 10-run oracle.
- **Root user**: `ls` permission tests check `is_root` and pass as root; `mkdir` umask test assumes umask 022 (root's
  default). Tests that expect "Permission denied" without such a guard would fail as root.
- **No network at test time**: nothing in the candidates' tests fetches; `http` commands' tests use mockito.
- **Generated files**: tests write under `tests/fixtures/nuplayground` (gitignored) and `target/`; nothing untracked.
- **CI's `--cfg ci`** (from `.cargo/ci.toml`) is not used: it would change rustflags for every crate (a separate
  build) and only serialises three `job` tests.
- **std-lib tests** (`crates/nu-std/tests/*.nu`, run by `nu` itself in CI) travel as data and are not run by
  `test_files`; no candidate has one.

## Hidden tests: where each goes

| id | hidden file(s) | run as |
|---|---|---|
| 01 | nu-command `tests/commands/extern_.rs`; nu-parser `tests/test_parser.rs`; `tests/repl/test_known_external.rs` | `-p nu-command --test tests -- commands::extern_::`; `-p nu-parser --test test_parser` (whole file); `-p nu --test tests -- repl::test_known_external::` |
| 02 | `tests/modules/mod.rs`, `tests/parsing/mod.rs` | `-p nu --test tests -- modules::F... parsing::F...` (own fns, hook) |
| 03 | `commands/database/query_db.rs`, `first.rs`, `stream_errors.rs` | nu-command `--test tests` with 3 module filters |
| 04 | nu-tui `tests/commands/tui.rs` | `-p nu-tui --test tests -- commands::tui::` |
| 05, 08, 12, 13, 16, 18, 22, 28, 30 | one `crates/nu-command/tests/commands/X.rs` | `-- commands::X::` (28, 30 also build nu first) |
| 06 | `tests/format_conversions/markdown.rs` | `-- format_conversions::markdown::` |
| 07, 20, 25, 26 | `tests/shell/mod.rs` | `-p nu --test tests -- shell::F...` (own fns, hook) |
| 09 | nu-protocol `tests/range.rs` | `-p nu-protocol --test tests -- range::` |
| 10 | nu-command `update.rs`; nu-protocol `test_signature.rs` | two calls |
| 11 | `tests/shell/pipeline/commands/external.rs` | `-- shell::pipeline::commands::external::` |
| 14, 21 | `tests/integration/cli.rs` | `-- integration::cli::` |
| 15 | `commands/into_datetime.rs` | `-- commands::into_datetime::` |
| 17 | `tests/integration/completions.rs` | `-- integration::completions::` |
| 19 | `columns.rs` (new), `empty.rs`, `length.rs`, `open.rs`, `commands/mod.rs` | 4 filters; mod.rs (no test) travels |
| 23 | nu-cli `tests/last_result.rs`; nu-command `commands/table/collapse_expand.rs` | two calls |
| 24 | nu-parser `tests/test_parser.rs` | whole target |
| 27 | `tests/repl/test_config_path.rs` | `-- repl::test_config_path::` |
| 29 | `commands/date/{format,from_human,humanize,to_timezone}.rs`, `date/mod.rs`, `into_datetime.rs` | 5 filters; mod.rs travels |

nu-parser's `test_parser.rs` is one big file (100-130 tests): the whole file runs, so a test in it red at the start for
an unrelated reason would sink nushell-01 and -24.

## Candidates unlikely to pass admission

- **nushell-15**: the fix turns on chrono-tz's `case-insensitive` feature, which adds six crates to Cargo.lock
  (chrono-tz-build, parse-zoneinfo, phf_codegen/phf_generator/phf_macros 0.12.1, uncased). Setup fetches the start's
  lock only and every command runs with `CARGO_NET_OFFLINE=true`, so the oracle cannot build; and an offline agent
  could never add them. Drop it, or keep it only if the agent can solve it without the feature (the hidden tests would
  still need the oracle to build: it can't).
- **nushell-18** (`par_each`, kind race): a race test may pass on the start commit some of the time (null) or fail
  some of the ten oracle runs.
- **nushell-04** (nu-tui): `timeit ... < 1sec` assertions under a 16-thread harness on 4 cores: flaky risk.
- **nushell-23** (nu-cli last_result, millisecond snapshots): flaky risk.
- **nushell-01, -24** (whole `test_parser.rs`) and **nushell-07/20/25/26** (`tests/shell/mod.rs` own fns, which spawn
  nu with deps): fine if every test in them is green on the machine; any environment-bound one sinks the oracle.

## For the admission session to try first

1. Setup on nushell-01 (newest): does `rustup toolchain install 1.98.1` land in `$RUSTUP_HOME`, does `cargo --version`
   in the copy say 1.98.1, does `cargo fetch --locked` get reedline's git checkout?
2. nushell-05 (one nu-command file, in-process tests): `test_files` null and oracle; time the cold build; watch for
   "required binary ... ensuring it is built" (the harness's nested cargo) working offline.
3. nushell-28 (old-style `nu!` in ls.rs, July pin 1.95.0): the "build nu first" path.
4. nushell-07 (tests/shell/mod.rs): the hook's own-fn filters; check the count it runs against the file's #[test]s.
5. `test_package .` once (`cargo test -p nu --tests`), for its time and red-at-start tests (plugins).
6. Rail verify with a one-line change in `crates/nu-command/src` to exercise the package part, not just fmt.
7. Decide nushell-15 (drop).

## What was checked locally

`nushell.toml` parses and loads with the bench's own loader (`bench.sets.load`, with a dummy situation appended);
`bash -n` on every command; the embedded Python compiles; the `failed` regex on kitest and libtest sample lines;
`test_files` (runner + hook) on a synthetic workspace: a `mod.rs` with its own tests and a submodule runs only its
own fns, a registering root travels, a helper module travels; `test_package` on a member and on a virtual root;
`verify` on a clean tree (passes after fmt) and with changes in two members (maps both, runs them).
