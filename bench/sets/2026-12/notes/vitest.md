# vitest (vitest-dev/vitest): bench settings

Files: `vitest.toml` (project, commands, Rail commands), `vitest.travel.json` (which changed files are hidden tests).
Written by reading only; nothing was installed, built or run. Shared decisions: `../../ts-tools/COMMON.md`
(two deviations, below).

## What I read

At the newest start `68dc42ccc9ac8ee74b71416b659630296ee97e9b` (vitest-01) and the oldest start
`d758b4755dc7534118fa0f62f16758881a8a6123` (vitest-35), via `gh api`:

- `package.json`, `pnpm-workspace.yaml`, `.npmrc`, `.gitignore`, `.github/workflows/ci.yml`,
  `.github/actions/setup-and-cache/action.yml`, `.github/actions/setup-playwright/action.yml`
- `CONTRIBUTING.md`, `AGENTS.md`, `test/README.md`
- `test/{e2e,unit,coverage-test,node-runner,typescript,workspaces,browser}/package.json`,
  `test/e2e/vitest.config.ts`, `test/unit/vite.config.ts`, `test/coverage-test/vitest.config.ts`,
  `test/test-utils/index.ts`, `packages/vitest/package.json`, `packages/vitest/vitest.mjs`, `packages/ui/package.json`
- vitest source for the output format and filters: `packages/vitest/src/node/reporters/base.ts` (printTaskErrors),
  `.../reporters/renderers/utils.ts` (formatProjectName), `.../projects/globProjectFiles.ts` (filterTestFiles),
  `.../config/resolveConfig.ts` (`--project '!x'` negation exists at both starts), `src/defaults.ts`,
  `src/utils/env.ts`; std-env `src/agents.ts` (agent detection).
- Full git trees at both starts (tracked `dist`/`node_modules` folders, test layout, fixtures).
- CI job logs: 139492536662 (e2e, failing, Windows: the ` FAIL ` line), 139492536640 (unit, build timing),
  139178698988 (e2e, node 22, Ubuntu: all pass, 355 s), 139178699315 (coverage, 199 s), 139178698938 (unit, 63 s).
- The pnpm v11.0.0 release notes (settings, env prefix, verifyDepsBeforeRun, trustPolicy).
- The 35 candidates' file lists in `bench-sets/files/vitest/`.

## Toolchain and pins

| | oldest start d758b47 | newest start 68dc42c |
|---|---|---|
| packageManager | pnpm@11.6.0 | pnpm@11.28.6 |
| engines.node | ^22.12.0 \|\| ^24.0.0 \|\| >=26.0.0 | same |
| vitest version | 5.0.0-beta.6 | 5.1.1 |
| lint script | `eslint --cache .` (@antfu config) | `oxlint && oxfmt --check` |
| build script | `pnpm -r --filter @vitest/ui --filter='./packages/**' run build` | same |
| test layout | test/e2e, test/unit, test/coverage-test, test/node-runner, ... | same |

No `.nvmrc`/`.node-version`/`devEngines`. The machine's node 22.23.5 satisfies engines. CI runs unit and coverage
only on node 24/26; node 22 gets only an e2e leg (which passes in full). setup reads the pnpm pin from the copy, so
both pnpm versions work. `.npmrc`'s `VITEST_MODULE_DIRECTORIES` is not passed on by pnpm 11 (it stopped exporting
`npm_config_*` to scripts), so CI runs without it too; my commands match.

## The commands

All commands put `$BENCH_CACHE/pnpm/$V/bin` first on PATH (V from `packageManager`), so nested `pnpm` calls inside
package scripts (`premove dist && pnpm build:node ...`) use the pinned pnpm too.

