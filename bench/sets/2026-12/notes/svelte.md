# svelte (sveltejs/svelte): bench settings

Written by reading only, 2026-11-26. Files: `svelte.toml`, `svelte.travel.json`. Shared choices for the four
TypeScript projects: `../../ts-tools/COMMON.md`; svelte follows them with no deviation.

## What I read

At the newest start `b1a066c2fd09` (svelte-01) and the oldest `2bace308e37a` (svelte-26):
`package.json` (scripts, `packageManager`, devDependencies), `pnpm-workspace.yaml`, `.gitignore`,
`packages/svelte/tests/.gitignore`, `vitest.config.js`, `vitest-reporter.js` (newest only),
`packages/svelte/tests/suite.ts`, `.github/workflows/ci.yml`, `.github/actions/setup/action.yml` (newest),
`packages/svelte/package.json` (scripts, exports), `packages/svelte/tsconfig.json`, `tsconfig.runtime.json`,
`tests/types/tsconfig.json`, the runner `test.ts` of every suite (newest), `tests/runtime-legacy/shared.ts`,
`tests/helpers.js`, `tests/snapshot/test.ts`, `tests/runtime-browser/test.ts` and `test-ssr.ts`,
`playgrounds/sandbox/package.json` and its `scripts/create-app-svelte.js` and `.gitignore`, both `pnpm-lock.yaml`,
the full git trees of both commits. One CI job log: run 45648562832, job 139326289482 ("Tests (24, ubuntu-latest)",
vitest 4.1.11, one failing snapshot test), for the `failed` form and the run time. The 26 file lists in
`bench-sets/files/svelte/`.

## Toolchain and pins

| | oldest 2bace308e37a | newest b1a066c2fd09 |
|---|---|---|
| pnpm (`packageManager`) | 10.4.0 | 10.33.4 (+sha512) |
| node | no `.nvmrc`; `engines` only `pnpm >=9`; vitest 4 needs node 20+ | same |
| vitest | ^4.1.7, `reporters: ['dot']`, no projects | ^4.1.11, own reporter `vitest-reporter.js` (a DefaultReporter that prints failures only), 8 projects (svelte; runtime-runes in 4 shards + an `inspect-trace` shard; runtime-legacy in 3 shards; custom-renderer-server) |
| lockfile | v9.0, ~502 packages | v9.0, ~510 packages |
| formatter | prettier | `@rsvelte/cli` (native) |

The machine's node v22.23.5 fits. Setup reads the pnpm pin from the copy and installs exactly that pnpm with npm into
`$BENCH_CACHE/pnpm/<version>`; the store is `$BENCH_CACHE/pnpm-store` (store v10 for both pins). No dependency
build scripts run (pnpm 10 default, no `onlyBuiltDependencies`/`allowBuilds` in either commit; CI is the same);
the only lifecycle script is `playgrounds/sandbox` `prepare`, which writes `playgrounds/sandbox/src/main.svelte`
(gitignored by `playgrounds/sandbox/.gitignore` `/src/*`). No git hooks are installed. No build is needed before the
tests: `packages/svelte/package.json` `exports` point at `src/*.js`, and CI runs `pnpm test` straight after
`pnpm install`.

## The commands

- **setup** (unverified: the pnpm-into-cache step and `--store-dir` are ours; the install itself is CI's
  `pnpm install --frozen-lockfile`). Network needed: npm registry for pnpm and the packages.
