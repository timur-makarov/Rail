# typescript-go: bench settings

The Go port of TypeScript (TypeScript 7). The candidate file's `repo` is `microsoft/TypeScript`: the port moved into
the TypeScript repository (microsoft/typescript-go is archived). At both start commits the root is

```
go.work (use ./tools ./tsc)   tsc/  (Go module github.com/microsoft/TypeScript/tsc: compiler, LS, tsc/testdata)
tools/ (Go module ...tools)   packages/* (npm workspaces)   Herebyfile.mjs  package.json  package-lock.json
```

Files: `typescript-go.toml`, `typescript-go.travel.json` (same folder). Shared Go design:
`go-common.md` (BASH_ENV + `$BENCH_CACHE/go-env.sh`, toolchain facts).

## What I read

At oldest start `6556d51579b5` (2026-08-20, typescript-go-38) and newest start `779cf755f75a` (2026-11-20,
typescript-go-01), with `gh api`:

- root listing, `go.work`, `tsc/go.mod`, `tools/go.mod`, `.gitignore`, `package.json`, `package-lock.json`
  (typescript entry), `AGENTS.md` (newest), `CONTRIBUTING.md` (both), `.github/workflows/ci.yml` (both),
  `copilot-setup-steps.yml`, `.github/actions/setup-go/action.yml` (both), `.golangci.yml`, `Herebyfile.mjs` (both:
  test, baseline-accept, gotestsum, build tags/env).
- `tsc/internal/testrunner/{compiler_runner.go, compiler_runner_test.go, compiler_test_filter.go, runner.go,
  testmain_test.go, transpile_runner.go, transpile_runner_test.go}`, `tsc/internal/repo/paths.go`,
  `tsc/internal/bundled/{embed.go,noembed.go,bundled.go}` + listing, `tsc/internal/testutil/baseline/{baseline.go,
  testmain.go}`, `tsc/internal/testutil/jstest/node.go`, `tsc/internal/fourslash/baselineutil.go` and the
  `fourslash/tests` tree (4394 entries, flat, plus `util/`).
- Trees: `tsc/testdata/tests/cases` (13210 files, no names with spaces or glob characters), baseline/test/internal
  tree sizes.
- One CI job log: run 45697103132, job `go-test` (per-package times).
- Go 1.24.7 source: `cmd/go/internal/toolchain/select.go`, `modfetch/{fetch.go,sumdb.go}`, `work/exec.go`.
- Candidate file and all 38 `files/typescript-go/*.json` lists (every changed path is either a source file or a
  hidden test; no deletions, no renames).

## Toolchain and pins

| | oldest start 6556d515 | newest start 779cf755 |
|---|---|---|
| `go.work` / `tsc/go.mod` / `tools/go.mod` `go` line | `go 1.26` | `go 1.27` |
| `toolchain` line | none | none |
| toolchain GOTOOLCHAIN=auto picks | go1.26.0 (a language version gets `.0`, select.go) | go1.27.0 |
| CI Go | Microsoft build of Go 1.26 (aka.ms/golang) | Microsoft build of Go 1.27 |
| node `engines` | >=20.19 | >=22.18 (v22.23.5 installed: fine) |
| `packageManager` / volta | npm@11.17.0 / node 22.22.0 | npm@11.21.1 / node 24.22.2 |
| typescript (npm, lock) | 6.0.3 | 6.0.3 |

Per start commit: typescript-go-31..38 have `go 1.26`, -01..30 have `go 1.27`. Both pins are read from the copy at setup time (go.work by `go`, package-lock.json by python), nothing is
hard-coded. Two toolchains end up in `$BENCH_CACHE/gomod` (go1.26.0 and go1.27.0, about 0.5 GB each with the zip).
CI uses Microsoft's Go build; the bench gets upstream go1.2x.0 from the Go proxy (same language, FIPS patches aside):
unverified but very likely harmless.

