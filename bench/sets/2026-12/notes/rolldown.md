# rolldown on the bench (a reserve)

rolldown/rolldown, 41 candidates (July to November 2026). The shared Rust choices are in `rust-common.md`; this file
says what rolldown adds. Files: `rolldown.toml`, `rolldown.travel.json`.

## What I read

At the oldest start (rolldown-40, `bb19a483dd`) and the newest (rolldown-04, `3a2d3b4ef3`): `Cargo.toml`,
`.cargo/config.toml`, `rust-toolchain.toml`, `rustfmt.toml`, `.gitignore`, `.gitmodules`, `justfile`, `package.json`,
`pnpm-workspace.yaml`, `.node-version`, `AGENTS.md`, `.github/workflows/reusable-cargo-test.yml` and
`reusable-node-test.yml`, `crates/rolldown/Cargo.toml`, `crates/rolldown/tests/integration/*.rs`,
`crates/rolldown/tests/rolldown/mod.rs` and `issues/`, `crates/rolldown_testing/{Cargo.toml,build.rs,src/fixture.rs,
src/integration_test.rs}`, `packages/rolldown/{package.json,.gitignore,build-binding.ts,build.ts}`,
`packages/rolldown/tests/{package.json,vitest.config.mts,fixture.test.ts,fixtures-concurrent.test.ts}` and four of
its test files. At every one of the 41 starts: the `testing_macros` version in Cargo.lock, the toolchain pin and the
`packageManager` pin. swc-project/swc `crates/testing_macros/src/fixture.rs` (main and `a7cbde7fdb`) and its
version history. One public CI run on main (run 45621813923, commit 067bd56152): the logs of the Cargo Test (ubuntu),
Build Rolldown Native and Node Test (22) jobs. The start..fix file lists of all 41 candidates.

## Pins (read by setup from the copy, never hard-coded)

| | oldest start | newest start | over the window |
|---|---|---|---|
| rust-toolchain.toml | 1.96.1 | 1.100.0 | 1.96.1, 1.97.0, 1.97.1, 1.98.1, 1.99.0, 1.100.0 |
| packageManager | pnpm@11.9.0 | pnpm@12.4.2 | 11.9.0, 11.17.0, 11.24.0, 12.4.2 |
| .node-version | 24.12.0 | 24.22.3 | engines `^20.19.0 \|\| >=22.12.0` |
| testing_macros (Cargo.lock) | 1.0.1 | 2.0.0 | 1.0.1 (35..41), 1.0.2 (17..30, 32..34), 2.0.0, 3.0.0 (01) |

Node: the machine's v22.23.5 is used, not the pinned 24 (see risks). pnpm: the machine's 10.28 is not used; setup
installs the pinned pnpm with corepack into `COREPACK_HOME` and puts corepack's `pnpm` shim in
`$COREPACK_HOME/bin`, which every command puts first on PATH (agents can't get that PATH: they must call
`corepack pnpm`, see risks).

## How the tests are built and run

**Rust.** `just test-rust` is `cargo test --workspace --exclude rolldown_binding` (CI sets `INSTA_UPDATE=no`, checks
out the `rollup` and `test262` submodules and runs `vp install`, i.e. pnpm install, first). The core tests are ONE
cargo target, `integration` (`crates/rolldown/tests/integration/main.rs`, 2537 tests in the CI log). Its modules
`rolldown_fixture.rs`, `esbuild.rs`, `rollup.rs` carry `#[fixture("./tests/SUB/**/_config.json")]` from
swc's `testing_macros`: a proc macro that globs at COMPILE time and makes one `#[test]` per fixture folder named
`FN_` + the `_config.json` path relative to `crates/rolldown` with `/` -> `__`, other non-word characters -> `_`,
then `___` -> `__`; for example `rolldown_fixture::fixture_with_config_tests__rolldown__issues__10013__config_json`.
I computed the name of all 2380 fixtures of the newest tree this way: every one is in the CI log. `main.rs` also
pulls `tests/rolldown/mod.rs` in with `#[path]` as module `rolldown_tests`, and the `issues/NNNN/mod.rs` files
below it are `#[path]` modules too (`rolldown_tests::issues::_11447::...`). A fixture test bundles the folder
(`rolldown_testing::Fixture`), compares `artifacts.snap` with insta (snapshot path set to the fixture folder at
run time) and then **runs the output with `node`** (`_test.mjs`/`_test.cjs` or the entries; `Command::new("node")`
from PATH). So node is needed for the Rust tests; the machine has it.