- **test_files** (unverified as a whole; built on `tests/suite.ts`, read at both starts). Svelte's suites are
  folders of samples run by one `test.ts` per suite, and `suite.ts` reads `FILTER`: `FILTER=name` runs only the sample
  folder named exactly `name` (the `/x/` form is a literal substring, so no alternation: one run per sample name).
  The command maps each listed file:
  `packages/svelte/tests/<suite>/samples/<name>/...` -> `FILTER=<name> vitest run packages/svelte/tests/<suite>/test.ts`
  (`samples-dom` -> `test-dom.test.ts`; `runtime-browser/samples` -> `test-ssr.ts`, the jsdom half;
  `runtime-browser/custom-elements-samples` -> `test.ts`, which needs chromium); plain `*.test.ts`, `tests/*/test.ts`
  and `src/**/*.test.ts` run as files with no FILTER; `tests/types/**` runs `tsc` there; anything else (helpers,
  `.json`/`.css` outside a sample) is reported and skipped. Samples of one name in two suites share one run. A run
  that exits 0 with no passed test (FILTER matched nothing) counts as a failure, so a mapping slip cannot pass the
  null check. `CI=true` as in CI; `NO_COMPILE_CACHE=true` turns off the `_output/<generate>/info.json` compile cache
  in `tests/helpers.js` (mtime-based; harmless in fresh copies, off for safety in the oracle's ten runs).
  Tested against a stub vitest on six lists made from real candidates (bash 3.2 compatible; no associative arrays).
  At the newest commit the runtime-runes file is in five projects; FILTER leaves the sample in exactly one shard and
  the others add one skipped `[SKIP] …` test each, so the summary reads "N passed | M skipped".
- **test_package** (unverified: dropping `runtime-browser/test.ts` is ours). `package_of =
  regex:^(packages/[^/]+|\.changeset|playgrounds/[^/]+|documentation|benchmarking)/`. Every fix adds a
  `.changeset/*.md`, which gives `.changeset`: the command exits 0 for `.changeset`, `documentation`, `benchmarking`
  and `playgrounds/*` (no tests there). `packages/svelte` and `.` (root files such as `vitest.config.js`) run the
  whole svelte suite with positional filters for `packages/svelte/src/`, every `packages/svelte/tests/<suite>/`
  except `runtime-browser/`, `tests/*.test.ts`, and `runtime-browser/test-ssr.ts`. Leaving out
  `runtime-browser/test.ts` is the only cut: it launches playwright chromium in `beforeAll` (CI runs
  `pnpm playwright install chromium`; the machine has no browser and agents are offline). CI log: the whole suite,
  8561 tests in 48 files, took 45 s on a 4-vCPU GitHub runner (`Duration 45.18s`), so expect about 1 to 2 min.
- **failed**: `^ *FAIL\b[^\n]*?\s((?:packages|playgrounds)/[^\s\[]+\.[cm]?[jt]s(?: > [^\n]*?)?)(?: \[[^\n]*\])?[ \t]*$`.
  Checked against the CI log line ` FAIL   svelte  packages/svelte/tests/snapshot/test.ts > async-parallel-deriveds`
  (colour badge, escape codes stripped), and in python against the NO_COLOR form `|svelte| `, a shard label
  `|runtime-runes (1/4)| `, the oldest form with no label, nested describes, `src/**/*.test.ts`, and a file-level
  failure `… test.ts [ … ]` (named by its file). The name leaves out the project label on purpose: which shard a
  sample lands in moves when samples are added. Names look like
  `packages/svelte/tests/runtime-runes/test.ts > transition-each-mixed-completion (dom)` (sample, then variant:
  dom, hydrate, ssr, async-ssr). The per-file `×` lines carry a duration and are not matched.
- **env**: COMMON.md's set only. Not `CI` (put in front of the test commands instead), not `SVELTE_NO_ASYNC`
  (it skips the async variants), not `FILTER`, which the package and verify commands also `unset`.
- **Rail setup** (unverified): hard-links (`cp -al`) every `node_modules` folder of the main checkout (root,
  `packages/svelte`, `playgrounds/sandbox`) into the worktree; pnpm's links inside are relative, so `svelte`
  (`workspace:^`) resolves to the worktree's own `packages/svelte`. Nothing to build. Does nothing in the main checkout
  (admission). Fallback: `pnpm install --offline --frozen-lockfile` from the store. Seconds; offline.
- **Rail verify** (unverified): the `check` script of `packages/svelte` (`tsc -p tsconfig.runtime.json`, `tsc`,
  `tsc` in `tests/types`; CI's Lint job runs it as `pnpm -r check` after `pnpm build`, the TSGo job runs the tsgo form
  with no build first), then the same whole svelte suite as test_package. It is "affected-aware" only trivially:
  `packages/svelte` is the only package with tests, the suite takes 1 to 2 min, and running it every time also proves
  it green at admission. Expect about 3 to 6 min (tsc is single-threaded over src, scripts and every sample
  `_config.js`). It prints the changed files against `$RAIL_BASE` for the log. No lint (eslint and the formatter
  differ between the starts: prettier at the oldest, `@rsvelte/cli` at the newest) and no `pnpm build` (it rewrites
  tracked generated files).

## Sizes and times

- Source tree ~8 MB of blobs (14.4k files at the newest), so a copy's tree plus its one-commit `.git` is ~20 MB.
- node_modules (estimate from the lockfile: typescript 5.5, playwright-core without browsers, two esbuild and
  lightningcss platform binaries, rollup, jsdom, eslint + typescript-eslint, vite 7, vitest 4, `@rsvelte/cli`
  native at the newest): ~250 to 350 MB, ~30k files. The sealed copy itself is hard-linked to the store, so it is
  cheap; every `shutil.copytree` copy is a real ~300 MB copy (seconds to copy). Rail worktrees add almost nothing
  (hard links to the run's own copy).
- `_output/` folders: each sample run writes compiled code next to the sample (gitignored); a full-suite run leaves
  some tens of MB in the copy. `_output` is in `build_dirs` so saved stages skip it.
- Times on 4 cores: setup ~1 to 3 min (pnpm download + ~510 packages); test_files ~5 to 15 s per sample name
  (vitest start, jsdom); test_package ~1 to 2 min; Rail setup seconds; verify ~3 to 6 min.

## Traps

- **Absolute paths**: none needed. Commands call `node node_modules/vitest/vitest.mjs` and
  `node node_modules/typescript/bin/tsc` (pnpm's `.bin` shims embed an absolute `NODE_PATH` of the setup folder,
  which no longer exists after the rename; we do not use them). pnpm's symlinks are relative.
- **Network at test time**: none, once `runtime-browser/test.ts` is left out. The agent's own `pnpm test` runs it
  and it fails with no chromium; the agent should use the given commands.
- **The agent's `pnpm`** is the machine's 10.28; with `npm_config_manage_package_manager_versions=false` it does not
  try to download the pin, and `pnpm test`/`pnpm vitest` work, but `pnpm install` offline would miss the store.
- **Generated files**: `packages/svelte/types/index.d.ts` and `src/internal/*/errors.js`/`warnings.js` are generated
  but tracked; svelte-20's fix changes `types/index.d.ts` (it stays in the source change, `never` keeps it there).
- **Shards** (newest): a sample's shard depends on its position among all sample folders, so the project label in
  output moves; `failed` leaves it out.
- **Compile cache**: `tests/helpers.js` `compile_directory_cached` reuses `_output` when it is newer than the
  compiler's sources and the sample's files (mtime). A fresh copy has no `_output`; test_files turns the cache off.
- **Flaky**: CI marks browser tests "brittle"; they are not run. Dev-mode tests that hit
  `effect_update_depth_exceeded` are slow (testTimeout 30 s in the config). No other flakiness seen.
- **Tests red at the start**: CI on main is usually green (the failing runs I listed were PRs); the one push run
  read failed only its Lint job.

## Candidates

All 26 hidden test lists match what `svelte.travel.json` gives from the fix's file lists (checked by script). None
touch `runtime-browser`, `types`, or support files. Ones to watch:

- svelte-02, svelte-08, svelte-12: hidden test is the whole `tests/signals/test.ts` (and a new `batch.test.ts`); every
  test in the file must pass ten times with the fix, a larger target than one sample.
- svelte-03, svelte-18, svelte-19: the fix changes existing samples' expected files; the null run must fail on at
  least one of them (it should: the old expectation is what the start produces only if the bug is visible there).
- svelte-20: the fix also changes the generated `packages/svelte/types/index.d.ts`; it stays in the oracle's source
  change, so Rail's verify `tsc` sees it with the fix, and an agent need not regenerate it to pass.
- svelte-06: three suites (compiler-errors, parser-modern, validator) -> three vitest runs.
- svelte-26 (oldest start, pnpm 10.4.0): the only situation on the oldest pnpm and on the pre-shard config.

## For the admission session to try first

1. On svelte-01 (newest) and svelte-26 (oldest): run setup, then
   `node node_modules/vitest/vitest.mjs run packages/svelte/tests/runtime-runes/test.ts` with
   `FILTER=<a sample name>` and `NO_COLOR=1 CI=true`; look at the FAIL/summary lines (label `|runtime-runes (1/4)|`?)
   and check `failed` against a real failure.
2. The test_package command on the start commit: confirm runtime-browser/test.ts is not collected and the run is green
   (or note which tests are red at the start).
3. Rail's verify on the start commit: the three `tsc` runs without `pnpm build` first. If one fails at the start,
   drop that `tsc` line (keep the tests) and note it.
4. Rail's setup in a new worktree with the network off: `cp -al` works (same filesystem) and
   `node node_modules/vitest/vitest.mjs --version` runs there.
5. svelte-02 (signals): ten oracle runs of the whole `tests/signals/test.ts`.
