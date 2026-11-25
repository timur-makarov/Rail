# vue-core (vuejs/core): bench settings, how they were found

Files: `vue-core.toml` (project, commands, Rail's commands), `vue-core.travel.json`. Everything was worked out by reading
(`gh api`, the npm registry, three public CI job logs). Nothing was cloned, installed or run, apart from a few local checks:
- the TOML loads with the bench's own `sets.load`, with a dummy situation added;
- every command passes `bash -n`;
- `test_files` and `test_package` were run with bash 3.2 against a stub `vitest.mjs` that prints its arguments, on the
  file lists of vue-core-02, -21 and -28, a list holding only a helper file, and a list with no test file;
- Rail's `setup` was run in a toy git repo with a `.claude/worktrees/01` worktree and pnpm-style relative links (the
  links resolved, the files were hard links, `git status` stayed clean);
- the `failed` regex was checked on sample lines and the real CI line;
- the travel globs give back exactly the candidate file's `hidden_tests` for all 34 situations.

## The two branches

The 34 candidates come from two branches of vuejs/core, and each branch has its own toolchain. Read each start's
`package.json` `version` to tell them apart:

| | main (3.5.x) | minor (3.6 beta/rc, vapor) |
|---|---|---|
| situations | 01-14, 16, 17, 25-28, 32 | 15, 18-24, 29-31, 33, 34 |
| pnpm pin (`packageManager`) | 11.9.0 (-32) .. 11.13.0, 11.27.0, 12.4.2, 12.11.2, 12.16.1 (-01..-04) | 11.5.2 (-33, -34) .. 11.13.0, 11.19.0, 12.4.2 (-15) |
| test runner | vitest 4.1.x, `vitest.config.ts`, `vitest --project unit*` | Vite+ `vp test --project unit*` over `vite.config.ts`: vitest 5.0.3 at -15; at -34 `vitest` is `npm:@voidzero-dev/vite-plus-test@0.1.22` |
| lint / format | eslint 10 + prettier (`eslint.config.js`, `.prettierrc`) | `vp lint` (oxlint) / `vp fmt` (oxfmt), config inside `vite.config.ts` |
| install hooks | preinstall `npx only-allow pnpm`, postinstall `simple-git-hooks` | preinstall `npx only-allow pnpm`, prepare `vp config --hooks-dir .vite-hooks` |
| node | `.node-version` `lts/*` (CI: 26.13.1); engines `>=20` | `.node-version` 24.15.0; engines `>=22.12` at -34, `^22.22.2 \|\| ^24.15.0 \|\| >=26` at -15 |

Every command reads the pnpm pin from the copy and calls the runners through their node entry. So one settings file
covers both branches. `node_modules/vitest/vitest.mjs` exists in vitest 4, in vitest 5, and in vite-plus-test 0.1.22
(its file list was checked on jsdelivr). On the machine's node 22.23.5, every engines range that was checked is met:
jsdom 30 (`^22.22.2`), eslint 10, vite 8, vite-plus-core 1.1, puppeteer 25, and pnpm 11 (`>=22.13`). CI runs node 26
(main) or 24 (minor), not 22. That is a small risk.

## What was read

| Commit | Why | Files |
|---|---|---|
| 096dc120ae (newest, -01, main) | newest main | package.json, pnpm-workspace.yaml, vitest.config.ts, .github/workflows/test.yml + ci.yml, .gitignore, .node-version, tsconfig.json, tree |
| 474907c0f0 (-32, oldest main) | oldest main | package.json, pnpm-workspace.yaml, vitest.config.ts (identical to newest), .gitignore |
| 37bf752bf1 (-28) | type test | package.json scripts, packages-private/dts-test/{tsconfig.test.json,package.json}, tsconfig.build.json, rollup.dts.config.js |
| b55f3b92a1 (-15, newest minor) | newest minor | package.json, pnpm-workspace.yaml, vite.config.ts, test.yml, AGENTS.md, .gitignore, .node-version |
| 1edd21e0b1 (-34, oldest minor) | oldest minor | package.json, pnpm-workspace.yaml, vite.config.ts, AGENTS.md, .gitignore, tree, pnpm-lock.yaml (head) |
| all 34 starts | branch, pnpm pin, test script | package.json (version, packageManager, scripts.test, engines), presence of vite.config.ts |