| command | what | status |
|---|---|---|
| setup | npm-install `pnpm@V` into `$BENCH_CACHE/pnpm/V`; `pnpm install --frozen-lockfile --store-dir $BENCH_CACHE/pnpm-store --filter '!docs'` (CI's filter, with dependency build scripts as CI runs them); Playwright chromium headless shell into `$BENCH_CACHE/ms-playwright` (+ `install-deps` as root); `pnpm run build`; write the build stamp | install/build/playwright steps are CI's; pnpm-by-npm, store dir and install-deps **unverified** |
| test_files | stamp-gated rebuild; group `{files}` by suite; run `CI=true node <root>/packages/vitest/vitest.mjs run FILES` from `test/SUITE` (node-runner: `node --test --test-reporter=tap FILES`; `packages/ui/...spec.ts` from packages/ui) | form from AGENTS.md ("CI=true cd test/<folder> && pnpm test <file>"); the wrapper logic **unverified** |
| test_package | rebuild; packages/coverage-* -> test/coverage-test; packages/ui -> packages/ui's vitest; any other packages/* -> test/unit + test/e2e; test/SUITE -> that suite; `.` (docs, lockfile, root config) -> test/unit | suites run as CI's test:ci:* do; the mapping is a choice, **unverified** |
| package_of | `regex:^((?:packages|test)/[^/]+)/` | checked with the bench loader on sample paths |
| failed | ` FAIL  [label  \| \|label\| ]NAME[ (attempts)][ [ file ]]` and TAP `not ok N - NAME` | vitest branch checked against base.ts and a CI log; TAP branch **unverified** |
| Rail setup | `cp -al` every node_modules folder of the main checkout (skips .claude, skips folders that exist or whose parent does not), offline install only if node_modules is missing or the lockfile changed, then the stamp-gated build | **unverified** |
| Rail verify | rebuild; `pnpm run lint`; `pnpm run typecheck` (CI's lint job); test/unit always; + test/e2e when packages/* other than coverage/ui changed; + test/coverage-test for coverage packages; + packages/ui; + any changed test/e2e, coverage-test, node-runner | steps are CI's; the affected choice **unverified** |

### The build, and why every test command rebuilds

Every suite imports `vitest` through workspace links whose `exports` point at `dist/` (AGENTS.md: "Tests execute
built output ... rebuild before re-running tests"; `vitest` also inlines @vitest/utils/expect/snapshot/spy/
pretty-format source at build time; `@vitest/mocker` is a separate runtime dependency). So a source change is
invisible until rebuilt. Each test command computes a stamp:
`sha256(git rev-parse HEAD:packages + git diff HEAD --binary -- packages + sha256 of untracked files under packages)`
and runs the full `pnpm run build` when the stamp differs from `node_modules/.bench-build` or
`packages/vitest/dist/cli.js` is missing. The full build is about 18 s on CI's 4-core runner (12-18 s in three logs);
expect 20-60 s here. With the stamp, the oracle's ten hidden runs build once. The stamp file is written
tmp-then-`mv` (and the log `rm`ed first) because a Rail worktree's node_modules files are hard links to the main
checkout's. A build failure exits 2 with no test named, which the grade counts as wrong (correct for a change that
breaks the build). `dist/` is gitignored, as are `.vitest`, `coverage`, `*.tsbuildinfo`, `.cache`; the build
regenerates some tracked files (LICENSE.md files, packages/ui `auto-imports.d.ts`), which CI checks are unchanged
after a build at every commit; setup prints `git status --porcelain` so the admission session can see if not.

### Deviations from COMMON.md

1. **No `NO_COLOR` in env.** CI runs every suite with `CI=true`, which turns tinyrainbow/picocolors colour ON;
   some tests may depend on that state (test-utils disables colour for inner runs, but outer test files are not
   all known). Instead, test commands pipe vitest's output through `sed` to strip ANSI codes, so `failed` sees
   plain text while the tests run exactly as in CI. `pipefail` keeps vitest's exit code.
2. **pnpm is used at test time**, for `pnpm run build` (package scripts call `pnpm` themselves). It is the pinned
   pnpm, with `PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false` (pnpm 11 defaults it to `install`, which would try an
   install; with a `--filter '!docs'` install the workspace state likely looks incomplete to it) and
   `PNPM_CONFIG_TRUST_LOCKFILE=true` (as CI; trustPolicy `no-downgrade` otherwise verifies the lockfile against the
   registry). Uppercase `PNPM_CONFIG_*` follows CI's own spelling.

Also: every test command unsets `CLAUDECODE`, `CLAUDE_CODE`, `AI_AGENT` (std-env agent detection makes vitest
switch its default reporter to `minimal` and `watch` off; inner e2e runs expect CI behaviour), and `GITHUB_ACTIONS`
(test/unit picks the github-actions reporter on it).

## Sizes and times (estimates)

- Tracked tree 37 MB (newest). Lockfile 640 KB (about 1,500 packages, including Playwright, webdriverio drivers,
  @swc/core, sass-embedded, rolldown/oxc bindings, workerd via wrangler). Expect node_modules 1.0-1.6 GB, dist
  about 30 MB. **One copy: about 1.2-1.7 GB.** The sealed copy itself is mostly hard links into
  `$BENCH_CACHE/pnpm-store` (pnpm on ext4 hardlinks), so 35 sealed copies cost little; every `copytree` copy
  (admission, grade, each run) is a full 1.2-1.7 GB. A Rail worktree costs little (cp -al) plus its dist.
- `$BENCH_CACHE`: pnpm store 1.5-2 GB, Playwright chromium headless shell about 250 MB, pinned pnpm about 25 MB per
  version (two or more versions across the window).
- setup: cold 5-10 min (download, dependency build scripts incl. edgedriver/geckodriver downloads, apt deps,
  chromium, build); warm store 1.5-3 min.
- test_files: build 20-60 s once, then seconds to 2 min per e2e file (e2e testTimeout is 60 s; some e2e files take
  tens of seconds); a unit file runs in three pools (threads, forks, vmThreads).
- test_package for packages/vitest: build + test/unit (63 s on CI) + test/e2e (355 s on CI, maxWorkers 2) = about
  8-12 min here; coverage packages: about 4-5 min; `.`: about 2 min. A grade (3 rounds) of a packages/vitest fix:
  30-40 min; vitest-08 touches packages/expect and packages/vitest, so it runs unit+e2e twice per round.
- Rail verify on the start commit: build + lint + typecheck + test/unit, 5-7 min; with packages/* changed add e2e,
  12-16 min. Timeouts: verify 1800 s, setup 900 s.

## Traps

- **Built packages.** Covered by the stamp-gated build in every command (above). If the build ever writes outside
  gitignored folders, agents' diffs would carry it.
- **pnpm self-switching.** The machine's pnpm 10.28 would try to download 11.x into the agent's per-run HOME;
  `npm_config_manage_package_manager_versions=false` stops it. Agents that run plain `pnpm` get 10.28, which can
  run scripts but must not `pnpm install` (store v10 is empty; pnpm 11 uses store v11 with SQLite index.db).
  The commands given to agents use the pinned pnpm.
- **Browser mode.** CI installs chromium headless shell for unit/e2e/coverage. test/coverage-test's
  `istanbul-browser`/`v8-browser` projects include many generic files (`**/results-snapshot.test.ts`,
  `**/all.test.ts`, ...), so running such a file runs it in chromium too (vitest-34). e2e has `browser`-tagged tests.
  Ubuntu 24.04 needs the chromium system libraries: setup runs `playwright install-deps chromium` as root (apt,
  machine-wide, unverified). If that fails, those tests fail at the start and with the fix alike. Fallback: add
  `--project '!*-browser'` to coverage-test runs (negation exists at both starts).
- **Tracked node_modules.** `test/e2e/project-references/packages/project-b/node_modules` (both starts) and
  `test/browser/fixtures/dep-imports-vitest/node_modules` (newest) are tracked, so the default build_dirs
  (`node_modules`) drop them from saved stages; restore copies them back from the sealed copy for the root, and
  Rail's setup copies the main checkout's into a restored worktree (it skips folders that exist). No tracked
  `dist`. Do not add `coverage` or `.cache` to build_dirs (tracked source/fixtures use those names).
- **Agent detection.** std-env treats `CLAUDECODE`/`CLAUDE_CODE` as an agent: vitest's defaults change. The bench
  itself may run from a Claude Code session; test commands unset them.
- **Filters are substrings.** vitest keeps a test file when its path relative to the suite contains the filter, so
  `test/caching.test.ts` would also pick any longer path ending in it (none seen). The e2e `snapshots` project
  (root `test/e2e/snapshots`) also sees the filters.
- **Git-driven e2e tests.** `test/git-changed.test.ts`, `list-changed`, `setup-files`, `watch/related` run
  `--changed` against tracked fixtures, serially. In a copy the hidden tests and the fix are uncommitted changes
  in the same repository; if these tests look at the whole repository's diff they may see them.
- **Ports.** test/unit uses fixed ports 3022/3023 (server, api). Two runs at once on one machine (an agent's test
  run beside Rail's verify) could collide.
- **Network at test time.** None found in the configs; the e2e suite was not audited file by file (1,800 tests).
- **node 22.** unit and coverage are not run on node 22 by CI; a test that needs node 24 would be red at the start
  (discounted by name in test_package, but it would break verify, which must pass at the start).
- **Flaky.** The e2e suite has timing and process tests (a Windows CI run failed
  `fs-module-cache-resiliency.test.ts` on ENOTEMPTY); package runs of e2e three times per grade will meet flakes
  that were not red at the start.

## Candidates that look unlikely to pass admission

- vitest-18: the fix adds a `file:` dependency to `test/e2e/package.json` (hidden) and changes `pnpm-lock.yaml`
  (source part). test_files reinstalls offline (`--offline --frozen-lockfile --ignore-scripts`) when the lockfile
  differs from HEAD; this is unverified and an agent cannot do the same offline unless it also edits the lockfile.
- vitest-04: kills pool workers and polls liveness for 5 s; 10/10 on a loaded 4-core box is doubtful.
- vitest-02: 100 ms timeouts in the hidden test; timing-sensitive under load.
- vitest-06: watch-mode e2e (file watcher); flaky by nature.
- vitest-13: WeakRef + forced GC retry loop (the candidate notes call it a small flake risk).
- vitest-15, vitest-33: in the serial git-driven project; see the git trap.
- vitest-24: detects a spawned-pipe leak; environment-dependent output.
- vitest-34, vitest-07, vitest-16: coverage-test; vitest-34 also runs in the browser projects (chromium).
- vitest-35: oldest start (pnpm 11.6.0, eslint lint); exercises browser config with `preview()`/playwright
  providers; probably resolution-only but may launch chromium.
- vitest-22: the only node-runner (node --test) case; the TAP form of `failed` is unverified.

## For the admission session to try first

1. On vitest-01 (newest) and vitest-35 (oldest): run setup; check `pnpm --version` = pin, `git status --porcelain`
   empty, `packages/vitest/dist/cli.js` present, `$BENCH_CACHE/ms-playwright` holds a chromium headless shell.
2. In a copytree copy, under `unshare -n`: test_files on `test/e2e/test/global-setup.test.ts` (fails at start),
   then apply the fix and run it twice (second run must skip the build). Look at the ` FAIL ` lines after colour
   stripping and check `failed` picks them.
3. vitest-27 (fixture-only hidden test: the importer fallback must pick timers-node/timers-jsdom.test.ts) and
   vitest-22 (node --test TAP output and `failed`).
4. test_package `packages/vitest` on a start commit, offline: time it and list what is red at the start on node 22.
5. Rail setup + verify on the start commit (copy root), then in a `git worktree add .claude/worktrees/01` worktree
   offline: cp -al time, build time, that `pnpm run lint` and `pnpm run typecheck` pass at both starts.
6. vitest-34 (coverage + browser projects) to see whether chromium runs on the machine; if not, add
   `--project '!*-browser'` for test/coverage-test.
7. vitest-18 for the offline reinstall path, or drop it.
