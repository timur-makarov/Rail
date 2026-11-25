# turso on the bench

Shared Rust choices (literal CARGO_HOME/RUSTUP_HOME, toolchain install, fetch-only setup, target/ per copy, the
test-file runner, test_package, Rail's shape) are in `rust-common.md`; this file says what is turso's own. Files:
`turso.toml`, `turso.travel.json`. Nothing here was run on a machine. The runner and the turso hook were tested on a
synthetic workspace with `cargo test` (cargo 1.98); the TOML parses and loads with `bench.sets.load`; every command
passes `bash -n`; `failed` was tried on sample nextest and sqltest lines.

## What I read

At the newest start `2cacdb46a2` (turso-01, 2026-11-24), the oldest `8ef452a3c9` (turso-63, 2026-07-07) and
`78f35283c3` (turso-60, the last start with the old sqltest layout):

- `.github/workflows/rust.yml` (nextest with `--workspace --all-features --locked --no-fail-fast` and the filter
  `not binary(fuzz_tests) and not binary(pending_byte_tests)`; the conn-raw-api job
  `cargo nextest run -p turso_core --features conn_raw_api`; `cargo fmt --check`; clippy), `sqltest.yml`
  (sqltest-rust job), `c-compat.yml` (the C API test), `.config/nextest.toml` (profile `ci`: retries = 2).
- `rust-toolchain.toml` at all 63 start commits (one blob: channel 1.88, clippy, rustfmt, rust-analyzer).
- Root `Cargo.toml` (members), `Cargo.lock` at the newest start (848 packages, no git sources; pg_query 18.1.0 runs
  bindgen; rusqlite `bundled`; aws-lc-sys 0.46 through rustls), `tests/Cargo.toml` (core_tester: `[[test]]
  integration_tests = integration/mod.rs`, default features made for testing), `core/Cargo.toml` features.
- `sqlite/conformance/Makefile` (`run-one: sqltest run $(FILE)`, cwd sqlite/conformance), `postgres/conformance/Makefile`
  at several commits (backend `pg` -> `tursopg` -> `tursopg-embedded`), `testing/sqltests/Makefile@78f35283c3`
  (`cargo run --bin test-runner`, cwd testing/sqltests), `testing/sqltest/docs/{cli-usage,snapshot-testing}.md`,
  `testing/sqltest/src/output/pretty.rs` (line forms), `bindings/c/tests/Makefile`.
- The trees at both ends and at 78f35283c3; every candidate's hidden files at its fix commit (first lines for
  `#![cfg(shuttle)]`, test attributes, module declarations).
- One public CI log (job 139504363042, rust.yml, 2026-11-25) for nextest's own lines.
- nextest docs (`selecting.md`, `running.md`, `pre-built-binaries.md`) and cargo's source for path-package hashing and
  mtime freshness (see rust-common.md section 3).

## Commands and whether each is verified

Every command is marked `# unverified` in the TOML: none was run against turso. What each rests on:

| Command | Source | Status |
|---|---|---|
| `setup` | rust-common.md; rust-toolchain.toml at all starts; Cargo.lock; nextest install docs | unverified: never run; assumes rustup on PATH, apt as root on Ubuntu, aws-lc-sys building without cmake |
| `test_files` | rust.yml (nextest, conn-raw-api), tests/Cargo.toml, the two sqltest Makefiles, sqltest docs, c-compat.yml | unverified: never run; runner logic tested on a synthetic workspace with `cargo test` |
| `test_package` | rust.yml (the same nextest calls and filter) | unverified: never run; times estimated |
| `package_of` | `nearest:Cargo.toml`; members read from Cargo.toml | unverified (loader rule only) |
| `failed` | CI log lines and pretty.rs | tested on sample lines only |
| `env` | rust-common.md | unverified |
| Rail `setup` | rust-common.md section 6 | unverified: never run |
| Rail `verify` | rust.yml (`cargo fmt --check`, nextest), sqltest.yml | unverified on turso; its bash tested on the synthetic workspace with nextest and fmt replaced by echo |