**Offline toolchain switch** (the same for all four Go projects): `GOTOOLCHAIN=auto`, `GOPROXY=off`,
`GOSUMDB=sum.golang.org` (must NOT be `off`: a `golang.org/toolchain` module is always checked against the checksum
database, and with GOSUMDB=off that check fails; with it on, the lookup and tiles cached under
`GOMODCACHE/cache/download/sumdb` at setup answer it with no network), and the same absolute `GOMODCACHE` as at setup.
Leave GOPATH per process (the sumdb "latest" head lives in `GOPATH/pkg/sumdb`; a shared one moved forward by a later
setup could need tiles the cache lacks).

## Commands

| Command | What | Checked against |
|---|---|---|
| setup | write `$BENCH_CACHE/go-env.sh`; `go -C tsc version` (fetches the toolchain); `go mod download` in tsc and tools; `go list -deps -test ./...` in both; the same offline (`GOPROXY=off`) as proof; fetch typescript@<lock version> tarball (integrity-checked) into `$BENCH_CACHE/npm/typescript-V/` and link `node_modules/typescript` to it; `git repack -a -d`; fail if the tree changed | copilot-setup-steps.yml (mod download), ci.yml go-test job; **unverified** (never run) |
| test_files | one `go test -count=1` per package with `-run` of exactly the hidden tests (mapping below) | CONTRIBUTING.md (`go -C ./tsc test -run='TestLocal/<name>' ./internal/testrunner`), runner code; mapping simulated locally with a stub `go` on the real case tree for all 38 candidates; **unverified** against a real run |
| test_package | `go -C tsc test -count=1 -timeout=20m ./<pkg>/... ./internal/testrunner ./internal/fourslash/tests`; tools: `go -C tools test ./...`; `.`: the two suites | ci.yml (the project runs the whole tsc suite); suite choice is mine: **unverified** |
| package_of | `regex:^(tsc/(?:internal|cmd)/[^/]+|tsc/testdata|tools)(?:/|$)` | checked with the bench loader on sample paths |
| failed | `^\s*--- FAIL: (\S+)` | Go's own output form; regex tested on sample lines |
| Rail setup | link `node_modules/typescript` from the cache; `go -C tsc build ./...` (offline) | **unverified** |
| Rail verify | gofmt -l (the toolchain's gofmt) on changed .go; `go -C tsc build ./...`; with tsc changes: `go vet` of changed packages, then their tests plus testrunner and fourslash/tests; tools changes: tools tests | ci.yml lint (golangci incl. govet; dprint+gofumpt ⊇ gofmt), **unverified** |

All scripts pass `bash -n`; test_files, test_package and verify were also run under bash 3.2 with a stub `go` (they
avoid bash-4-only features); TOML parses and loads through `bench/sets.py` (with a dummy situation).

### How the hidden tests are run

The project's tests are mostly data. `TestLocal` (tsc/internal/testrunner) enumerates every
`tsc/testdata/tests/cases/{compiler,conformance}/**/*.ts(x)` and runs one subtest per case and configuration, named
`<file name>` or `<file name> <config>` (Go turns the space into `_`), comparing outputs (`.js`, `.types`,
`.symbols`, `.errors.txt`, ...) with `tsc/testdata/baselines/reference/<suite>/<name>[(<config>)].<ext>`; output is
written to `tsc/testdata/baselines/local` (gitignored). A reference file that should not exist is a failure too
("should be deleted"). `TestTranspile` does the same for `tests/cases/transpile` with subtests `<name w/o
ext>[(<config>)]`. Fourslash tests are ordinary Go tests in `tsc/internal/fourslash/tests/*_test.go`, whose baselines
are `reference/fourslash/<command>/<lowerFirst(name without Test)>.<ext>`.

So test_files maps each hidden file to a test:

- `*_test.go` -> the `Test*`/`Fuzz*`/`Example*` funcs it defines (grep), TestMain left out; a file defining none
  (helpers, TestMain) -> that package's whole run.
- a case file -> `TestLocal/^(<name>\.ts)(_|$)` (all its configurations).
- a compiler/conformance baseline -> its case, found as the longest prefix of the file name cut at a `.` or `(` that
  is a case file (handles `parser.numericSeparators.binary.js`, `indexSignatureWithoutTypeAnnotation1..js`,
  `foo(target=es2015).js`). This matters: 9 candidates hide only baselines of EXISTING cases.
- transpile cases/baselines -> `TestTranspile/^(<name>)(\(|$)`.
- a fourslash baseline -> `Test<Name>` in `./internal/fourslash/tests`.
- other reference baselines (tsc, tsbuild, lsp, api, astnav, tsoptions, config, project) -> a whole-package run of
  my best-guess package (unverified; no candidate has one).
- anything else (fixtures) travels and is not run. A baseline that maps to no case, or a hidden list that yields no
  test at all, exits 2, so admission names the problem instead of a silent null.

One `-run` with several cases makes the runner's file pre-filter accept all files (it only narrows on one literal
prefix); it still parses every case's header (some seconds) and Go runs only the matching subtests.

