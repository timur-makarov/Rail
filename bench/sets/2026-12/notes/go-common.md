# Shared Go design for the four bench projects (caddy, typescript-go, rclone, tailscale)

Facts from reading the bench (bench-sets/bench/*.py):
- `[commands] env` values are set LITERALLY (sealed.project_env: env.update(project.commands["env"]), no expansion).
  So `GOMODCACHE = "$BENCH_CACHE/gomod"` would reach Go as a relative path; Go refuses it
  ("GOMODCACHE entry is relative; must be absolute path"). Agents' children get HOME = the run's own home, so the
  Go defaults (GOPATH=$HOME/go, GOMODCACHE=$HOME/go/pkg/mod, GOCACHE=$HOME/.cache/go-build) are EMPTY in agent runs
  and with GOPROXY=off every `go` command the agent types fails ("module lookup disabled by GOPROXY=off").
- Workaround with no bench change: env `BASH_ENV = "$BENCH_CACHE/go-env.sh"`. bash (non-interactive, `bash -c` and
  `bash -lc`) EXPANDS BASH_ENV and sources that file at startup (checked locally: works with -c and -lc, silent when
  the file is missing, nested bash too; `sh`/dash ignores it). Setup writes the file (constant content, safe to share
  in $BENCH_CACHE), with single-quoted heredoc so `$BENCH_CACHE` expands at source time:
      export GOMODCACHE="$BENCH_CACHE/gomod"
      export GOCACHE="$BENCH_CACHE/gocache"
  Every TOML command ALSO starts with `. "$BENCH_CACHE/go-env.sh"` (explicit, works even if BASH_ENV is not honoured).
  Unverified: that Claude Code's Bash tool (and Rail's command runner) start bash so BASH_ENV is read. The clean fix
  is a bench change: expand `$BENCH_CACHE` in [commands] env values (then GOMODCACHE/GOCACHE go in env directly).
- The plain arm's prompt shows test_files, test_package, Rail setup and verify VERBATIM: keep them readable.
- Every later use is a copytree at another path: nothing absolute may be recorded in the copy (Go records nothing).
- Setup must not leave tracked files modified (grade diff vs start commit includes them, and the patch would then not
  apply to a fresh copy that already has setup's edits): end setup with a check/restore of go.mod/go.sum.
- `go test ./...` / `go build ./...` ignore directories starting with "." or "_" and `testdata`, so `.claude/worktrees`
  and `.rail` inside the copy are never walked.
- grade clash: with clash="dir" the arm's test files in a hidden test's folder are MOVED AWAY (deleted from the tree),
  not reverted to the start version. If hidden tests use helpers/TestMain from another _test.go file in that folder
  that the arm edited, the package no longer compiles. Report as a bench caveat; ideal is "revert to start, delete if
  new".

Toolchain (Go source read at go1.24.7: cmd/go/internal/toolchain/select.go, modfetch/fetch.go, modfetch/sumdb.go):
- GOTOOLCHAIN=auto: when go.mod's `go`/`toolchain` line is newer than 1.24.7, cmd/go downloads module
  golang.org/toolchain@v0.0.1-goX.Y.Z.linux-amd64 into GOMODCACHE via modfetch.Download.
- modfetch.download returns the extracted dir from the cache with no network. checkMod then checks the ziphash:
  a toolchain module can never be in go.sum, and useSumDB() returns TRUE for golang.org/toolchain EVEN WHEN
  GOSUMDB=off — and with GOSUMDB=off dbDial fails ("checksum database disabled by GOSUMDB=off"). So GOSUMDB must stay
  `sum.golang.org` (set it explicitly: distro go.env files may set off).
- The sumdb client reads cached lookups and tiles from GOMODCACHE/cache/download/sumdb (written at setup) and only
  calls ReadRemote (initBase, which consults GOPROXY) when something is not cached. So offline works with GOPROXY=off
  once the same GOMODCACHE holds the toolchain.
- Caveat: the "latest" signed tree head is kept in GOPATH/pkg/sumdb (NOT in GOMODCACHE). If GOPATH is shared and a
  later setup moved it forward past the cached record's tree, the client must prove consistency with tiles it may not
  have -> network. So DO NOT set GOPATH into $BENCH_CACHE; leave it per process (agent runs: fresh HOME -> empty
  latest -> fine; bench grade: network on -> fine). Admission's offline check should use a fresh HOME.
- Env that makes the switch work offline after one download:
  GOTOOLCHAIN=auto, GOPROXY=off, GOSUMDB=sum.golang.org, GOMODCACHE=<the same absolute dir as at setup>,
  GOFLAGS=-mod=mod, GOPATH unset/per-run.
- Setup overrides GOPROXY for itself: `export GOPROXY=https://proxy.golang.org,direct`.

Env table used by all four (literal values only):
  GOTOOLCHAIN = "auto", GOPROXY = "off", GOSUMDB = "sum.golang.org", GOFLAGS = "-mod=mod",
  BASH_ENV = "$BENCH_CACHE/go-env.sh", GOTELEMETRY = "off"? (telemetry writes only to the user config dir; leave it)

Setup skeleton (bash):
  set -euo pipefail
  mkdir -p "$BENCH_CACHE"
  t=$(mktemp "$BENCH_CACHE/.go-env.XXXXXX")
  printf '%s\n' 'export GOMODCACHE="$BENCH_CACHE/gomod"' 'export GOCACHE="$BENCH_CACHE/gocache"' > "$t"
  mv -f "$t" "$BENCH_CACHE/go-env.sh"
  . "$BENCH_CACHE/go-env.sh"
  export GOPROXY=https://proxy.golang.org,direct
  go version                       # fetches the toolchain go.mod asks for
  go mod download
  go list -deps -test ./... >/dev/null          # every module a build or test of any package needs
  go test -count=1 -exec /bin/true ./... >/dev/null   # compiles and links every test binary, runs none: warm GOCACHE
  git diff --quiet -- go.mod go.sum || { git diff --stat; git checkout -- go.mod go.sum; }

test_files (one `go test` per folder, only the Test/Fuzz/Example funcs the hidden files define):
  for each f in {files}: skip non-*_test.go (testdata etc. just travel), skip missing; dir=$(dirname f);
  names += grep -ohE '^func (Test|Fuzz|Example)[A-Za-z0-9_]*\(' f ; then per dir:
  go test -count=1 "./$dir" -run "^(A|B)$" ; a dir with hidden files but no names -> run the whole package (helpers
  only). Collect failures, exit 1 if any.
failed = '^\s*--- FAIL: (\S+)'  (subtests are indented; panics print --- FAIL before the trace)
package_of = 'regex:^(.*?)(?:/testdata/.*|/[^/]*)$'  (folder of the file, cut at testdata; root files -> ".")
test_package: walk {package} up to the nearest folder holding *.go, then `go test -count=1 "./$p"`.
Rail setup: source env, `go build ./...` (offline; checks toolchain + modules). Rail verify: gofmt -l on changed .go,
  go build ./..., go vet + go test -count=1 of the changed packages (git diff --name-only "$RAIL_BASE" plus
  git ls-files --others --exclude-standard, minus .rail/ and .claude/).
