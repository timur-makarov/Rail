# rclone: bench settings, how they were found

Project `rclone` = github.com/rclone/rclone, module `github.com/rclone/rclone`, a reserve. 24 candidates, starts from
2026-07-02 (rclone-24, c1b5756eec) to 2026-11-25 (rclone-01, 554ddb5de2). Settings: `rclone.toml`, `rclone.travel.json`.
The Go mechanics shared with caddy, typescript-go and tailscale (BASH_ENV, go-env.sh, the offline toolchain switch)
are in `go-common.md` and only summarised here.

## What I read

| File | Commit(s) | For |
|---|---|---|
| `go.mod` (go/toolchain/godebug lines) | all 24 starts | toolchain pins |
| `.github/workflows/build.yml` | 554ddb5de2, c1b5756eec (go versions, tags) | CI test and lint steps |
| `Makefile` (quicktest, racequicktest, check) | 554ddb5de2, c1b5756eec | the test command |
| `AGENTS.md`, `CLAUDE.md` (present at the newest start, absent at the oldest) | 554ddb5de2 | build/test commands the project gives agents |
| `.golangci.yml` | 554ddb5de2 | which vet analyzers CI runs |
| `.gitignore` | both | what setup/builds may leave in the copy |
| `fstest/fstests/fstests.go` (Run), `fstest/testserver/testserver.go` | 554ddb5de2 | how backend integration tests skip |
| `backend/chunker/chunker_test.go`, `backend/ftp/ftp_test.go` | 6e01cb6e22, 554ddb5de2 | TestIntegration runners |
| `vfs/vfs_test.go` and the vfs test file list | 36ce1a28fe | helpers that hidden tests depend on |
| every hidden test file, at its fix commit, and the test-file patches of rclone-01/05/06/07/10/12/15/19/21/22/23 | fix SHAs | which Test funcs a `-run` selection picks |
| tree size | 554ddb5de2 | copy size |
| the bench: sets.py, sealed.py, grade.py, admit.py, common.py, driver.py, netlock.py | | how commands run |

## Toolchain and pins

- `go.mod`: `go 1.25.0` at rclone-24..rclone-19 (starts up to 2026-08-14), `go 1.26.0` from rclone-18 (2026-08-21) on.
  No `toolchain` line at any start. `godebug x509negativeserial=1` (old) and a `godebug (...)` block adding
  `multipathtcp=0` (new): the go command applies these itself, nothing to do.
- The machine has go 1.24.7, so every start needs a switch: GOTOOLCHAIN=auto downloads go1.25.0 or go1.26.0 at setup
  into `$BENCH_CACHE/gomod` (two toolchains in all). The pin is read from the copy's go.mod at setup time, not
  hard-coded.
- CI builds with newer patch releases (`go: '~1.26.4'` at the oldest start, `'~1.27.4'` at the newest, plus a `go1.26`
  job). GOTOOLCHAIN=auto runs exactly go1.25.0 / go1.26.0, the minimum go.mod names, which CI never ran. Low risk;
  if a hidden test fails only on that, `GOTOOLCHAIN = "go1.26.4+auto"` would bring the bench closer to CI (one more
  download, and that string is literal so it fits the env table).
- Env that makes the switch work offline once downloaded (from the Go 1.24.7 cmd/go source, go-common.md):
  `GOTOOLCHAIN=auto GOPROXY=off GOSUMDB=sum.golang.org GOFLAGS=-mod=mod`, and `GOMODCACHE` the same absolute folder as
  at setup (it holds the toolchain zip and tree and the cached checksum-database lookup and tiles). GOSUMDB must not be
  `off`: the toolchain module is always checked against the checksum database, and `off` turns that into an error.
  GOPATH is left alone (its `pkg/sumdb/latest` must not be shared and moved forward by later setups).