CI job logs used:
- 137457563410 (main unit-test): `pnpm install` gives +503 packages. The whole unit suite took 40.8 s on 185 files and
  4188 tests.
- 138939029760 (minor unit-test): `vp install` with pnpm 12.21.0. `vp test --project unit*` prints `RUN v5.0.3`. The
  whole unit suite took 102 s on 292 files and 10253 tests.
- 139034997207 (main e2e, failing): the ` FAIL ` summary line.

The pnpm v11.0.0 and v12.0.0 release notes were read for the pnpm traps below. The npm registry was read for the
`pnpm`, `vite-plus`, `@voidzero-dev/vite-plus-test` and engines fields. The diff file lists in `files/vue-core/*.json`
were read for all 34.

## Commands

| Command | What it does | Verified? |
|---|---|---|
| `setup` | Installs the pinned pnpm with npm into `$BENCH_CACHE/pnpm/V` once per version. Then `pnpm install --frozen-lockfile --ignore-scripts --store-dir $BENCH_CACHE/pnpm-store`. Then it restores any tracked file pnpm touched, smoke-runs `packages/shared/__tests__/`, and fails if anything unignored is left. | Install step from CI (`pnpm install` / `vp install`). The pnpm-from-npm install, `--ignore-scripts`, `--store-dir` and the smoke run are **unverified**. |
| `test_files` | Sorts `{files}` into four groups. (1) Specs (`*.spec.ts`, `*.test.ts`) run as given. (2) `__snapshots__/X.spec.ts.snap` runs `X.spec.ts`. (3) Helpers under `packages/P/__tests__/` run `packages/P/__tests__/` when no spec of the list is there. (4) Type tests under `packages-private/dts-test/` run `node --run build-dts && node --run test-dts-only`. The specs run as `CI=true node node_modules/vitest/vitest.mjs run --project 'unit*' --reporter=default SPECS` from the root. | `test-unit` is CI's command on main. On minor, CI runs it through `vp test`, and calling vitest directly is **unverified**. The sorting is ours (checked on a stub). `node --run` is **unverified** (node 22 has it). |
| `test_package` | `vitest run --project 'unit*' --passWithNoTests packages/{package}/`. `.` runs the whole unit suite. | **unverified** (ours, from `test-unit`) |
| `package_of` | `regex:^packages/([^/]+)/`. packages-private, scripts and root files give `.` | ours |
| `failed` | Names start at the path: `^ *FAIL\b…\s((?:packages\|packages-private\|scripts)/…\.ts(?: > …)?)(?: \[ … \])?$` | Checked against CI log 139034997207 and vitest's NO_COLOR form `\|unit\| ` |
| Rail `setup` | Hard-links (`cp -al`) every `node_modules` folder of the main checkout into the new worktree, except under `.git` and `.claude`. In the main checkout it does nothing. If the main checkout has no `node_modules/.pnpm`, it runs an offline pnpm install from the store instead. | **unverified** (ours; toy-repo run only) |
| Rail `verify` | (1) Lint and format the changed `.ts/.js` files plus `packages/shared/src/index.ts`: eslint + prettier on main, `vp lint` + `vp fmt --check` on minor. (2) `tsc --incremental --noEmit`. (3) `build-dts` + `test-dts-only`. (4) The whole unit suite. | The steps are CI's (lint-and-test-dts and unit-test jobs). The changed-file selection and running `vp` from `node_modules/.bin` are **unverified**. |

How long things take (estimates):
- One `test_files` run: about 10-30 s (vitest start plus jsdom).
- One `test_files` run with type tests: about 2-3 min (`tsc` over all of src, the rollup dts bundle, two or three `tsc`
  projects).
- One `test_package` run: about 10-40 s.
- A `.` package run: the whole unit suite, about 1-3 min on 4 cores (CI: 41 s on main, 102 s on minor).
- Rail `verify`: about 5-8 min.
- Rail `setup`: seconds.

`timeout_minutes` is 20. The bench's admission runs Rail's setup and verify under `timeout_minutes`, not under
`verify_timeout_secs`, so it must cover verify too. `verify_timeout_secs` is 1500 and `setup_timeout_secs` is 600 (the
offline-install fallback).

Why the whole unit suite always runs in `verify`, rather than only the changed packages:
- The packages import each other. A runtime-core change breaks runtime-dom, vue and server-renderer tests.
- The whole suite costs 1-3 minutes.
- It runs on the start commit, so admission exercises it.

