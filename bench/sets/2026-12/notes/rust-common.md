# Rust projects on the bench: what the four project files share

turso, nushell, ruff and rolldown share the choices below. Each `PROJECT.md` says only where it departs from them.
`rust-test-files.py` is the shared test-file runner that each `PROJECT.toml` embeds in `test_files` (with a
project hook where needed). Keep the embedded copies and this file in step when one is fixed.

## 1. Where cargo, rustup and the registry live

**The trap.** `[commands] env` values are literal strings: `sealed.project_env` does `env.update(...)` with no
expansion, so `CARGO_HOME = "$BENCH_CACHE/cargo"` would make cargo use a folder literally named `$BENCH_CACHE`
inside the copy. Bench commands could `export CARGO_HOME="$BENCH_CACHE/cargo"` first, but an agent's shell only gets
the env table, and the driver gives each agent its own `HOME`. With no `CARGO_HOME`/`RUSTUP_HOME` set, an agent's
`cargo` (a rustup proxy) would look in `$HOME/.rustup` and `$HOME/.cargo` of the run's empty HOME: no toolchain, no
registry, and offline it can't fetch either.

**The choice.** The env sets absolute paths, the same for the four Rust projects:

```toml
CARGO_HOME = "/srv/rail-bench/cache/rust/cargo"
RUSTUP_HOME = "/srv/rail-bench/cache/rust/rustup"
```

That is `STORE/cache/rust/` when the store is `/srv/rail-bench` (BENCH_STORE, as the cloud prompts set it) and the bench runs as root (the brief's
machine). One folder for all four projects, not one per project, because both are content-addressed (a toolchain by
its version, a crate by name and version) and the four share many crates and maybe toolchains, which saves disk.
If the store is elsewhere the paths still work; they just sit outside the store.

**Better, a one-line bench change** (recommended): in `sealed.project_env`, expand `$BENCH_CACHE` in env values
(`v.replace("$BENCH_CACHE", cache)`), then write `CARGO_HOME = "$BENCH_CACHE/cargo"` per project. Every language
with a cache dir needs this (GOMODCACHE, UV_CACHE_DIR, pnpm store), so it is worth doing once.

The rest of the env, per project:

```toml
CARGO_NET_OFFLINE = "true"            # agents and Rail run offline; setup overrides it for its fetch
RUSTUP_AUTO_INSTALL = "0"             # rustup >= 1.28.1: never try to download a toolchain at command time
CARGO_PROFILE_DEV_DEBUG = "line-tables-only"   # target/ about half the size, faster links; backtraces keep lines
CARGO_TERM_COLOR = "never"
```

`CARGO_PROFILE_DEV_DEBUG` is set for everyone (agents, Rail, bench) so their builds agree; changing debug info does
not change what a program does. `CARGO_INCREMENTAL=0` is exported inside `test_files`/`test_package` only (see 3).

## 2. The toolchain pin

All four projects pin a toolchain in `rust-toolchain.toml`, and three of the pins move inside the window (oldest ->
newest start commit): turso `1.88` -> `1.88`; nushell `1.95.0` -> `1.98.1`; ruff `1.97.0` -> `1.100.0`; rolldown
`1.96.1` -> `1.100.0`. None is the machine's `1.97.0` except some ruff starts. So the toolchain is installed per pin,
and up to a dozen versions may pile up in `$RUSTUP_HOME` (about 300 MB each with `--profile minimal` plus rustfmt and
clippy; `rustup toolchain uninstall` old ones when disk is short). Setup reads the pin from the copy, not from this
file, so a pin that moves between start commits is handled:

```bash
command -v rustup >/dev/null || { echo "bench: rustup is not on PATH"; exit 1; }
mkdir -p "$CARGO_HOME" "$RUSTUP_HOME"
read -r tc comps tgts < <(python3 - <<'PY'
import os, tomllib
f = next((n for n in ("rust-toolchain.toml", "rust-toolchain") if os.path.exists(n)), None)
d = {}
if f:
    t = open(f).read()
    try: d = tomllib.loads(t).get("toolchain", {})
    except tomllib.TOMLDecodeError: d = {"channel": t.strip()}
print(d.get("channel", "stable"), ",".join(d.get("components", [])) or "-", ",".join(d.get("targets", [])) or "-")
PY
)
args=(--profile minimal --component rustfmt,clippy)
[ "$comps" != - ] && args+=(--component "$comps")
[ "$tgts" != - ] && args+=(--target "$tgts")
rustup toolchain install "$tc" "${args[@]}"
rustup default >/dev/null 2>&1 || rustup default "$tc"
```

Inside the copy, `rust-toolchain.toml` picks the toolchain for every later command, offline, as long as it is
installed in `$RUSTUP_HOME`; the listed components and targets are installed too, so rustup never wants the network.
**Unverified on the machine:** that `rustup` is on the bench's PATH (the brief says "likely"). If it is not, install it
once by hand, `rustup-init -y --no-modify-path --default-toolchain none` with `RUSTUP_HOME`/`CARGO_HOME` as above,
and put `$CARGO_HOME/bin` on the PATH the bench is started with (a child's PATH comes from the bench's own).
`cargo --version` must then name the pinned version inside the copy; setup prints it.