What `test_files` does with each kind of hidden file:

- `.rs` in a workspace crate: `cargo nextest run -p PKG --test T|--lib|--bin B --no-fail-fast --no-tests=fail -- FILTERS
  [--skip ...]`. turso_core gets `--features conn_raw_api` (as CI's job); everything else default features (core_tester's
  defaults are its test set; `--all-features` would turn on `checksum`, which breaks the integrity tests).
- `.sqltest` (sqlite/conformance, testing/shared-sqltests, testing/sqltests): grouped per runner and run once with
  `cargo run --manifest-path RUNNER/Cargo.toml --bin sqltest|test-runner -- run RELS --backend rust --snapshot-mode no`
  from the Makefile's cwd. Counted by `(\d+) passed`; exit 1 on any failure.
- `.snap` under `snapshots/`: runs the `.sqltest` it belongs to (`STEM.sqltest` in the parent folder, else every
  `.sqltest` there). `--snapshot-mode no` makes a missing or different snapshot fail without writing.
- `postgres/conformance/*.sqltest`: the Makefile's `run-one-embedded` recipe, else `run-one`, read at run time, with
  `cargo build --package tursopg` first when the recipe names the server binary.
- `bindings/c/tests/*.c`: `cargo build -p turso_sqlite3 --features capi`, then the Makefile build and `./sqlite3-tests`.
- Travel only, with a `bench:` line: files starting `#![cfg(shuttle)]`/`#![cfg(loom)]`, Tcl `.test`/`.tcl`, Python,
  JS, Go, Java, C# and other binding tests.

## Toolchain and pins

| | oldest start (turso-63, 8ef452a3c9) | newest start (turso-01, 2cacdb46a2) |
|---|---|---|
| rust-toolchain.toml | 1.88, clippy, rustfmt, rust-analyzer | the same blob |
| sqltest runner | `testing/sqltests`, bin `test-runner` (turso-60..63) | `testing/sqltest`, bin `sqltest` |
| postgres crates | none (turso-63..60) | `postgres/*`, backend `tursopg-embedded` |
| cargo-nextest | not pinned by the repo (CI takes latest via taiki-e) | the same; setup installs the latest 0.9 |

One toolchain for the whole set: install it once in the shared RUSTUP_HOME. rust-analyzer is not installed (not needed
to build or test).

## Sizes and times (estimates, unverified)