The lint step always includes one fixed file for the same reason: otherwise the lint tools would first run at a ship.

## pnpm and the cache

- **The pin moves inside the window** (11.5.2 to 12.16.1, eight distinct versions). Setup reads it from the copy and
  installs each version into `$BENCH_CACHE/pnpm/<version>` once (pnpm 11 is about 20 MB; pnpm 12 is a Rust binary via
  `@pnpm/exe.linux-x64`, about 30 MB).
- pnpm 11 and 12 share store format v11. CI's log shows `store/v11` under pnpm 12. So one `$BENCH_CACHE/pnpm-store`
  serves every start.
- **The machine's pnpm 10.28** is what an agent gets when it types `pnpm`. In a project pinned to another version,
  pnpm 10 tries to download the pin (`manage-package-manager-versions`, true by default), which fails offline.
  - The env sets `npm_config_manage_package_manager_versions=false` (pnpm 10 reads `npm_config_*`) and
    `pnpm_config_pm_on_fail=ignore` (the pnpm 11+ spelling).
  - With those, `pnpm vitest …` and `pnpm exec …` work offline. `pnpm install` does not.
  - `pnpm test` on main runs every vitest project, including the e2e ones that need puppeteer's Chrome and playwright.
    Agents should use the given commands.
- **Why `--ignore-scripts`**:
  - It skips the root `preinstall` (`npx only-allow pnpm`, which fetches from npm).
  - It skips the git hooks: `simple-git-hooks` on main and `vp config --hooks-dir .vite-hooks` on minor. These would
    make every Rail commit run lint-staged and `pnpm check`.
  - It skips the dependency builds that `allowBuilds` lists. None of them is needed for unit tests:
    - esbuild, @swc/core, unrs-resolver and @parcel/watcher get their binaries from optional dependencies.
    - puppeteer would download Chrome.
    - vue-demi's script only prints.
- **pnpm 11+ settings** come only from `pnpm-workspace.yaml` and `pnpm_config_*` env vars (not `.npmrc`). Flags are
  used for the store, offline and frozen lockfile.
