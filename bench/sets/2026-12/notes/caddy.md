# caddy (caddyserver/caddy): bench settings, how they were found

Files: `caddy.toml` (project, commands, Rail commands), `caddy.travel.json` (which changed files are hidden).
Nothing was cloned, built or run; every command is `unverified` until the admission session runs it.

## What I read

Commits: oldest start `b2be548275c99cd061ec1c2f9c27eedae64a17b8` (caddy-29, 2026-07-11), newest start
`16618f454ca6f78f37dfd85a90573d8ffd43c1c8` (caddy-01, 2026-11-18); `ci.yml` also at the starts of caddy-24, 23, 16,
10, 05 and 02; `go.mod` at all 29 starts.

- `.github/workflows/ci.yml` (both ends and five between), `.github/workflows/lint.yml`, `.gitignore`, `AGENTS.md`,
  `go.mod`, the recursive tree at both ends (no `go.work`, no submodule, no Makefile, no vendor folder).
- `caddytest/caddytest.go` (the integration harness), `caddytest/integration/caddyfile_adapt_test.go`,
  `modules/caddypki/acmeserver/acmeserver_test.go`, `caddyconfig/caddyfile/formatter_test.go` (TestMain).
- Every hidden test file at its fix commit (37 files), the sibling `_test.go` files of each hidden folder at its start
  (for the clash rule), the candidate file and the 29 changed-file lists.
- Go 1.24.7's own source for the offline toolchain switch: `cmd/go/internal/toolchain/select.go`,
  `cmd/go/internal/modfetch/fetch.go`, `cmd/go/internal/modfetch/sumdb.go` (summary in go-common.md, next to this
  folder: `go-common.md`).
- The bench: `sets.py`, `sealed.py`, `grade.py`, `admit.py`, `common.py`, `netlock.py`, `proxy.py`, parts of
  `driver.py` and `runs.py`.

What CI does (ci.yml@16618f454c, the same shape at b2be548275): `GOFLAGS=-tags=nobadger,nomysql,nopgx`,
`GOTOOLCHAIN=local` with setup-go `~1.26.0` (until about 2026-10-19) then `~1.27.0`, `go get -v -t -d ./...`,
`go test -coverprofile=cover-profile.out -short -race ./...`, and from about 2026-10-09 `GODEBUG=http2xconnect=1`.
Lint is golangci-lint `latest` (not pinned) plus govulncheck. AGENTS.md: `go test -race -short ./...`, integration
tests `go test ./caddytest/integration/...` (no -short), `golangci-lint run --timeout 10m`.

## Toolchain and pins

| Starts | go.mod | toolchain line | GOTOOLCHAIN=auto picks | CI used then |
|---|---|---|---|---|
| caddy-24..29 (2026-07-11..09-26) | `go 1.25.1` | none | go1.25.1 | ~1.26.x |
| caddy-01..23 (2026-10-03..11-18) | `go 1.26.0` | none | go1.26.0 | ~1.26.x, then ~1.27.x from about 10-26 |

Go 1.24.7 is installed, so every start needs a switch. Two toolchains are downloaded in all (about 0.3 GB each with
their zips). Both versions exist on proxy.golang.org (go1.25.0..1.25.14, go1.26.0..1.26.11, go1.27.0..1.27.4).

The env that makes the switch work offline after setup downloaded it once (from cmd/go source, not tried):
- `GOTOOLCHAIN=auto`, `GOPROXY=off`;
- `GOMODCACHE` = the same absolute folder setup used (`$BENCH_CACHE/gomod`): it holds the toolchain module (zip,
  ziphash, extracted tree) and the checksum database's cached lookup and tiles (`cache/download/sumdb/...`);
- `GOSUMDB=sum.golang.org`, NOT off: `useSumDB` always checks a `golang.org/toolchain` module against the checksum
  database (go.sum can never list it), even with GOSUMDB=off, and with GOSUMDB=off that check fails. With the lookup
  and tiles cached, the client never calls the network (`initBase` runs only on a cache miss);
- `GOPATH` left alone (per process): the checksum database's "latest tree" file lives in `GOPATH/pkg/sumdb`, not in
  GOMODCACHE. A shared one that a later setup moved forward could need tiles that are not cached, which means the
  network. In agent runs HOME is fresh, so the file starts empty and the cached record is accepted.
- `GOFLAGS=-mod=mod` is harmless here (caddy has no go.work; with a go.work it would be refused).

The [commands] env table is set literally by the bench (`sealed.project_env` does `env.update(...)`, no expansion), so
`GOMODCACHE="$BENCH_CACHE/gomod"` cannot go there: Go refuses a relative GOMODCACHE. Setup writes
`$BENCH_CACHE/go-env.sh` (two exports, the same text for every situation) and env sets
`BASH_ENV="$BENCH_CACHE/go-env.sh"`: bash expands BASH_ENV and sources the file in every non-interactive shell
(`bash -c`, `bash -lc`, nested bash; checked locally). Every command also sources it explicitly. If Claude Code's Bash
tool or Rail's runner does not start bash (or the agent runs `sh`), the agent's own `go` commands find an empty
module cache in their fresh HOME and fail offline. The clean fix is a bench change: expand `$BENCH_CACHE` in env
values (then GOMODCACHE and GOCACHE move into the env table and BASH_ENV goes).