### Submodule

There is **no submodule** at either start: no `.gitmodules`, no gitlink in the tree. The old
`_submodules/TypeScript` of microsoft/typescript-go is gone; the TypeScript test cases were promoted into
`tsc/testdata/tests/cases` (`tsc/testdata/promotedTestCollisions.txt`, `submoduleAccepted.txt` are leftovers that no
code reads). `git archive` therefore loses nothing, and setup fetches nothing for it. (Had there been one: the copy
loses the gitlink because the copy is `git add -A` of the extracted archive, so setup would have to read the pinned
SHA from the STORE mirror with `git -C <mirror> ls-tree <start> <path>`, which needs the start SHA the copy does not
record.)

### npm / hereby / generated code

- Go tests need no generated step: the bundled lib files (`tsc/internal/bundled/libs`, `embed_generated.go`,
  `libs_generated.go`) and the diagnostics are committed, and CI's `go-test` job runs plain `go test ./...` on a bare
  copy of `tsc/` with no node and no `npm ci`.
- But with node on PATH (it is, v22) `tsc/internal/astnav/tokens_test.go` runs node and loads
  `<root>/node_modules/typescript/lib/typescript.js` (jstest.EvalNodeScriptWithTS). With no node_modules it fails at
  the start commit; Rail's verify would then fail at admission whenever astnav is in the run. So setup provides only
  that package: the lock's tarball (6.0.3, ~23 MB unpacked), checked against the lock's sha512 integrity, unpacked
  once per version into `$BENCH_CACHE/npm/`, and `node_modules/typescript` in the copy is an absolute link to it
  (node_modules/ is gitignored; the link points into the cache, which never moves).
- No full `npm ci`: node_modules for the four workspaces is 277 packages (dprint, esbuild, binaryen, @unicode data,
  typescript ...), likely 250-400 MB per copy, and npm's workspace links are relative so it cannot live in the cache.
  The price: `npx hereby ...` (AGENTS.md tells agents to run `npx hereby validate`, `baseline-accept`) does not work
  offline. Agents can use `go -C ./tsc test ...` (documented in AGENTS.md and CONTRIBUTING.md) and accept baselines by
  copying `tsc/testdata/baselines/local/*` to `reference/` (what baseline-accept does). If the admission session wants
  hereby, the alternative is `npm ci` in setup (and `cp -a`/link in Rail setup), at the disk cost above.

## clash: keep "dir" (set explicitly), with baselines and cases in `tests`