- No build tags: CI builds with `GOTAGS=cmount`, which needs libfuse headers (cgo); without it `cmd/cmount` is simply
  left out of the build. No `-race` (CI's racequicktest is a separate job; no candidate needs it).

## Commands

All commands start with `. "$BENCH_CACHE/go-env.sh"` (GOMODCACHE, GOCACHE under `$BENCH_CACHE`); the env table also
sets `BASH_ENV` to that file so an agent's own bash commands get the same two variables.

| Command | What | Source | Verified? |
|---|---|---|---|
| env | `GOTOOLCHAIN=auto GOPROXY=off GOSUMDB=sum.golang.org GOFLAGS=-mod=mod BASH_ENV=$BENCH_CACHE/go-env.sh RCLONE_CONFIG=/notfound` | Makefile quicktest (RCLONE_CONFIG), Go source | RCLONE_CONFIG yes (CI); the rest reasoned, unverified |
| setup | write go-env.sh; `go version` (toolchain); `go mod download`; `go list -deps -test ./...`; `go build ./...`; `go vet ./...` to warm the build cache (not fatal); restore go.mod/go.sum; fail if the copy is dirty | GO-COMMON, Makefile | unverified |
| test_files | per folder, `go test -count=1 -timeout 20m ./DIR -run '^(names)$'`, names = the `Test/Fuzz/Example` funcs the hidden files define (TestMain left out); a hidden file with no Test func but an `(f *Fs) InternalTest` method runs `TestIntegration`; a file with neither runs the whole package; non-`_test.go` files are skipped; "no tests to run" counts as a failure | Makefile quicktest, AGENTS.md | unverified (dry-run with a stub `go`: names and folders come out right) |
| test_package | walk `{package}` up to the nearest folder with `*.go`; `go test -count=1 -timeout 20m ./P`; for `.`: `go build ./...` then `go test .` (root `rclone.go`, compile only) | Makefile quicktest | unverified |
| package_of | `regex:^(.*?)(?:/testdata/.*|/[^/]*)$` (file's folder cut at testdata; root files give `.`) | | checked in python |
| failed | `^\s*--- FAIL: (\S+)` (top-level and indented subtests) | Go testing output | regex checked on sample lines |
| Rail setup | `go version && go build ./...` (offline; modules and build cache are shared, nothing to copy) | AGENTS.md | unverified |
| Rail verify | gofmt -l of changed .go files; `go build ./...`; `go vet` + `go test -count=1 -timeout 20m` of changed packages (diff against `$RAIL_BASE` plus untracked, `.rail/` and `.claude/` left out) | Makefile quicktest/check, .golangci.yml | unverified (dry-run with stubs: clean tree runs only the build) |

golangci-lint (CI's `check`) is left out of verify: not installed, CI pins `version: latest`, and it would need a
setup download per version. `.golangci.yml` enables govet with all analyzers but fieldalignment and shadow, so plain
`go vet` (the default analyzer set) is a subset CI already keeps clean.

Timeouts: `timeout_minutes = 30` (one command); Rail `setup_timeout_secs = 900`, `verify_timeout_secs = 2400`,
`timeout_secs = 1800`.

## How the hidden tests are picked, situation by situation

All 24 hidden lists are `_test.go` files only; no fix touches testdata, go.mod or go.sum.

- Ordinary: the hidden file defines top-level `TestX` funcs and the new or changed checks are among them: rclone-01,
  02, 03, 04, 05, 06, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24. The selection also runs the
  file's older tests (the whole file), which is what the oracle wants as long as none is red or flaky.
- **rclone-07 (chunker)**: `chunker_internal_test.go` has no top-level Test func. The new check is a subtest of
  `func (f *Fs) InternalTest`, which `fstests.Run` calls from `TestIntegration` in `chunker_test.go` (package
  `chunker_test`). With no `-remote` that test overlays a local temp dir (`QuickTestOK`), so it runs offline. The
  command's fallback turns such a file into `-run '^TestIntegration$'`: the whole chunker integration suite against
  local disk, about 1 to 3 minutes per run, so 10 oracle runs take 10 to 30 minutes. Its temp dir is the fixed
  `$TMPDIR/rclone-chunker-test-standard`: two grades of this situation at once on one TMPDIR would collide.
- rclone-05 and 21/22/23 also change `InternalTest` methods or define them, but their new checks are top-level
  `TestX` funcs, so `TestIntegration` (which needs a configured remote or a docker test server) is not run.
- `TestIntegration` in backends with a real remote skips under `RCLONE_CONFIG=/notfound` ("quicktest only", before
  any docker test server is started), so `test_package` on a touched backend (rclone-05 ftp, rclone-06 pcloud, pikpak,
  zoho, seafile, rclone-09 pikpak, rclone-13 drime, rclone-17 yandex, rclone-21/23 dropbox, rclone-22 drive) runs the
  unit tests only and is quick once compiled.
- No hidden file has a `//go:build` line; no testify suites; Examples are none.

## Clash rule

`clash = "dir"` (the Go default) is kept, with a caveat. Under "dir" the grade MOVES AWAY every arm test file in a
hidden test's folder; it does not put back the start version. rclone keeps shared helpers in other test files of the
same package: `vfs/vfs_test.go` (TestMain, `newTestVFS`) for rclone-11/12, `fs/config` (`testConfigFile`) for
rclone-03, `fs/sync`/`fs/operations` (`fstest.TestMain`, helpers) for rclone-01/20, and `backend/chunker/chunker_test.go`
is the very runner of rclone-07's hidden check. An arm that edits one of those files loses it at grading: the hidden
tests then fail to compile (a false "wrong"), and for rclone-07 the hidden run would find no `TestIntegration` (the
"no tests to run" guard in test_files turns that into a failure instead of a false pass). `path` has the opposite
failure (an arm's new test file that defines a name a hidden file also defines does not compile). Arms usually add
tests to the same file upstream did (same path, set aside under both rules), so both are rare; the right fix is in
the bench: under "dir", restore an arm-modified test file to its start version instead of removing it.

## Expected sizes and times

- Copy: the tree at 554ddb5de2 is 2,844 files, 42 MB; with the one-commit `.git` about 60 to 70 MB per copy. 24
  situations: about 1.6 GB of sealed copies, plus a temporary copy per grade and per run.
- `$BENCH_CACHE`: module cache 1.5 to 2.5 GB (rclone pulls the AWS, Azure, Google API and many other SDKs; estimate),
  two toolchains about 0.5 GB, build cache 2 to 4 GB per Go version, so 6 to 10 GB in all (estimate). This is the
  biggest disk risk of the four Go projects on a 30 GB machine. Dropping the `go vet ./...` warm-up from setup saves
  perhaps 1 GB at the cost of slower first test runs.
- Setup, cold: toolchain and modules 2 to 5 minutes, `go build ./...` 4 to 8 minutes, vet 3 to 5 minutes; warm (same
  Go version already cached) 1 to 3 minutes.
- Test binaries that import `backend/all` (vfs, fs/sync, fs/operations, cmd/*) are large: compiling the package's test
  variant and linking takes 20 to 60 s even with a warm cache.
- Typical `test_package`: fs ~15 s, lib/transform, fs/accounting, fs/walk < 30 s, fs/config ~30 s, fs/sync and
  fs/operations 1 to 2 min, vfs 2 to 4 min, vfs/vfscache ~1 min, backend/local 1 to 2 min, a remote-only backend a few
  seconds after linking. Root `.`: build of everything, about 1 min warm.
- Rail verify on the start commit (nothing changed): `go build ./...`, about 1 minute warm.

## Traps

- **[commands] env is literal** (bench sealed.project_env): GOMODCACHE/GOCACHE cannot be written there as
  `$BENCH_CACHE/...`. Worked around with BASH_ENV (bash expands it at startup and sources go-env.sh); unverified that
  Claude Code's Bash tool and Rail start bash so it is read. If it is not, every `go` command an agent types itself
  uses an empty module cache in the run's HOME and fails offline ("module lookup disabled by GOPROXY=off"). The clean
  fix is a one-line bench change: expand `$BENCH_CACHE` in env values.
- Agents work offline: tests that need the internet fail for them (not for the grade, which has the network). No
  hidden test touches the internet (the googleapis/google.com strings in rclone-21/22/23 are constants, not requests).
  Tests that bind `localhost:0` (httptest, serve restic/http/webdav) work in the bench's namespace, which brings
  loopback up.
- Not on this machine, not in any candidate: FUSE (`cmd/mount`, `cmd/mount2`, `cmd/cmount` with tag), NFS, docker test
  servers, git-annex (`cmd/gitannex` end-to-end). A change in those packages would make `test_package` red at start
  as well (left out by the red-at-start rule) or skipped.
- `.gitignore` lists `rclone` (any path named so) and `*.test`: an agent's `go build` binary (~100 MB at the root) is
  ignored and never in the change, but it is a file, not a folder, so `build_dirs` cannot keep it out of Rail's saved
  stages; stages may grow by 100 MB.
- AGENTS.md at newer starts tells agents to run `make`: the Makefile calls `git describe --tags` and
  `git rev-list --count`, which in the one-commit, tag-less sealed copy print an error and build a strange version
  string; harmless. `make quicktest` (all packages, 10 to 20 minutes) is what an agent may reach for.
- Setup must not change tracked files (the grade diffs against the start commit); it restores go.mod/go.sum if
  `-mod=mod` touched them and fails if anything else is dirty.

## Candidates likely to have trouble at admission

- rclone-07: the hidden check runs only inside `TestIntegration` (whole chunker suite on local disk, minutes per run,
  fixed temp path); slow oracle and the only situation using the InternalTest fallback.
- rclone-08: GC-based weak-pointer check with `Eventually`; 10 of 10 may not hold.
- rclone-12, rclone-19: vfs cache timing (handle-caching grace and 30 s deadlock guards in the same files) under 10
  runs on 4 cores.
- rclone-20: concurrency probe asserting max in flight equals `--checkers`, 10 s deadline: scheduler-sensitive.
- rclone-06: 10 s deadlock timeout; the fix touches five backends, so five `test_package` runs, each linking a big
  binary (several minutes in all).
- rclone-21: the hidden test needs the fix's API (`Fs.srv` as `files.ContextClient`, `GetMetadataContext`): at the
  start it does not compile. That still fails the null run as it should; noted for the "tests use what existed" rule.
- rclone-22: 1 s arrival timeout in the new concurrency test.

## For the admission session to try first

1. Setup on rclone-24 (go 1.25.0) and rclone-01 (go 1.26.0): check both toolchains land in `$BENCH_CACHE/gomod`, then
   `unshare -n env HOME=$(mktemp -d) bash -c 'cd COPY && go version && go test -count=1 ./lib/transform'` works with
   the network gone (the offline toolchain switch and module cache).
2. In the same namespace, `bash -c 'echo $GOMODCACHE'` with only the env table set: confirms BASH_ENV; then the same
   through Claude Code's Bash tool in one agent run.
3. rclone-07's test_files (the TestIntegration fallback): time it and run it twice in parallel.
4. rclone-08, 12, 19, 20: the ten oracle runs (flakiness).
5. Rail verify in a fresh `.claude/worktrees/NN` worktree, offline, with a one-line change in `vfs/` (time it).
6. Disk: `du -sh $BENCH_CACHE/*` after setups of both Go versions.