To run one fixture: a libtest filter on its generated name (what `test_files` does), or `cargo run-fixture PATH`
(an alias for the `run-fixture` bin of rolldown_testing; `just t-run` adds `NEEDS_EXTENDED=false`).

**node_modules for the Rust tests.** Two fixture folders are pnpm workspace packages with npm dependencies:
`crates/rolldown/tests/rolldown/topics/npm_packages` (util-deprecate) and `warnings/eval2` (peggy). They fail
without `pnpm install`. Other fixtures resolve committed `node_modules` folders inside the fixtures. CI always
installs first, so the commands install too (from the store, offline; see setup).

**JS.** `packages/rolldown/tests` (package `rolldown-tests`) runs vitest against the built `rolldown` package:
`just test-node-rolldown` = napi build of `crates/rolldown_binding` (debug) + JS glue (`build-node`), then
`ROLLDOWN_TEST=1 vitest run` (`test:main` leaves out `watch.test.ts`/`dev-watch.test.ts`, run by `test:watcher`).
Fixture folders with `_config.ts` become tests named by their path under `fixtures/` (`fixture.test.ts` for
`sequential` ones, `fixtures-concurrent.test.ts` for the rest). Tests importing `@rolldown/test-dev-server` need
that package built (`tsc -b`).

## Commands

| Command | What | Checked against |
|---|---|---|
| `setup` | toolchain from rust-toolchain.toml; `cargo fetch --locked`; corepack installs the pinned pnpm; `pnpm install --frozen-lockfile --ignore-scripts --store-dir STORE` fills the store, `git clean -ffdx` removes what it made, an offline install proves the store, clean again | pins and justfile at both starts; **unverified**: rustup/corepack on the machine, pnpm 11/12 flags |
| `test_files` | installs node_modules from the store if missing, then the shared runner with a rolldown hook (below); JS files go to one vitest step after the cargo runs | Rust part: runner tested on a synthetic workspace, names checked against CI; **unverified**: the vitest step has never run |
| `test_package` | `.`/non-member: `cargo test -p rolldown --lib`; `rolldown_binding`: `cargo check -p rolldown_binding --tests` (CI never tests it; a napi cdylib); `rolldown`: install node_modules, `cargo test -p rolldown --tests --no-fail-fast -- --skip test262_module_code`; others: `cargo test -p NAME --tests --no-fail-fast` | justfile test-rust; **unverified**: run times |
| `package_of` | `nearest:Cargo.toml` | |
| `failed` | `^test (.+?) \.\.\. FAILED` (cargo only; JS failures only fail the exit code) | CI log line form |
| Rail `setup` | `cargo fetch --offline`, `pnpm install --offline ...` in the worktree | **unverified** |
| Rail `verify` | `cargo fmt --all --check` always; for each workspace member the branch changes, its tests as in `test_package` | justfile lint-rust/test-rust; **unverified** times |