## 3. Fetch, and where builds go

Setup fetches, it does not build:

```bash
CARGO_NET_OFFLINE=false cargo fetch --locked
cargo metadata --offline --format-version 1 >/dev/null   # every dependency resolves offline
```

`--locked`: a Cargo.lock out of step with the manifests fails setup instead of rewriting Cargo.lock in the copy (a
rewritten Cargo.lock would be in every agent's diff). `cargo fetch` with no `--target` fetches the crates of every
platform, which is what an offline build on any platform needs.

**target/ stays per copy, inside the copy (cargo's default), and setup does not build.** Checked against cargo's source
(rust-lang/cargo master, Nov 2026):

- A workspace member's artifact names do not depend on where the workspace is: `SourceId::stable_hash` hashes a
  path package by its path *relative to the workspace root* (`src/workspace/source_id.rs`), and
  `compilation_files.rs` builds the metadata hash from it. Freshness of a path package is by mtime: stale only when a
  source file is newer than the dep-info file (`fingerprint/mod.rs`, `CheckDepInfo`).
- Env vars that cargo itself sets for rustc, `CARGO_MANIFEST_DIR` among them, are left out of the fingerprint
  (`fingerprint/dep_info.rs`, `translate_dep_info`: "we won't recompile" when they change).

So with **one shared `CARGO_TARGET_DIR` under the cache**, copy B reuses whatever copy A last compiled for a
workspace crate whenever B's files are older than A's build, and they always are: the copy's files carry the start
commit's time (`git archive` sets it, `tar` and `copytree` keep it). Admission runs the null check, then the oracle
with the fix; a later grade of an agent's patch that leaves a fixed file alone would be compiled with the *fix's*
version of that file and pass. Different start commits of one project would mix too. It is wrong results, not just a
lock; no setting of `CARGO_INCREMENTAL` changes it. And test binaries keep the `CARGO_MANIFEST_DIR` of the copy that
built them (insta snapshot paths, ruff's fixture paths), a folder that is later deleted.

For the same reason **setup must not build into the sealed copy**: the copy is built at `ID.building/copy` and renamed,
and every use is a `copytree` elsewhere; a prebuilt target/ would be "fresh" in each copy while its test binaries
point at `ID.building/copy/...`, which no longer exists.

**Cost of the choice.** Every fresh copy builds from cold: the dependencies (the same crates every time) and the
workspace crates the tests need. Admission of one situation makes about four fresh copies (null; oracle with ten
hidden runs and the touched packages; the red-at-start runs of those packages; Rail setup and verify), so four cold
builds; a grade makes two (the change; red-at-start, cached once per package). Each PROJECT.md gives its cold build
time. Disk: a copy is the source tree only while it is idle; a debug target/ with `line-tables-only` is a few GB,
alive only while that copy is in use. Grade and admission copies are temp folders removed after use. **A run's copy
(`store/runs/.../copy`) is not removed**, and with Rail it holds one target/ per ticket worktree
(`.claude/worktrees/NN/target`): delete `target` folders of finished runs, or 30 GB fills after a handful of runs.

Measures that do help, all applied:

- `CARGO_INCREMENTAL=0` inside `test_files`/`test_package`: their copies are fresh and built once, so incremental
  data is pure cost (it is written on a cold build, about doubling the workspace crates' share of target/). Not in
  `env`: an agent's or Rail worker's edit-build loop gains from it, and Rail's verify runs in the same worktree
  target/ as the worker, where flipping `CARGO_INCREMENTAL` back and forth would rebuild workspace crates each time.
- `CARGO_PROFILE_DEV_DEBUG=line-tables-only` (env, for everyone).
- No `--all-features`, no `--workspace` builds in the bench's commands.

If cold builds prove too slow, the safe speed-up is `sccache` (content-hashed, keyed on the absolute path unless
`SCCACHE_BASEDIRS` is set), not a shared target dir; not proposed now.

## 4. Running only the hidden tests: `rust-test-files.py`

The runner reads `cargo metadata --no-deps --offline` and, for each listed `.rs` file:

- the target whose crate root it is (`tests/foo.rs` -> `--test foo`, a custom `[[test]] path`, `src/main.rs`), else
  the target whose crate-root folder is the deepest one holding it, preferring one whose root declares the file's top
  module and a library over a binary (`tests/foo/main.rs` + `tests/foo/x.rs` -> `--test foo`;
  `crates/c/src/a/b.rs` -> `-p c --lib`; `src/x.rs` of a binary-only crate -> `--bin NAME`);
- a libtest filter for the file's module path (`a::b::`; `a/mod.rs` -> `a::`), or the file's own test function names
  for a crate root of a lib or bin; the whole target when the file is the test target's crate root and is listed alone;
- `required-features` of the target become `--features`.

Files of one target go into one call, `cargo test -p PKG --test T --no-fail-fast -- f1 f2` (libtest ORs filters).
A listed file that declares child modules kept in other files (`mod x;`) gets `--skip a::b::x::` for each child
that is not listed itself, so a folder module's `mod.rs` or `foo.rs` with a `foo/` folder runs only its own tests.
Non-`.rs` files (snapshots, fixtures, data) and `.rs` files holding no test (a `tests/common/mod.rs` helper, a
`mod.rs` that only registers modules) travel but are not run. It exits non-zero when a `.rs` file fits no target,
when nothing in the list can run, or when a call ran zero tests, counted as passed + failed from libtest's
`test result:` line (also printed by libtest-mimic and kitest; ANSI colour allowed) or nextest's `Summary` line;
`running N tests` would count ignored tests. A filter that matches nothing would otherwise pass the oracle vacuously
while the null check fails on a compile error. Tested on a synthetic workspace with cargo 1.98 (unit tests in
`src/a/b.rs`, `tests/foo.rs` + helper, `tests/bar/main.rs` + module, a custom `[[test]] path = "integration/mod.rs"`
with nested folder modules that hold tests themselves, an only-ignored test, a bin-only crate, `required-features`,
data files, an unplaceable file).

Settings and hooks at the top of the file: `RUNNER` (`test`, or `nextest` for `cargo nextest run` with the same
selectors and filters after `--`, plus `--no-tests=fail`; turso), `ALL_ARGS`, `PKG_ARGS` (per-package cargo args,
e.g. features), `project_hook(path, runs, other)` (handle a file some other way: `other` takes `(argv, cwd)` or
`(argv, cwd, count regex)`, a count of zero failing the run) and `project_finish(runs, other)`.

**The embedded copies are not all the same version.** turso embeds this file as it is now. nushell, ruff and rolldown
embed the first version (no child-module skips, no `RUNNER`/`PKG_ARGS`/`project_finish` in the shared part; each
added what it needed in its own hook: nushell filters a folder module's `mod.rs` by its own top-level fns, ruff adds
per-package args and a finish step, rolldown follows `mod`/`#[path]` from the crate root), with the zero-test count
fixed in all three as above. Port the shared part to them when one of them is next edited.

Known limits: a module renamed with `#[path]` gets the file's name, not the module's (rolldown's hook resolves it);
tests made by a `macro_rules!` are not seen as tests; a proc macro that globs fixture files at compile time makes
tests depend on the absolute path (rolldown's testing_macros 1.0.1 marks every fixture ignored when any folder of
the path starts with a dot, as the bench's default store `~/.rail-bench` and `.claude/worktrees` do: a store path without a dot folder, e.g.
`BENCH_STORE=/srv/rail-bench`, avoids it for the bench's own copies).

`failed`: libtest's per-test line, `^test (.+?)\s+\.\.\. (?:FAILED|timed out)` in general: `\s+` because
libtest-mimic (datatest-stable, ruff's mdtest) pads names; `timed out` is kitest's (nushell). Doc tests are included
(`test src/lib.rs - f (line 3) ... FAILED`). Names are not prefixed by their binary, so the same name in two targets
of one package is one name to the discount. Each project file states its own variant (turso's matches nextest's and
the sqltest runner's lines instead).

## 5. `test_package`

`package_of = "nearest:Cargo.toml"` gives a folder. `test_package` turns it into a workspace member's name with
`cargo metadata` and runs `cargo test -p NAME --tests --no-fail-fast` (lib, bins and integration tests; no doc tests,
no benches, no examples). `--no-fail-fast` matters: without it cargo stops at the first failing test binary, the
binaries after it never run, and the red-at-start discount would then pass a package whose later binaries fail.
A folder that is not a workspace member (an excluded crate, a binding with its own workspace) and `.` (a changed file
outside every crate, Cargo.lock, CI files) get the project's bounded fallback (each PROJECT.md).

## 6. Rail

`setup`: the worktree needs nothing from the main checkout for Rust (toolchain and registry are in the shared cache),
so it checks that: `cargo metadata --offline --format-version 1` (resolves every dependency offline, so it fails when a
crate is missing; whether `cargo fetch --offline` does is less clear) and prints `cargo --version`.

`verify`: changed paths against `$RAIL_BASE` (`git diff --name-only` plus untracked files), mapped to workspace members
by the nearest Cargo.toml; then the project's own format check as its CI runs it (`cargo fmt --all --check`, or turso's
`cargo fmt --check`) and `cargo test -p NAME --tests --no-fail-fast` (turso: nextest) for each, plus the project's
fixed fast part. With no change (admission) it runs only the fixed part. **Admission does
not exercise the package part**: a package whose suite is red at the start commit (flaky, environment-bound) makes
every Rail ship that touches it fail. Each PROJECT.md names the packages to try.