Alternative if a test fails only because of the old toolchain (1.25.1 was never what CI ran at those starts):
`GOTOOLCHAIN = "go1.26.11+auto"` runs every start on go1.26.11 (and switches up if a go.mod asks for more), one
toolchain instead of two, closer to CI for caddy-11..29, one minor below CI for caddy-01..10.

## Commands

| Command | What | Verified? |
|---|---|---|
| setup | writes go-env.sh; cleans GOCACHE when over 6 GB; `go version` (fetches the toolchain); `go mod download`; `go list -deps -test ./...` with the proxy, then again with `GOPROXY=off`; restores go.mod/go.sum if touched; fails if the copy is left with changes | unverified (CI uses `go get -v -t -d ./...`, which may edit go.mod; replaced by read-only downloads) |
| test_files | per folder, `go test -count=1 -v -run '^(names)$' ./DIR` with the Test/Fuzz/Example names the hidden files define (TestMain left out; a file with none runs its whole package); hidden adapt cases run as `-run '^TestCaddyfileAdaptToJSON$/^(case\.caddyfiletest|...)$' ./caddytest/integration`; non-.go files are skipped. Fails when a run ran nothing (`no tests to run`, `[no test files]`) or when caddytest skipped for "failed integration prerequisites" | unverified; no `-short` on purpose (from AGENTS.md: integration tests run without it; caddytest's InitServer skips under -short) |
| test_package | walk `{package}` up to the nearest folder holding `.go` files; `go test -count=1 -short ./DIR` | unverified; -short from ci.yml/AGENTS.md, -race and coverage left out |
| package_of | `regex:^(.*?)(?:/testdata/.*|/[^/]*)$`: the file's folder cut at testdata; root files give `.` (the root package, about 20 s) | checked on sample paths with the bench's loader |
| failed | `^\s*--- FAIL: (\S+)` (top-level and indented subtests) | checked on sample output with the bench's loader |
| env | `GOTOOLCHAIN=auto GOPROXY=off GOSUMDB=sum.golang.org GOFLAGS="-mod=mod -tags=nobadger,nomysql,nopgx" GODEBUG=http2xconnect=1 BASH_ENV=$BENCH_CACHE/go-env.sh` | tags and GODEBUG from ci.yml; the rest reasoned |
| Rail setup | `go version && go build ./...` (offline; nothing to install: modules, toolchain and build cache are shared in $BENCH_CACHE) | unverified |
| Rail verify | gofmt -l on changed `.go` files; `go build ./...`; then `go vet` and `go test -count=1 -short` on the packages the branch changes against `$RAIL_BASE` (`git diff --name-only` plus untracked, minus `.rail/` and `.claude/`) | unverified; golangci-lint left out (not installed, CI runs `latest`, cannot be pinned offline); go vet is its govet part |
| timeouts | timeout_minutes 30; Rail timeout_secs 1800, setup 900, verify 1800 | estimates |

All commands pass `bash -n`; the TOML loads through `bench/sets.py` (with a dummy situation appended). test_files
and test_package were run against a fake `go` on a small tree made from real hidden files (caddy-01, 03, 13): the
selection, the adapt subtest pattern, the two guards and the exit codes behave as intended.

`go test ./...` and `go build ./...` skip folders whose names start with `.` or `_`, so `.claude/worktrees/NN` and
`.rail` inside the copy are never built from the root.

## Sizes and times (estimates)

- One copy: about 850 files, 5.5 MB of tracked content, about 10 MB with its one-commit `.git`. Setup adds nothing
  inside the copy.
- `$BENCH_CACHE` (caddy only): modules 1 to 1.5 GB, two toolchains about 0.6 GB, build cache growing (below).
- First setup about 3 to 6 minutes (toolchain plus modules); later setups for the same toolchain under a minute.
- A package run (`test_package`) in a fresh copy: 1 to 3 minutes, mostly compiling caddy's own packages; the
  tests themselves take seconds (reverseproxy and caddyhttp the longest, under a minute with -short).
- test_files: the first run in a copy compiles the package (caddytest/integration imports every standard module:
  1 to 2 minutes); the next nine oracle runs reuse it and take seconds each.
- Rail verify on the start commit (no change): gofmt nothing, `go build ./...` 1 to 3 minutes in a new worktree.
  With a change: plus vet and tests of the changed packages, 2 to 5 minutes. Well under 15 minutes.

## Traps

1. **Build cache growth.** Go keys the compile of a main-module package by its absolute folder (no `-trimpath`), so
   every new copy path (each admission copy, each grade copy, each agent run and each Rail worktree) adds one
   compile of the packages it touches, about 50 to 300 MB, to the shared `$BENCH_CACHE/gocache`; only modules and the
   standard library are shared across paths. Go trims only entries unused for 5 days. Setup cleans the cache when it
   is over 6 GB; between batches of runs, run `. "$BENCH_CACHE/go-env.sh"; go clean -cache` (safe: it only costs a
   recompile). `-trimpath` would make copies share their compiles but breaks caddytest: `getIntegrationDir` uses
   `runtime.Caller` to find the test certificates, and with trimmed paths every integration test skips.
2. **Silent skips.** caddytest skips (not fails) a test when its in-process server cannot start, for instance when
   port 2999, 9080 or 9443 is taken, and skips every integration test under `-short`. test_files therefore runs
   without -short and fails on "failed integration prerequisites". The bench's grades and admissions run on the
   host network: do not run two caddy integration situations (02, 03, 13, 15, 16, 21) at the same time. Inside an
   agent's network namespace loopback is up (netlock brings `lo` up) and the cost proxies use ephemeral ports, so the
   fixed ports are free there.
3. **Whole hidden files run.** -run takes every Test the hidden file defines, so one test in that file already red at
   the start commit, or flaky, fails the oracle. Large ones: caddy-01 `server_test.go` (93 tests) and
   `idletimeout_test.go` (38), caddy-09/11 `filters_test.go` (29/28), caddy-04/20/29 `parse_test.go` (17 to 20).
4. **Clash rule.** Kept the Go default `dir` (an arm's new test file in a hidden folder could otherwise redeclare a
   hidden Test or helper). But the grade MOVES the arm's edited sibling test files away rather than reverting them,
   and three hidden files depend on a sibling: caddy-17 `encode_conformance_test.go` uses the helpers of
   `encode_harness_test.go`; caddy-27 `active_health_test.go` uses `resetDynamicHosts` from
   `dynamic_upstreams_test.go`; caddy-04's folder has a TestMain in `formatter_test.go` (clears the environment). An
   arm that edits one of those siblings fails to compile the hidden tests and is graded wrong. Bench fix: restore an
   edited test file to its start version, delete only new ones.
5. **Toolchain older than CI.** caddy-24..29 run on go1.25.1 and caddy-01..23 on go1.26.0, the go.mod minimums,
   while CI ran the newest 1.26.x or 1.27.x. See the GOTOOLCHAIN alternative above.
6. **Root.** The bench runs as root. caddy-28 (`filewriter_test.go`, file modes under a set umask) and caddy-04
   (import errors; uses ENOTDIR, not EACCES) were checked and do not depend on being refused a permission.
7. **No network at test time.** None of the hidden tests reaches outside loopback: caddy-07 uses an httptest proxy
   and `acme.invalid`; caddy-21 uses `local_certs`; the integration tests use the in-process server. Unknown for the
   rest of a package under test_package; CI runs with the network, so a package test that needs it would show as
   red at the start and be discounted only when it names itself.
8. **Tracked files from setup.** CI's `go get` may rewrite go.mod/go.sum; setup uses read-only downloads and fails if
   the copy is left changed, because the grade diffs the copy against the start commit.
9. **Large ignored binary.** An agent's `go build` in `cmd/caddy` leaves `cmd/caddy/caddy` (gitignored, about
   40 MB). It is not a folder, so `build_dirs` cannot leave it out of Rail's saved stages.