**The rolldown hook in `test_files`.** For a listed file under `crates/rolldown/tests/{rolldown,esbuild,rollup}/`:
a `.rs` module (found by following `mod`/`#[path]` from `integration/main.rs`) runs its module path if it holds
tests (a registration `mod.rs` travels only); any other file runs the fixture of the nearest folder above it with a
`_config.json` (so a changed `artifacts.snap` or input runs its fixture), else the nearest `mod.rs` module with
tests (inputs of a hand-written test such as `issues/10183/project/main.js`), else travels only. All of these go into
ONE call: `cargo test -p rolldown --test integration --no-fail-fast -- --include-ignored NAME1 NAME2 ...`.
`--include-ignored` because of the testing_macros trap below. `crates/rolldown/tests/integration/*.rs` go through
the shared runner (module filters), data files there (the test262 snapshot, `test262_failures.json`,
`tests/package.json`) travel only. For `packages/rolldown/tests/`: `*.test.ts` files run by path, files in a
`fixtures/X/` folder run the fixture `X` (`-t '^(X|Y)$'` over the two fixture test files), other files travel only;
a test file importing `@rolldown/test-dev-server` adds its build. The vitest step fails when no test passed (a `-t`
pattern that matches nothing makes vitest skip everything and exit 0). Tested on a synthetic workspace with cargo
1.98 (fixture names, a nested fixture, an esbuild fixture, a `#[path]` module, its input file, a registration
`mod.rs`, a dot-folder fixture, data files, the JS collection with the vitest step stubbed).

## Copy size and times (estimates, unverified)

- Tree: 17,255 files, 30 MB at the newest start (23.7 MB at the oldest), plus the copy's `.git` (one commit, about
  as much again): about 60 MB per sealed copy, 2.5 GB for 41. The submodules `rollup` and `test262` are not in it
  (`git archive` leaves submodules out).
- Cache: toolchains 6 versions x ~300 MB; registry ~0.5 GB (shared with the other Rust projects); pnpm store for the
  whole workspace ~1-2 GB; corepack a few MB per pnpm version.
- A copy in use: `target/` for `-p rolldown --test integration` ~3-5 GB (oxc is large; the workspace already sets
  `debug = "line-tables-only"`); the napi binding build adds ~1-2 GB; node_modules are hard links into the store.
- Cold build of the `integration` target on 4 cores: ~8-12 min. Hidden fixtures run in seconds. The whole `rolldown`
  package (`--tests`): build plus ~3-5 min of tests (101 s for the integration target on CI's runner). JS step on a
  cold copy: binding build ~4-8 min more, `build-node` ~1 min, vitest seconds; it rebuilds the glue on every one of
  the ten oracle runs (~1 min each). Offline pnpm install into a copy: ~20-60 s.
- `timeout_minutes = 45`; Rail `verify_timeout_secs = 2400` (a cold `rolldown` package run), setup 900.

## Traps

1. **testing_macros 1.0.1 ignores every fixture under a dot folder.** Before swc's fix of 2026-07-23 (released in
   1.0.2), a fixture is `#[ignore]`d when ANY component of its absolute path starts with `.`. Starts rolldown-35..41
   lock 1.0.1. The store's default `~/.rail-bench` and every Rail worktree (`.claude/worktrees/NN`) have such a
   component, so there every fixture test is ignored: `cargo test` passes without running them. `test_files` passes
   `--include-ignored` (only the listed fixtures run, so it is safe), but `test_package`, Rail's `verify` and the
   agents' own runs would check no fixture at all. Put the store at a path with no dot folder (`BENCH_STORE`) for
   rolldown; Rail worktrees can't avoid `.claude`, so Rail's worker and verify are blind to fixtures on these seven
   starts while a plain agent in the copy root is not.
2. **New fixtures need a recompile.** The fixture list is fixed when `integration` compiles, and cargo does not know
   the glob: a new fixture folder in a copy that already built the target is not a test until a `.rs` file of the
   target changes (or `cargo run-fixture`). The bench's copies are fresh, so grading is not hit; agents are.
3. **test262** needs the submodule: `test262_module_code` fails in every copy. Skipped in `test_package` and
   `verify` (`--skip test262_module_code`); rolldown-27's hidden test262 snapshot travels but can't run.
