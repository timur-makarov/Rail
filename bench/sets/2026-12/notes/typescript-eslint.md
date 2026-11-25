# typescript-eslint: bench settings

Files: `typescript-eslint.toml` (project, commands, Rail's commands), `typescript-eslint.travel.json`.
Shared decisions for the four pnpm projects: `../../ts-tools/COMMON.md` (followed here; no deviation).

## What was read

At the newest start `aac759c23dc3c66e607ee498884e161c24440f3a` (typescript-eslint-01) and the oldest start
`dd020578ed417b844b1d03a70be42a126d51cbb5` (typescript-eslint-32), through `gh api`:

- `.github/workflows/ci.yml`, `.github/actions/prepare-install/action.yml`, `.github/actions/prepare-build/action.yml`
  (oldest only; the newest builds in the `build` job and pulls outputs from Nx Cloud).
- `package.json` (scripts, packageManager, nx targets of the root project `repo`), `pnpm-workspace.yaml`, `.npmrc`
  (empty), `.gitignore`, `.nxignore`, `nx.json`, `tsconfig.build.json`, `vitest.config.mts`, `vitest.config.base.mts`,
  `tools/vitest.config.mts` (newest only), `tools/scripts/postinstall.mts`.
- `packages/*/package.json` (exports point at `./dist/...`; nx names equal folder names; nx `test` overrides),
  `packages/{eslint-plugin,ast-spec,typescript-estree}/vitest.config.mts`, `packages/ast-spec/tests/fixtures.test.ts`,
  `packages/eslint-plugin/tests/docs.test.mts` (imports only; no network).
- `docs/contributing/Local_Development.mdx` and `DEVELOPMENT.md` (newest).
- The git trees of both starts; the 32 fix file lists under `bench-sets/files/typescript-eslint/`.
- One CI job log: job 139326381044 (run 45648489702, 2026-11-25, `pnpm exec nx test eslint-plugin -- --shard=1/4
  --coverage`, vitest 5) for the failure line format.
- vitest's `formatProjectName` and the FAIL summary line (`packages/vitest/src/node/reporters/{renderers/utils,base}.ts`
  on vitest main) for the uncoloured form; npm registry entries of `pnpm` 10.33/12.x and `vitest` 4.0.18/5.0.3
  (engines, bin); pnpm v11.0.0 and v12.x release notes.

## Toolchain and pins

