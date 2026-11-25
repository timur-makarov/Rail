# Languages

Rail serves Python, TypeScript, Rust and Go first. Each has a profile: data in the framework's `profiles/`
folder that `rail init` reads when it finds the language. Any other language is unsupported: Rail still runs,
because the engine reads commands, not languages, but init writes nothing language-specific for it.

## How init finds a language

Init reads the repository's tracked files (`git ls-files`) and looks for each profile's manifests. A manifest
inside `node_modules`, `vendor`, `target`, `.venv` or `dist` is vendored, installed or built code and counts
for nothing.

| Profile | Manifests |
|---|---|
| `python` | `pyproject.toml`, `setup.cfg`, `requirements*.txt` |
| `typescript` | `package.json`; type checking is on only where a `tsconfig.json` is tracked too |
| `rust` | `Cargo.toml` |
| `go` | `go.mod` |

A manifest at the root gives the profile `paths = "**"`. Manifests only below the root give the top-most
folders that hold one: `web/**` for one folder, `{api,worker}/**` for two. A repository with a Go service in
`api/` and a web app in `web/` gets two profiles. Init's receipts list what it found.

## What init writes

Into a new `.rail/config.toml`, for each profile found:

- a `[[profiles]]` entry with its `name` and `paths`;
- a `[[rules]]` entry that forbids the language's suppression markers in added lines of its own files
  (`rail docs rules`);
- its migration folders in `migration_paths`, its generated files in `[size] exclude`, and its test files in
  `[tests] paths`.

| Profile | Suppression markers, in these files | Migration paths | Generated files |
|---|---|---|---|
| `python` | `# type: ignore`, `# pyright: ignore`, `@pytest.mark.skip`, `@pytest.mark.xfail` in `**/*.py` | `**/alembic/versions/**` | `**/*_pb2.py`, `**/*_pb2_grpc.py` |
| `typescript` | `@ts-expect-error`, `@ts-nocheck`, `oxlint-disable`, `biome-ignore`, `.only(` in `**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}` | `**/drizzle/**` | none |
| `rust` | `#[allow(`, `#![allow(`, `#[ignore` in `**/*.rs` | none | none |
| `go` | `//nolint`, `t.Skip(` in `**/*.go` | none | `**/*.pb.go` |

The seed's own `no-new-suppressions` rule stays, on every file. An existing `.rail/config.toml` is never
touched: init lists what it found and writes nothing to it.

Into `.claude/settings.json`, whether the config is new or not: each profile's package registry in
`sandbox.network.allowedDomains`, so the agent's own installs reach it with the sandbox on. Python:
`pypi.org`, `files.pythonhosted.org`. TypeScript: `registry.npmjs.org`, `registry.yarnpkg.com`. Rust:
`index.crates.io`, `static.crates.io`. Go: `proxy.golang.org`, `sum.golang.org`. A mirror, a private
registry or a Git dependency is the project's to add.

After init every file is the project's, as with the rest of the seed: change or delete what doesn't fit.
