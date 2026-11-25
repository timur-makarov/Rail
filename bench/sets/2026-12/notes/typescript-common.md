# Shared decisions for the four TypeScript (pnpm) projects

Facts found so far (2026-11-26):
- All four pin pnpm through package.json `packageManager`, and the pin moves between start commits:
  vue-core 11.5.2 (oldest) -> 12.16.1 (newest); typescript-eslint 10.33.0 -> 12.20.0; vitest 11.6.0 -> 11.28.6;
  svelte 10.4.0 -> 10.33.4. The machine has pnpm 10.28.0 and node v22.23.5 (pnpm 11 needs node >=22.13: ok;
  pnpm 12 is a Rust CLI shipped as npm package `pnpm` with optional deps `@pnpm/exe.<platform>` and an install.js
  pre/postinstall that links the native binary; node >=18).
- pnpm 10 defaults `manage-package-manager-versions` to true: the machine's pnpm 10.28 run in a project pinned to
  another version tries to DOWNLOAD that version into PNPM_HOME (per-run HOME for agents) -> fails offline. pnpm 10
  reads `npm_config_*` env. pnpm 11 removed that setting for `pmOnFail` (download default; `ignore` to turn off),
  reads only `pnpm_config_*` env vars, reads only auth/registry from `.npmrc`, store v11 (SQLite index.db),
  `verifyDepsBeforeRun: install` by default (pnpm run/exec may try an install), `strictDepBuilds: true`,
  `allowBuilds` replaces onlyBuiltDependencies. pnpm 12: `--frozen-lockfile false` no longer accepted; packageImportMethod
  auto tries hardlink first on Linux; unknown pnpm-workspace.yaml keys fail when the pin is honored.
- The bench's `[commands] env` values are LITERAL (no `$BENCH_CACHE` expansion); `BENCH_CACHE` itself is set by the
  bench for every command and agent child. Agents get a per-run HOME. So any path into the cache must be written as
  `$BENCH_CACHE/...` inside the bash commands, not in env.

Decisions (keep the four projects consistent):
1. env (every project): `NO_COLOR = "1"` (picocolors/tinyrainbow turn colour ON when `CI` is set; colour codes would
   break `failed`), `npm_config_manage_package_manager_versions = "false"` and `pnpm_config_pm_on_fail = "ignore"`
   (the machine's pnpm 10.28 must never try to download the pinned pnpm offline), `COREPACK_ENABLE_STRICT = "0"`,
   `COREPACK_ENABLE_DOWNLOAD_PROMPT = "0"`, `PUPPETEER_SKIP_DOWNLOAD = "1"`, `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"`,
   `SKIP_SIMPLE_GIT_HOOKS = "1"`, `HUSKY = "0"`, plus project-specific ones (e.g. `NX_DAEMON = "false"`,
   `NX_NO_CLOUD = "true"`). Do NOT put `CI` in env (it changes pnpm/agent tools); put `CI=true` only in front of test
   commands if wanted (vitest: CI makes snapshot update mode `none`, so a missing snapshot fails instead of being
   written, and an empty `toMatchInlineSnapshot()` is never rewritten into the hidden test file).
2. The pinned pnpm: setup reads the version from the copy's package.json and installs it with npm into
   `$BENCH_CACHE/pnpm/$V` (`npm install -g --prefix "$BENCH_CACHE/pnpm/$V.tmp.$$" "pnpm@$V"` with
   `npm_config_cache="$BENCH_CACHE/npm-cache"`, then `mv` into place; skip when `$BENCH_CACHE/pnpm/$V/bin/pnpm` exists).
   Every later pnpm use is `"$BENCH_CACHE/pnpm/$V/bin/pnpm"` with V read again from package.json.
3. Install at setup: `"$PNPM" install --frozen-lockfile --store-dir "$BENCH_CACHE/pnpm-store"` (decide per project
   about `--ignore-scripts`: dependency builds vs. root postinstall/prepare that need network or write git hooks).
   The store is content-addressed and shared by every situation of the project.
4. Test commands avoid pnpm at test time: call the runner's own entry with node
   (e.g. `node node_modules/vitest/vitest.mjs run ...`), filtering `{files}` down to real test files in bash and
   skipping fixtures/snapshots in the list. Put `CI=true` in front if it suits the project.
5. Rail's `setup` in a new worktree: copy every `node_modules` folder of the main checkout
   (`main="$(git rev-parse --path-format=absolute --git-common-dir)/.."`) into the worktree at the same relative
   path with `cp -al` (hard links: fast, no disk; pnpm's symlinks inside node_modules are relative, so workspace links
   resolve to the worktree's own packages). Skip when the worktree IS the main checkout (admission runs Rail's setup
   in the copy root). Copy needed build outputs (dist) with plain `cp -a` (a rebuild truncates files in place and would
   write through a hard link into the main checkout), or rebuild offline. Fallback when main has no node_modules:
   `"$PNPM" install --offline --frozen-lockfile --store-dir "$BENCH_CACHE/pnpm-store"`.
   Exclude `.claude/worktrees` when walking the main checkout.
6. `failed` for vitest: the summary lines ` FAIL  [|project| ]path > suite > test`. Check against a real CI log.
7. Every command gets `# from: FILE@SHA` and, when not checked against the project's CI/docs, `# unverified: WHY`.