| | oldest dd020578 | newest aac759c2 |
|---|---|---|
| packageManager | pnpm@10.33.0 (+sha512) | pnpm@12.20.0 (+sha512; the Rust CLI) |
| node engines | ^18.18 \|\| ^20.9 \|\| >=21.1 (CI primary 24) | same |
| nx | 22.3.3 | 23.3.0 |
| vitest (catalog) | ^4.0.18 | ^5.0.3 (needs node ^22.12: the machine's 22.23.5 is fine) |
| typescript | 6.0.2 (override) | `npm:@typescript/typescript6@6.0.2` (override), plus `@typescript/native` 7.1 dev |
| install in CI | `pnpm install --frozen-lockfile` | `pnpm install --frozen-lockfile --trust-lockfile` |
| dep builds | none listed (pnpm 10 skips unlisted builds) | `allowBuilds`: all false (@swc/core, core-js, esbuild, nx) |

No `.nvmrc`/`.node-version`. The pnpm pin moves 10 -> 12 inside the window, so setup reads it from the copy and
installs that exact version into `$BENCH_CACHE/pnpm/VERSION` with npm; `--trust-lockfile` is passed only when the
copy's own `prepare-install` action uses it (pnpm 10 would reject the flag).

## Commands and whether they are verified

- **setup** (partly verified): pinned pnpm into the cache (ours), `pnpm install --frozen-lockfile [--trust-lockfile]
  --store-dir $BENCH_CACHE/pnpm-store` with `SKIP_POSTINSTALL=true HUSKY=0` (as CI's prepare-install), then what the
  skipped postinstall would do minus husky and clean: `nx run-many -t build --exclude=website,website-eslint` (CI's build
  job, root `build` script) and `nx run ast-spec:typecheck` (postinstall). Ends by failing if anything is left that git
  does not ignore. Dependency lifecycle scripts: none are allowed by the project, so nothing downloads at install.
- **test_files** (unverified as a whole): maps the list to runnable files, builds, then runs vitest per package in the
  package folder with `--config vitest.config.mts` and `CI=true` (what `nx test PKG -- FILES` does, as CI runs it).
  Mapping: `*.test.{ts,tsx,mts,cts}` and `*.test-d.ts` under `packages/*/tests/` run as given; ast-spec fixture files
  (`packages/ast-spec/src/**/fixtures/**`) and `packages/ast-spec/tests/*.shot` run `packages/ast-spec/tests/fixtures.test.ts`
  (the one file that tests every fixture; it also checks the four fixture-list snapshots); scope-manager
  `tests/fixtures/**` run `tests/fixtures.test.ts`; eslint-plugin `tests/schema-snapshots/*` run `tests/schemas.test.ts`,
  `tests/docs-eslint-output-snapshots/*` run `tests/docs.test.mts`; `__snapshots__/X.snap` runs `X`; other fixtures are
  skipped. A list with no runnable file exits 2.
  Before the tests: `nx run-many -t build --exclude=website,website-eslint` (every package's `dist/` from its `src/`;
  nx's local cache makes unchanged packages instant), and `nx run-many -t typecheck` for ast-spec, utils and
  typescript-eslint when they are tested, because their nx `test` target depends on `typecheck`.
- **test_package** (unverified, same reasons): build as above, then the package's whole vitest suite in its folder.
  `.` runs the repo's `tools/` tests (newest only; nothing at the oldest). website, website-eslint, integration-tests and
  tseslint.com exit 0 (left out of the root `test` script; integration-tests packs and installs packages). A package
  without `tests/` exits 0.
- **package_of** `regex:^packages/([^/]+)/` (folder name = nx project name for every package but tseslint.com).
- **failed** `^ FAIL +(\S.*?)\s*$` (verified against the CI log and vitest's source): with `NO_COLOR=1` the summary
  line is ` FAIL  |eslint-plugin| tests/rules/x.test.ts > x > valid > ...`; a file that fails to load gives
  ` FAIL  |p| tests/x.test.ts [ tests/x.test.ts ]`. The per-test `×` lines carry a duration, so they are not used.
  Checked in python against both forms; the coloured CI form does not match (colour is off by env).
- **env**: COMMON.md's set plus `SKIP_POSTINSTALL=true` (the project's own switch: its postinstall would run
  husky, clean and a full build on any `pnpm install`), `NX_DAEMON=false`, `NX_NO_CLOUD=true` (nx.json has an
  `nxCloudId`; without this nx tries Nx Cloud), `NX_TUI=false`.
- **Rail setup** (unverified, ours): in a new worktree, `cp -al` of `node_modules` and `packages/*/node_modules` from
  the main checkout (only those two levels: newest has a TRACKED `packages/type-utils/tests/fixtures/node_modules`,
  which a recursive find would copy into itself), `cp -a` of `dist`, `packages/*/dist` and
  `packages/types/src/generated`. No build: the test commands and verify build incrementally (tsc `--build` with the
  copied `.tsbuildinfo`; nx has no cache in a new worktree, so the first build runs every package's tsc, which finds
  nothing changed, plus ast-spec's api-extractor: about 1-3 min, a guess). Fallback without node_modules in main:
  `pnpm install --offline --frozen-lockfile --store-dir $BENCH_CACHE/pnpm-store` and a build.
- **Rail verify** (unverified, ours from CI pieces): prettier `--check --ignore-unknown` on changed files (CI's
  check-format, narrowed), the build (type-checks every package's src with tsc), then `nx show projects --affected
  --files=CHANGED --withTarget=test` (CI uses `--affected` with base/head) and each affected package's whole vitest
  suite, website/website-eslint/integration-tests left out. On the start commit nothing changed: format + build only.

## Sizes and times (estimates, nothing was run)

- One copy: node_modules about 1.5-2 GB (the whole workspace is installed, website's docusaurus/monaco included),
  `dist` about 100 MB, `.nx/cache` 0.2-0.5 GB, source and `.git` about 0.3 GB: **about 2-2.5 GB**. The sealed copy
  itself is cheap (pnpm hard-links node_modules from `$BENCH_CACHE/pnpm-store`), but every `copytree` copy is full.
  To cut it, an install filtered to leave out `website` and `website-eslint` (`pnpm install --filter '!website'
  --filter '!@typescript-eslint/website-eslint' ...`) would drop most of the website's dependencies; untested, and the
  root project must stay included, so it is not the default.
- Setup: pnpm install 1-3 min (network), cold build of all packages 3-6 min, ast-spec typecheck 1 min.
- test_files: nx graph + cache check 10-20 s when nothing changed; after a source change the changed package and its
  dependents rebuild once per copy (eslint-plugin about 1 min); one rule test file 10-60 s (the biggest, e.g.
  no-unnecessary-condition, are slow); ast-spec fixtures.test.ts about 1 min (927 fixtures parsed twice).
- test_package eslint-plugin: about 3-5 min on 4 cores (CI shard 1/4 of it took 40 s of tests for 50 of ~200 files with
  coverage); typescript-estree 1-2 min; ast-spec, scope-manager about 1 min; others under 30 s.
- Rail verify: format + build 1-3 min, plus the affected suites: an eslint-plugin change about 5-8 min, a
  typescript-estree change (nearly everything affected) about 10-14 min. setup 900 s, verify 1800 s, timeout_minutes 25.

## Traps

- **Built outputs are required.** Every package's `exports` point at `./dist/...`; nx `test` depends on `^build`;
  the contributing docs say to rebuild dependents. So an eslint-plugin test after a type-utils change (typescript-eslint-09)
  or an ast-spec fixture after a typescript-estree change (-18, -30) only sees the fix after a rebuild: the test
  commands build first. A type error anywhere in the built packages fails the command (as CI's build would).
- **Absolute paths**: none needed by the commands (relative `node node_modules/...` entries, pnpm's relative symlinks,
  tsbuildinfo paths are relative). pnpm's `.bin` shims embed an absolute NODE_PATH; the commands do not use them.
  nx's `.nx/workspace-data` is copied with the copy; if nx rejects it at the new path, deleting `.nx/workspace-data`
  first costs a cache miss (rebuild) and nothing else.
- **pnpm on PATH**: the commands put `$BENCH_CACHE/pnpm/PIN/bin` first on PATH, because nx hashes `pnpm -v` (nx.json
  sharedGlobals) and the machine's pnpm 10.28 would otherwise be asked about a project pinned to 12. An agent typing
  plain `pnpm` gets 10.28; `npm_config_manage_package_manager_versions=false` keeps it from downloading the pin, and
  `pnpm exec`/`pnpm test` then work offline (pnpm 10 does not verify deps before run), but `pnpm install` would not.
- **nx** must stay offline: `NX_NO_CLOUD=true` (nxCloudId set), daemon off. `nx.json` `sync.applyChanges: true`: if nx's
  sync generators find tsconfig references out of date they rewrite tracked tsconfig files; setup fails on any such
  leftover, and an agent change to package dependencies could trigger it.
- **Snapshots**: `CI=true` on every vitest run, so a missing `.shot`/`.snap` fails instead of being written and an
  empty `toMatchInlineSnapshot()` (typescript-eslint-18's node-utils test uses inline snapshots) is never rewritten into
  the hidden file. ast-spec writes snapshot folders (`fs.mkdir`) for fixtures it finds; they are tracked anyway.
- **Hang**: typescript-eslint-04 is an infinite loop before the fix; vitest's testTimeout cannot stop synchronous code, so
  the null run ends only at the 25-minute command timeout (counts as a failure, but slow).
- **Worktree nested in the main checkout**: at the oldest start `.claude/worktrees` is not gitignored (it is at the
  newest). nx run from the main checkout while worktrees exist might find the worktrees' projects twice; Rail runs nx
  inside the worktree, where the worktree's own nx.json is the root, so this should not bite.
- **build_dirs**: `.nx` added. No tracked folder is named `dist` or `.nx`; `node_modules` is tracked once
  (`packages/type-utils/tests/fixtures/node_modules`, newest), so a saved stage drops it and the restore copies the start
  commit's version back: fine unless a change edits that fixture.
- **Tests red at the start**: none known (CI is green at merge); typescript-estree's `native-*` tests run the
  `@typescript/native` binary from node_modules (no network). Integration tests are never run.
- **Hard links**: the sealed copy's node_modules share inodes with the pnpm store (fine, it is never written); a
  worktree's `cp -al` node_modules share inodes with that run's main checkout only.

## Candidates that look risky for admission

- typescript-eslint-04: null run hangs until the 25-minute timeout (slow, still a failure as wanted).
- typescript-eslint-18: fixtures.test.ts runs all 927 fixtures and the four fixture-list snapshots; the new fixture must
  not change the AST-difference lists (the fix does not touch them, so it should not), plus an inline snapshot in
  typescript-estree's node-utils test.
- typescript-eslint-30: only ast-spec fixtures are hidden (no .test.ts); depends on the fixture-to-fixtures.test.ts
  mapping. The null run should fail on `1-TSESTree-Error.shot` and the error-difference list.
- typescript-eslint-09: hidden tests in two packages and the source in type-utils: depends on the rebuild of type-utils'
  dist before the eslint-plugin test.
- typescript-eslint-31: the fix also deprecates the rule (configs, docs); the eslint-plugin package run (configs,
  docs and schema tests) must pass with the fix's source, which includes them.
- Every situation touches eslint-plugin (or type-utils/typescript-estree/rule-tester): each package run is a 3-5 min
  eslint-plugin suite or more, so admission of one situation is about 15-25 min.

## For the admission session to try first

1. On the newest start: run setup; check `pnpm --version` prints 12.20.0 from `$BENCH_CACHE/pnpm/12.20.0`, that the
   install took `--trust-lockfile` and `--store-dir`, and that `git status --porcelain` is empty after the build.
2. In a `cp -a`-style copy (another path), run test_files for typescript-eslint-01's hidden file: nx must reuse its
   cache (or rebuild without network), and vitest must print ` FAIL  |eslint-plugin| ...` lines that `failed` matches.
3. test_files with typescript-eslint-30's list (fixtures only) and -18's: the ast-spec mapping, `nx run-many -t
   typecheck --projects=ast-spec`, and that the null run fails.
4. With `unshare -n`: test_files and test_package eslint-plugin offline (nx, Nx Cloud off, the `pnpm -v` hash input).
5. Repeat 1-2 on the oldest start (pnpm 10.33.0, nx 22, vitest 4: no `--trust-lockfile`).
6. Rail setup in a `git worktree add .claude/worktrees/01` of the copy, offline, then Rail verify there with an
   eslint-plugin source edit: `nx show projects --affected --files=...` must list eslint-plugin; time it.