- **pnpm 12 checks the lockfile against `trustPolicy` and `minimumReleaseAge`** on install ("Lockfile passes
  supply-chain policies" in CI's log). That is fine with the network at setup. It may fail in the offline fallback of
  Rail's setup, which is why the main path copies node_modules instead.
- **pnpm 11+ may add placeholder `allowBuilds` entries to `pnpm-workspace.yaml`**. Setup runs `git checkout -- .`
  after install, and the final `git status` check catches anything else.

## Copy size and disk

- The repository itself is small: 800-1200 tracked files, under 30 MB.
- `node_modules` holds about 500 packages on main (CI: +503) and somewhat more on minor. It includes:
  - monaco-editor (about 90 MB, via template-explorer and sfc-playground)
  - typescript 6
  - @swc/core binaries
  - rolldown and vite-plus native binaries
  - oxlint, oxlint-tsgolint and oxfmt binaries (minor)
  - jsdom, puppeteer and playwright (without browsers)
- **Expect about 0.6-1.0 GB and 40-70 k files per copy.** This is an estimate; nothing was installed.
- The sealed copy itself is cheap, because pnpm hard-links from the store when the store is on the same filesystem.
  Every `shutil.copytree` copy, though, is a full copy. Each one takes about 15-40 s.
- The store grows with every distinct lockfile: about 1-1.5 GB at first, perhaps 2-4 GB over 34 starts.
- If disk gets tight, a filtered install that leaves out `packages-private/{sfc-playground,template-explorer}` would save
  about 150 MB. It is untested, and `tsc --noEmit` might then miss their types.
- Rail worktrees cost almost nothing (hard links).
- **Trap**: a hard-linked worktree shares inodes with the run's main checkout, so writing a file in place in
  `node_modules` writes through to the main checkout.
  - That is harmless for caches (`node_modules/.vite`).
  - An agent that edits a file inside `node_modules` while debugging changes it for that run's main checkout too.
  - It never reaches the shared store, because the run's copy is a copytree copy.

## Traps seen

- **Absolute paths**:
  - pnpm's `.bin` shims carry an absolute `NODE_PATH` from install time. It goes stale after the copy and the rename,
    but it is only a fallback, and pnpm's links inside `node_modules` are relative.
  - The commands never use pnpm at test time; they call `node node_modules/…` directly.
- **Generated files**:
  - Type tests need `build-dts`. It writes `temp/` and `packages/*/dist/*.d.ts`, both gitignored. `temp` was added to
    `build_dirs`; no tracked folder is named temp or dist.
  - Unit tests run from source through `scripts/aliases.js` and need no build.
- **Snapshots**:
  - With `CI=true`, vitest's snapshot mode is `none`. A missing snapshot fails, and an empty `toMatchInlineSnapshot()`
    is never written back into the hidden test file.
  - vue-core-04's ssrInjectCssVars tests are inline snapshots.
- **vue-core-21** hides `compiler-vapor/__tests__/transforms/__snapshots__/TransformTransition.spec.ts.snap` but not its
  spec. `test_files` maps the snapshot to that spec, so the compiler side is checked.
- **AI-agent detection**: vitest 4.1+ picks a different reporter when it sees an agent. The commands pass
  `--reporter=default` and unset `CLAUDECODE`, `CLAUDE_CODE` and `AI_AGENT`.
- **Colour**: `NO_COLOR=1` is in env. Under `CI=true`, picocolors and tinyrainbow would otherwise colour the FAIL line.
  The regex keys on the path, so a colour badge such as `  e2e-browser (chromium)  ` does not break it, but ANSI codes
  would.
- **Network at test time**: none for unit tests. The e2e (puppeteer) and e2e-browser (playwright) projects are never
  run, and `VAPOR_E2E` is never set.
- **vitest initialises every project, even under `--project unit*`** (comment in vite.config.ts). That includes the
  browser projects, but CI's unit job runs that way with no browsers installed, so it does not launch them.
- **Tests red at the start**: not known. CI on main and minor is mostly green, and the e2e failures seen are in browser
  projects, which these commands never run.

## Situations that may not pass admission

- **vue-core-28**: a type test (`packages-private/dts-test/setupHelpers.test-d.ts`).
  - Each run is build-dts plus the dts `tsc` projects, about 2-3 min, so the ten oracle runs take about 25 min.
  - It passes only if the whole dts-test project is green with the fix at 37bf752bf1.
- **vue-core-25**: the test allocates 1M callbacks. It may be slow or memory-hungry under 3 worker threads (CI was
  green).
- **vue-core-03**: the notes say the vModel tests likely pass before the fix. The null check covers the whole list, so
  it still fails through looseEqual.spec.ts.
- **Minor-branch situations** (15, 18-24, 29-31, 33, 34): they depend on plain vitest running `vite.config.ts` the way
  `vp test` does. The oldest two (-33, -34) also depend on `vite-plus-test@0.1.22` as vitest, which is the least sure.
- **Timer-heavy runtime-vapor Transition, Suspense and hydration specs** (-07, -09, -21, -24, -29, -34): a 10-of-10
  oracle may show flakes on a loaded 4-core box.

## For the admission session to try first

1. Run setup on vue-core-01 (main, pnpm 12.16.1) and vue-core-34 (minor, pnpm 11.5.2).
   - Check that `$BENCH_CACHE/pnpm/<v>/bin/pnpm --version` prints the pin.
   - Check that the install ends with `git status --porcelain` empty.
   - Check that the smoke run passes.
   - If pnpm 12 refuses `--ignore-scripts` or `--store-dir`, try the `pnpm_config_ignore_scripts=true` and
     `pnpm_config_store_dir=…` env forms.
2. On vue-core-34 and vue-core-15, run `test_files` on the hidden spec. Check that plain vitest loads `vite.config.ts`.
   If it does not, swap the vitest call for `node_modules/.bin/vp test run --project 'unit*' --reporter=default …` on
   minor (detect with `[ -x node_modules/.bin/vp ]`), and check that vp does not try to fetch a Node 24 runtime offline.
3. Check that the ` FAIL ` lines in a real failing run match `failed` (the null run of vue-core-01 gives one).
4. Run Rail's `verify` on the start commits of -01 and -34 and time it.
   - On minor, check that `vp lint` and `vp fmt --check` work offline.
   - If they don't, drop those two lines and keep `tsc`, dts and unit.
5. Run vue-core-28 (`node --run build-dts`; type tests) and time one run.
6. Create a worktree in a copy, run Rail's `setup` there with the network off (`unshare -n`), then run one spec.