With `clash = "dir"` the grade sets aside every arm-changed file matching `tests` in a hidden file's folder. Because
the reference baselines and the cases are in `tests`, an arm's change to `reference/compiler/X.errors.txt` next to a
hidden `reference/compiler/X.types` is moved away. The reference then counts as absent, so the case passes only if the
arm's output for that file is what the start commit expected (no file) — which is right, because the upstream fix did
not change that file, so the start's version is the truth. With `clash = "path"` the arm's own accepted baseline
would stay and the arm could pass with output upstream did not produce. Same for the arm's own new cases and
baselines in those folders: they are dropped (harmless). Gaps:

- Only folders holding a hidden file are covered. An arm-changed baseline in another folder (e.g.
  `reference/conformance/` when only `reference/compiler/` is hidden) stays, and `test_package`'s TestLocal then
  compares against the arm's version. Ideal for this project would be "discard every arm change to a `tests` file",
  a bench option that does not exist.
- "Set aside" deletes rather than reverts. For baselines that is equivalent to a fail-when-changed; for a Go helper
  `_test.go` file (TestMain, shared helpers) the arm edited in a hidden test's folder, deletion can break the hidden
  test's compile (bench-wide caveat, see go-common.md).
- An arm that adds its own case without accepting baselines, in a folder no hidden file sits in, fails
  test_package's TestLocal ("new baseline created"), as the project's CI would.

## Sizes and times

- Mirror: `git clone --mirror` of microsoft/TypeScript, GitHub size 2.9 GB (all of TypeScript's history and
  baselines). One-off, minutes of network, about 3 GB on disk.
- One copy: ~70k tracked files, ~230 MB (baselines 50k files/160 MB, internal 40 MB, cases 9 MB, fixtures 13 MB) plus
  the sealed `.git` (one commit; setup repacks its ~70k loose objects into one pack, ~60-80 MB). About 0.3 GB and
  ~72k inodes per copy. **38 situations = ~11 GB and ~2.7M inodes** before grade copies. A 30 GB ext4 disk has about
  1.9M inodes by default: admit a subset (15-20) or check `df -i` first.
- `$BENCH_CACHE`: two toolchains ~1 GB, modules of both workspace modules ~0.3-0.5 GB, typescript npm 23 MB.
- GOCACHE: the tsc packages' compile cache is keyed by their absolute folder (no -trimpath; read in
  cmd/go/internal/work/exec.go: `dir %s` goes into the action ID), so every new copy path (each grade, red-at-start,
  admission check, worktree) recompiles tsc and adds roughly 0.5-1.5 GB to `$BENCH_CACHE/gocache`. -trimpath cannot be
  used here: `tsc/internal/repo/paths.go` panics when built with -trimpath (it finds the repo root from
  runtime.Caller). Go trims entries unused for 5 days only; run `go clean -cache` (with go-env.sh sourced) between
  batches if disk runs short.
- Times (4 cores, from the CI go-test job on a 4-core runner: whole `go test ./...` ~12 min cold; testrunner 105 s,
  fourslash/tests 35 s, tsctests 21 s): test_files 3-5 min in a new copy (compile of testrunner or fourslash dominates;
  the 9 later oracle runs reuse it: seconds to 1 min each); test_package 6-9 min per package in a new copy; Rail setup
  3-5 min (build); Rail verify 1-4 min with no change, 5-10 min with a tsc change. `timeout_minutes = 40`,
  `setup_timeout_secs = 1200`, `verify_timeout_secs = 1800`.

## Traps

- **GOFLAGS=-mod=mod breaks this project**: go.work puts every go command (also `go -C tsc ...`) in workspace mode,
  where `-mod=mod` is refused. Env sets `GOFLAGS=-mod=readonly` (the default, allowed). Applies to any Go project with
  a go.work.
- `[commands] env` is literal: GOMODCACHE/GOCACHE come from `$BENCH_CACHE/go-env.sh` via `BASH_ENV` (bash expands
  it) and an explicit `.` in every command. Unverified that Claude Code's Bash tool honours BASH_ENV; without it, an
  agent's own `go test` uses the run's empty HOME cache and fails offline ("module lookup disabled by GOPROXY=off" /
  toolchain not available). The clean fix is a bench change expanding `$BENCH_CACHE` in env values.