10. **GODEBUG=http2xconnect=1** is set for every start; CI set it only from about 2026-10-09. Older toolchains ignore
    an unknown key; the setting enables HTTP/2 extended CONNECT in x/net's server code, which no hidden test of the
    older situations touches.

## Candidates that may not pass admission

- caddy-03, caddy-29: their hidden lists must gain the adapt cases the fix changes (`caddy.travel.json` does that);
  with the candidate file's lists as they are, the oracle applies the new expectations as "source", test_files never
  runs TestCaddyfileAdaptToJSON, and an arm's adapt output is not checked at all (its package run is
  `./modules/caddyhttp/reverseproxy/fastcgi`, not the integration package).
- caddy-01: timing (100 ms / 300 ms deadlines) over ten runs, and 131 tests in the two hidden files.
- caddy-21: waits up to 5 s for certificates issued in the background by the internal CA; slow under load.
- caddy-16: integration logging test polls for up to 5 s.
- caddy-17, caddy-27: fine for the oracle; exposed to the clash rule (trap 4) for arms.
- caddy-24..29: go1.25.1 (trap 5).

## For the admission session to try first

1. Build caddy-01 (go1.26.0) and caddy-29 (go1.25.1); after setup, check offline in a fresh HOME:
   `unshare -n env HOME=$(mktemp -d) bash -c 'cd COPY && go version && go test -count=1 -run XXX ./modules/caddyhttp'`
   with the [commands] env set. This proves the cached toolchain switch and module cache work with no network.
2. Check BASH_ENV reaches an agent: run Claude Code in a locked run and have it run `go env GOMODCACHE GOCACHE`.
   If it prints HOME paths, ask for the bench change (expand `$BENCH_CACHE` in env values).
3. Admit caddy-03 (adapt subtests plus integration tests in one package) and caddy-13 (two folders, one of them the
   integration package) to exercise every branch of test_files.
4. Run Rail verify on a start commit in a new worktree and time it.
5. Watch `du -sh $BENCH_CACHE/gocache` across the first few admissions.