- Copy: 44 MB of source at the oldest start, 87 MB at the newest, plus `.git`: about 70-130 MB idle per copy.
- target/ after a test run: 2-5 GB per copy (turso_core is built twice when Rust tests and sqltests run together:
  conn_raw_api on, then the runner's own feature set). Grade and admission copies are temp folders and go away; Rail
  run copies keep a target/ per ticket worktree, so plan disk per concurrent ticket.
- Registry (shared CARGO_HOME): about 1 GB after `cargo fetch` of 848 packages.
- Cold build plus run on 4 cores: turso_core unit tests 6-10 min build, 1-3 min run; core_tester 10-15 min build,
  2-5 min run; sqltest runner 4-8 min build (pg_query and bindgen), seconds per file. A null-plus-oracle admission of
  one situation is two cold builds: 15-40 min. `timeout_minutes = 60` covers the worst (turso_core twice plus
  core_tester); `verify_timeout_secs = 3000` likewise.
- `CARGO_INCREMENTAL=0` inside the test commands: no incremental cache is written for a copy that is built once.

## Traps

- **libclang.** pg_query's build script runs bindgen; without libclang the sqltest runner and the postgres crates do
  not build. Setup installs `libclang-dev` with apt when `ldconfig -p` shows none; on a machine without apt or root
  this must be baked into the image.
- **aws-lc-sys** (rustls in the `turso` crate) may need cmake and a C compiler; unverified.
- **io_uring.** Tests that use io_uring fail when the container's seccomp profile blocks it. Check on the first run
  whether any hidden test reaches io_uring with the bench's features (default plus conn_raw_api).
- **No retries.** CI's `ci` nextest profile retries twice and hides flakes; the bench's default profile does not.
  Leaving it so is deliberate (a pass must be a pass), but timing tests will flake (below).
- **Shared target dir is wrong, not slow.** Cargo hashes path packages by their workspace-relative path, so two copies
  sharing CARGO_TARGET_DIR reuse each other's compiled workspace crates by mtime. Kept per copy (rust-common.md).
- **The old runner.** turso-60..63 start before `testing/sqltest`; the hook reads which runner exists at the start
  commit. That its summary and `[FAIL]` lines match the new runner's (`(\d+) passed`, `failed`) is assumed, not
  checked: try turso-60 early.
- **pg backend name.** It changed three times in the window; the hook reads the Makefile at run time instead of
  naming a backend.
- **Snapshots.** `.snap` files travel and are hidden tests; a change that makes the runner write snapshots would hide a
  fault, hence `--snapshot-mode no`. Snapshot tests only run on the rust backend.
- **Ignored and cfg-gated tests.** A hidden file whose tests are all `#[ignore]` or gated by `#![cfg(shuttle)]` runs
  zero tests; the runner then fails the run ("no test ran") or skips with a message. Such situations cannot be admitted.
- **rustup on PATH.** `RUSTUP_AUTO_INSTALL=0` stops rustup from installing a toolchain mid-test; setup must install it.

## Hidden tests: coverage of the travel lists

`turso.travel.json` was checked against all 63 candidates: no hidden test is lost. It adds `.sqltest` files to
turso-03, 08, 11, 14, 15, 17, 26, 27, 28, 29, 31, 41, 48, 50 and 56; `upstream/all.test` (Tcl, travels, not run) to
turso-03 and turso-31; `testing/cli_tests/extensions.py` (Python, travels, not run) to turso-08. `never` keeps
manifests, the lock file, build scripts and the sqltest runner's own source out of the hidden set.

## Candidates unlikely to pass admission

- **turso-12**: its only hidden test is a Python binding test; nothing runs, so `test_files` exits 2. Drop it.
- **turso-55**: its shuttle test does not run (needs `RUSTFLAGS=--cfg shuttle`); `core/mvcc/database/tests.rs` still
  runs, so admission depends on whether that file alone tells null from oracle.
- **turso-39**: the fix is in the sqltest runner's own snapshot code, which `never` keeps out of the hidden set; the
  snapshot files alone may not fail at null.
- **turso-10**: the C API test (Makefile build, LD_LIBRARY_PATH) was never run in this setup.
- **turso-27, turso-50**: pg `.sqltest` files on the tursopg server backend; the extra server build and the Makefile
  recipe are the least certain path.
- **Flaky by timing**: turso-09 (query_timeout), turso-63 (WAL backfill race), turso-01 (a race), turso-05 (five
  files, including unreliable-IO and crash tests), turso-23, 49, 52 (the whole `mvcc.rs` module). Expect admission to
  need repeats; a flip between runs should reject them.
- **turso-60..63**: the old runner layout, read but not run.

## For the admission session to try first

1. Setup on turso-01: toolchain 1.88 lands in the shared RUSTUP_HOME, libclang is found or installed, `cargo nextest
   --version` works, `cargo fetch --locked` finishes. Note the time and the registry size.
2. turso-01 null and oracle: the nextest call line, the `Summary` count, `failed` names on the null run.
3. turso-11: a `.sqltest` with snapshots; check the runner builds (bindgen), the `N passed` count, and that a missing
   snapshot fails under `--snapshot-mode no`.
4. turso-60: the old `test-runner` layout.
5. turso-04: a `mod.rs` plus a module file, to see the child-module skips on real nextest output.
6. `test_package .` (falls back to turso_core) and `test_package tests` (core_tester with CI's filter): times.
7. Rail verify on a copy with a one-line change in `core/`: fmt check, then turso_core's unit tests only.
8. Then turso-12 (expect exit 2), turso-27 (pg backend), turso-10 (C test).