4. **pnpm shims.** `pnpm` on the machine is 10.28; in this repo it would switch to the `packageManager` version and
   download it, which fails offline. The bench's commands use corepack's shim through PATH; an agent's shell has the
   machine's PATH, so it must use `corepack pnpm` (the commands it is shown do). The env also sets
   `npm_config_store_dir` so a plain `corepack pnpm install --offline` finds the store (if pnpm 11/12 still read it).
5. **Untracked node_modules.** `.gitignore` re-includes `packages/rolldown/tests/fixtures/**/node_modules`, and four
   of those fixtures are workspace packages, so an install makes four untracked `node_modules/rolldown-tests` links
   that show up in an agent's change (harmless: relative links; `package_of` gives `.`). `build_dirs` has
   `node_modules`, which also leaves out the fixtures' committed node_modules from saved stages; `runs.restore` puts
   them back from the sealed copy.
6. `crates/rolldown_testing/build.rs` writes the tracked `_config.schema.json` into the source tree on every build
   (same content unless the test config types change).
7. `.cargo/config.toml` `[env] WORKSPACE_DIR` is the copy's absolute path at build time; per-copy target/ keeps it
   right.
8. The napi build (`build-binding`) rewrites the tracked `packages/rolldown/src/binding.cjs`/`binding.d.cts`.
9. Node 22 instead of the pinned 24: CI's Node tests run on 20, 22 and 24, but the Rust fixture job only on 24; a
   fixture whose output needs a Node 24 feature fails here at the start and with the fix (seen at admission).

## Candidates unlikely to pass admission

- rolldown-35, 36, 37, 38, 39, 40, 41: testing_macros 1.0.1 (trap 1). Admittable with a dot-free store, but Rail's
  worktrees can't see fixtures; 36, 40, 41 are the Rust-fixture ones where that matters most.
- rolldown-05, 28 (`dev/dev-watch.test.ts`), 17, 19, 36 (`dev/dev-lazy-compile.test.ts`), 32
  (`watch/watch.test.ts`): file-watcher tests, timing-bound; 10 of 10 is doubtful, and they need the JS step.
- rolldown-15: `cli/cli-e2e.test.ts` runs the `rolldown` CLI from node_modules/.bin and checks colored diagnostics;
  `CI=true` and no TTY may change colors (the fix adds `supports-color`).
- rolldown-37: hidden `packages/rolldown/tests/package.json` adds a `link:` dependency while the fix's
  `pnpm-lock.yaml` is source: `--frozen-lockfile` fails whenever the two disagree (null fails for that reason, and
  an agent must edit the lockfile by hand offline).
- All JS-only situations (04, 05, 09, 15, 16, 17, 19, 23, 24, 30, 32, 33, 35, 37, 38, 39) depend on the unverified
  vitest step; the Rust-fixture ones (01, 02, 03, 06, 07, 08, 10, 11, 12, 13, 14, 20, 22, 25, 26, 29, 31, 34) are the
  safe core; 18, 21, 27 mix both.

## For the admission session to try first

1. Setup on rolldown-01 (newest pins): does `corepack install` + `corepack enable --install-directory` work with the
   machine's node 22, does pnpm 12.4.2 accept `--ignore-scripts --store-dir`, does the offline install pass?
2. `test_files` on rolldown-03 (6 fixture files): the integration filter names, `--include-ignored`, cold build time.
3. `test_package crates/rolldown` on the start commit: green with `--skip test262_module_code` and node_modules
   installed? (If npm_packages/eval2 still fail, the install did not reach their workspace packages.)
4. One JS situation (rolldown-24, `utils/transform.test.ts`): the napi build, `build-node`, vitest by file.
5. Rail `verify` with a one-line change in `crates/rolldown/src`: time on 4 cores (must be under ~15 min plus build).
6. Decide the store path (no dot folder) before admitting 35..41.
