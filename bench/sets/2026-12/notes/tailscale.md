# tailscale (tailscale/tailscale): bench settings

A reserve project. Files: `tailscale.toml` (project, commands, Rail's commands), `tailscale.travel.json`.

## What I read

At the oldest start `74235b46c1e435ac90fb0d962efd7b77bd205224` (tailscale-23, July 2026) and the newest start
`da6276d77025ee2bce288c4ccf07b35e14f253a7` (tailscale-02, November 2026), with `gh api`:

- `go.mod` (`go` line, `require honnef.co/go/tools`, `tool` block), `go.toolchain.rev`, `go.toolchain.next.rev`,
  `go.toolchain.branch`, `go.toolchain.version` (newest), `.gitignore`, `Makefile`, `staticcheck.conf`.
- `tool/go` and `tool/gocross/gocross-wrapper.sh` (identical at both commits).
- `.github/workflows/test.yml` (both), `vet.yml` (both), `golangci-lint.yml`, `checklocks.yml` (newest).
- `cmd/testwrapper/flakytest/flakytest.go`, `tstest/tstest.go`, `tstest/resource.go`,
  `tstest/privileges_notwindows.go`, `tool/listpkgs/listpkgs.go`, `cmd/vet/vet.go`, the root package's tests
  (`version_tailscale_test.go`, `cache_key_test.go`, `gomod_test.go`, `assert_ts_toolchain_match.go`).
- tailscale/go (the fork) at both pinned revs: `VERSION` and `go.env`.
- Every candidate's hidden test file at its fix and start commits (Test names, build tags, what they use), and the
  changed-file lists in `bench-sets/files/tailscale/*.json`.
- Checked on the network: proxy.golang.org has `golang.org/toolchain` `go1.26.4` and `go1.27.4` linux-amd64 (302);
  the fork's release tarballs `build-<rev>/linux-amd64.tar.gz` exist for both revs (57 MB and 60 MB).

## Toolchain and pins

| | oldest start 74235b46 | newest start da6276d7 |
|---|---|---|
| go.mod `go` | 1.26.4 | 1.27.4 |
| `toolchain` line | none | none |
| go.toolchain.rev (fork) | c803676b…, branch tailscale.go1.26, VERSION go1.26.4 | ee691292…, branch tailscale.go1.27, VERSION go1.27.4 |
| fork go.env | GOTOOLCHAIN=auto, GOSUMDB=sum.golang.org | same |
| staticcheck (go.mod require) | honnef.co/go/tools v0.7.0 | v0.8.1 |
| module layout | one module, no go.work, no submodules, no vendor | same |

Both pins are newer than the installed go 1.24.7, and they change between start commits, so nothing is hard-coded:
setup reads `go.toolchain.rev` from the copy.

**Fork or stock Go.** Tailscale's CI runs every build and test through `./tool/go`, which runs Tailscale's Go fork
(github.com/tailscale/go; it sets the `tailscale_go` build tag, which some files and tests need, e.g.
`version_tailscale_test.go`, `assert_ts_toolchain_match.go`, `net/sockstats` with `ts_enable_sockstats`). Stock Go
would build most packages and very likely run all 23 hidden tests the same, but the grade should match upstream's CI,
so every bench command uses `./tool/go`. Setup ALSO fetches the stock toolchain go.mod names, so a bare `go` typed by
an agent works offline too (stock, without the `tailscale_go` tag).

**How the fork works offline.** `./tool/go` (→ `gocross-wrapper.sh`) runs `$HOME/.cache/tsgo/$REV/bin/go` and
downloads it with curl when `$HOME/.cache/tsgo/$REV.extracted` is missing. Agent runs get a fresh HOME, so it would
try to download, offline. Setup therefore downloads the fork once per REV into `$BENCH_CACHE/tsgo/$REV` (plus the
`$REV.extracted` marker, written last), and `$BENCH_CACHE/go-env.sh` (sourced by every bash through `BASH_ENV`, and
explicitly by every command) symlinks each fetched fork into the current `$HOME/.cache/tsgo/`. That is a few
`ln -s` per new HOME, silent on errors, and it never touches the network. Tested locally with a fake fork: a fresh
HOME gets the link, `set -euo pipefail` shells are unaffected, a missing cache is a no-op.

**Env that makes it work offline** (`[commands.env]`): `GOTOOLCHAIN=auto` (the fork reports go1.27.4 = go.mod, so no
switch; stock 1.24.7 switches to the cached stock toolchain), `GOPROXY=off`, `GOSUMDB=sum.golang.org` (must NOT be
off: a toolchain module always needs a checksum-database check, served from the cached lookup in
`$GOMODCACHE/cache/download/sumdb`), `GOFLAGS=-mod=mod`, `BASH_ENV=$BENCH_CACHE/go-env.sh` (bash expands it), and
from go-env.sh `GOMODCACHE=$BENCH_CACHE/gomod`, `GOCACHE=$BENCH_CACHE/gocache`,
`STATICCHECK_CACHE=$BENCH_CACHE/staticcheck`. GOPATH is left per process on purpose (see go-common.md: a shared
sumdb "latest" could force a network fetch). `TS_SKIP_FLAKY_TESTS=true` makes tests marked
`flakytest.Mark` skip themselves (CI retries them through cmd/testwrapper instead; the bench has no retry).

## Commands

| Command | What | Verified? |
|---|---|---|
| setup | write go-env.sh; fetch the fork for `go.toolchain.rev` into `$BENCH_CACHE/tsgo`; `./tool/go version`; `go version` (stock toolchain); `./tool/go mod download` (CI's gomod-cache step); `go list -deps -test ./...`; build `./cmd/vet` and staticcheck once; `go list -e -export -deps -test ./...` compiles every package and test variant into GOCACHE without linking; restore any tracked file setup changed | unverified (fork URL/layout from gocross-wrapper.sh@da6276d7; mod download from test.yml) |
| test_files | per folder of the hidden `_test.go` files, `./tool/go test -count=1 -run '^(Names)$' ./DIR`, Names = the `func Test…/Fuzz…/Example…` the hidden files define; non-.go files skipped; a hidden test file with no such func runs its whole package; `PATH=$PWD/tool:$PATH` as CI does, so a test that execs `go` gets the fork | unverified (selection is the bench's own; `go test` via ./tool/go is CI's) |
| test_package | walk `{package}` up to the nearest folder holding .go files, `./tool/go test -count=1 ./P` | unverified |
| package_of | `regex:^(.*?)(?:/testdata/.*|/[^/]*)$` (folder, cut at testdata; root files → `.`, the root package `tailscaleroot`: license headers, go.mod, toolchain match: quick) | checked on sample paths |
| failed | `^\s*--- FAIL: (\S+)` (top tests and indented subtests; a panicking test prints its FAIL line before the trace) | checked on sample output |
| Rail setup | source go-env.sh, `./tool/go version`, `./tool/go build ./...` | unverified (build all from test.yml) |
| Rail verify | gofmt -l on changed .go files; `./tool/go build ./...`; for the changed packages: Tailscale's vet tool (`go build ./cmd/vet` + `go vet -vettool`, as vet.yml), staticcheck as the Makefile runs it (PATH with the fork's GOROOT/bin first, tempfork/ left out), `go test -count=1` | unverified (each piece is from CI or the Makefile; the affected selection is the bench's own) |

Plain `go vet` (all default analyzers) is left out of verify on purpose: CI does not run it (vet.yml runs only the
custom vettool, whose unitchecker has only jsontags, lowerell and subtestnames), so a package could fail it at the
start. `go test` still runs its usual vet subset. golangci-lint, depaware, `go generate` cleanliness and the
privileged/integration/natlab/VM jobs are left out (heavy, docker/root/qemu, or not about the change).

`clash = "path"`, not Go's default `dir`: tailscale packages share test helpers across many `_test.go` files
(`ipn/ipnlocal/local_test.go` defines `newLocalBackendWithMockEngineAndControl`, used by tailnet-lock, serve,
peerapi and node_backend tests: four candidates live in ipn/ipnlocal). With `dir`, an arm that added a test to any
such file would have that file moved away whole (the bench deletes, it does not revert), the package would stop
compiling and the hidden tests would fail for a reason that is not the arm's. With `path`, the only clash left is an
arm defining a top-level name the hidden file also defines in a different file of the package (unlikely: arms add
tests to the obvious file, which is the hidden one and is set aside).

## Sizes and times (estimates, unverified)

- One copy: tree 24.7 MB in 3,168 files at the newest start, plus one commit's git objects: about 40–50 MB.
- `$BENCH_CACHE` (shared by all situations): module cache 1.5–2.5 GB (go.mod requires golangci-lint and k8s trees);
  fork ~250 MB extracted per REV (two REVs over the window, maybe more); stock toolchains ~250 MB each; GOCACHE
  3–6 GB after the warm-up; staticcheck cache some hundred MB. Call it 6–10 GB: a lot of the 30 GB. If disk is
  short, drop the `go list -export` warm-up line from setup (builds are then cold per run, a few minutes more).
- Setup: first one cold 20–35 min (download + compile everything on 4 cores); later ones 3–8 min (incremental).
- Hidden-test run: 20–90 s (compile the package's test binary, link, run the named tests).
- Package run: tstime/util/cmpver seconds; wgengine/netstack, net/*, cmd/tailscale/cli 20–60 s; ipn/ipnlocal and
  cmd/k8s-operator 1–3 min.
- Rail verify with one or two changed packages: 3–8 min, most of it staticcheck's first cold analysis of the
  dependency graph (its cache then lives in `$BENCH_CACHE/staticcheck`).

## Traps

- **BASH_ENV** carries GOMODCACHE/GOCACHE and the fork links into the agent's shells, because `[commands] env` is not
  expanded by the bench. If Claude Code's Bash tool or Rail's runner does not start bash (or runs `sh`), a bare
  `go`/`./tool/go` in an agent run will try to download. The commands themselves source go-env.sh explicitly.
- **Fork via HOME**: if a run's HOME is not writable, the link step fails silently and `./tool/go` tries curl.
- **Root**: the bench runs as root, so tests gated by `tstest.RequireRoot` (derp/xdp, ssh/tailssh privs,
  tstest/integration, util/linuxfw nftables, wgengine/router/osrouter) RUN, unlike in CI's main test job. None of the
  candidates' hidden tests or touched packages is among them. If a change touches one, its test_package may need
  netlink/tun/nftables; failures that are also red at the start are discounted.
- **Network namespace**: agent runs see only loopback (brought up by the bench). Tests that bind `:0` or 127.0.0.1
  (socks5, derpserver, serve, httptest) work. Tests that look for a default route or real interfaces (net/netmon,
  net/netcheck, portmapper discovery) may behave differently inside the namespace than in the bench's grade, so a Rail
  verify inside an agent run can fail where admission passed. Watch net/netmon (tailscale-03).
- **Generated/committed files**: none needed by tests at setup (generated code is committed; gocross is not built
  because TS_USE_GOCROSS is unset; `/gocross` is gitignored anyway). Setup restores any tracked file it changed and
  removes untracked ones, so the agent's diff starts clean.
- **-race**: not used. The three "race" candidates (03 netmon, 05 tailnet-lock, 19 derpserver) assert their outcome
  deterministically (10 s deadlock timer; netmap/state after logout; shared backing array check after wg.Wait), so the
  race detector is not needed for the oracle.
- **Flaky**: tests with fixed deadlines (socks5 10 s log poll, netmon 10 s, server timing) under a loaded 4-core
  machine; `TS_SKIP_FLAKY_TESTS` skips only tests upstream marked.
- **go.mod changes**: a fix or an arm that adds a dependency cannot build offline (GOPROXY=off); none of the 23 fixes
  touches go.mod.
- **Whole-file selection**: `-run` takes every Test in each hidden file (up to 27 in ipn/ipnlocal/serve_test.go), so
  a test in the same file already red or flaky at the start fails the oracle.

## Candidates that may not pass admission

- tailscale-07, -09, -10, -11, -20, -14, -18, -22, -12, -13, -04, -15: the fix adds no new Test function; it changes
  existing ones (or table rows). Fine for the oracle, but every Test in the file runs, so one red-at-start neighbour
  fails it.
- tailscale-03 (net/netmon): the start commit deadlocks until the test's own 10 s timer, fine; other netmon tests in
  the file use netlink and real interfaces: fine on the host, may differ in an agent's namespace.
- tailscale-17 (net/socks5): polls the standard log for 10 s; on a slow machine the null run takes 10 s+ per run.
- tailscale-02/-22/-12 (k8s operator): the package run of cmd/k8s-operator is the slowest of the set (1–3 min) and
  builds a large dependency tree the first time.
- tailscale-19: the fix also touches cmd/derper; its package run compiles cmd/derper's tests (including any deps
  test) — expect it to pass, but it is the one candidate with three touched packages.

No candidate's hidden tests depend on root, the network, a build tag or a testify suite, and every hidden file
defines at least one top-level `Test` function, so the `-run` selection finds them all.

## For the admission session to try first

1. On the machine, setup for tailscale-02 (newest; go 1.27.4) then, in `unshare -n` with a fresh `HOME=$(mktemp -d)`
   and the `[commands.env]`, run `bash -c './tool/go version; go version; ./tool/go test -count=1 ./tstime'`: proves
   the fork link, the stock toolchain switch and the module cache offline.
2. Check that the agent's Bash tool honours BASH_ENV: in an agent run, `echo $GOMODCACHE` must print the cache path.
3. Setup for tailscale-23 (oldest; go 1.26.4, the other fork REV) and look at `$BENCH_CACHE` size after both.
4. Admit tailscale-15 (smallest: util/cmpver, one test) to check the oracle path end to end, then tailscale-05
   (ipn/ipnlocal, the slow package) for times.
5. Run Rail verify on the start commit in the root and in a new worktree, offline, and time the staticcheck step.