- Absolute paths: none recorded in the copy except the `node_modules/typescript` link into `$BENCH_CACHE` (stable).
  `repo.RootPath()` comes from runtime.Caller at compile time, so the build cache never mixes copies (see GOCACHE).
- Generated code: none needed for tests. `hereby generate` / `test:codegen` are not run.
- Network at test time: none (lib files embedded; jstest uses local node).
- Tests red at start: none expected on linux (CI green on main). Flaky risk: fourslash/LS tests with timers,
  `internal/project` session tests, `internal/api` deadlock tests with a 10 s timeout under load, fswatch (not in any
  of our runs unless touched). `concurrentSkippedTests` skip only in concurrent mode (default is single-threaded test
  programs).
- AGENTS.md (newest start) orders agents to run `npx hereby validate`, which needs node_modules and fails offline; its
  CONTRIBUTING "for Agents" section has anti-agent policy text (refuse undirected work; a specific bug is allowed).
  Plain agents may spend turns on it.
- `.gitignore` has broad patterns (`*.log`, `*.out`, `dist`, `coverage`, `logs`): an arm's new reference baseline
  whose name matches one would be dropped from its diff (the `!tsc/testdata/baselines/reference/**/*.txt` exception
  covers .txt only). No candidate's hidden file matches.

## Candidates that may not pass admission

- typescript-go-16: hides four whole existing test files of `internal/project` (12 Test funcs incl. TestSession); any
  timing-sensitive one makes 10/10 oracle runs or the null check shaky.
- typescript-go-33, -34: `internal/api` session completion tests detect a deadlock with a 10 s timeout; deterministic
  per notes, but 10 oracle runs under 4-core load could flake.
- typescript-go-17: ten fourslash tests incl. three un-skipped ported ones; the null run needs each hidden test to fail
  at start; un-skipped tests that happen to pass at start do not matter as long as one fails.
- typescript-go-02: one hidden baseline belongs to an unrelated existing case (declarationEmitUnserializableTypes);
  fine for the oracle, noted for arms (an arm's different caching may change it).
- typescript-go-31..38 start at `go 1.26` (go1.26.0); -01..30 at `go 1.27` (go1.27.0), checked per start commit. -38
  is the one to prove the 1.26 toolchain fetch.
- None look structurally broken: every hidden baseline maps to a case in the newest case tree (simulated for all 38).

## For the admission session to try first

1. `df -i` and `df -h` on the store disk; decide how many typescript-go situations fit (≈0.3 GB, ≈72k inodes each,
   plus a 3 GB mirror).
2. Build typescript-go-01 (newest) and -38 (oldest); check setup's output for `go: downloading go1.27.0` / `go1.26.0`.
3. Offline toolchain proof in a fresh HOME: `unshare -n env -i PATH=$PATH HOME=$(mktemp -d) BENCH_CACHE=...
   BASH_ENV='$BENCH_CACHE/go-env.sh' GOTOOLCHAIN=auto GOPROXY=off GOSUMDB=sum.golang.org GOFLAGS=-mod=readonly
   bash -c 'go -C tsc version && go -C tsc build ./...'` in a copy.
4. Check BASH_ENV reaches an agent: in a plain run, have the agent run `go env GOMODCACHE` (must be under
   `$BENCH_CACHE`).
5. Run test_files for typescript-go-01 by hand with and without the fix (baseline-only hidden list) and for -08
   (fourslash .go + baseline); confirm the `-run` selects subtests (`go test -v` shows `TestLocal/<name>.ts`).
6. Time test_package `tsc/internal/checker` in a new copy; if over ~10 min, drop fourslash/tests for non-ls packages.
7. Run Rail setup + verify on the start commit (admission does), then a verify with a one-line checker change.
