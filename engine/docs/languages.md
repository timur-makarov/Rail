# Languages and projects

One repository may hold several projects: services, apps, libraries and infrastructure, in one language or
several. Rail works out which they are from the tracked files of the tree in front of it, each time it needs
them, and a ticket sets up and checks only the projects its change reaches. Nothing is written for a project:
one that a ticket or a person adds later is found the same way.

Rail serves Python, TypeScript, Rust and Go first. Each has a profile: data in the engine's `profiles/` folder
with the language's manifests, commands, rules and paths. Any other kind of thing is a project a `[[projects]]`
entry declares, with the commands that check it.

## How Rail finds the projects

It reads the tracked files and looks for each profile's manifests. A manifest inside `node_modules`, `vendor`,
`target`, `.venv` or `dist` is vendored, installed or built code and counts for nothing.

| Profile | Manifests |
|---|---|
| `python` | `pyproject.toml`, `setup.cfg`, `requirements*.txt` |
| `typescript` | `package.json`; type checking is on only where a `tsconfig.json` is tracked beside it |
| `rust` | `Cargo.toml` |
| `go` | `go.mod` |

- Each folder a manifest marks is one project, named after the folder: `workers/billing`, with the paths
  `workers/billing/**`. A manifest at the repository's root gives the project `root`, with the paths `**`.
- A manifest nested inside a project's folder counts for that project: the top-most folder is the project,
  unless a workspace names the nested folder as a member (below).
- Two languages' manifests in one folder give two projects, `FOLDER-python` and `FOLDER-typescript`.
- A manifest that marks no project, such as a `package.json` kept for a formatter, goes under
  `[init] other_manifests`, a list of globs.

`rail doctor` prints each project: its language and package manager, its paths, what it uses and its commands,
with the `[[projects]]` entries marked. `rail context NN` names the projects a ticket's scope reaches.

## What a project gets

Its profile's `setup` and `verify`, run in the project's folder (the table below), and what the profile brings
besides, applied to the project's paths:

- a rule that forbids the language's suppression markers in added lines of its own files (`rail docs rules`);
- its migration folders, as `migration_paths` holds them (the kind `data-loss`);
- its generated files, left out of the size count as `[size] exclude` leaves files out;
- its test files, as `[tests] paths` holds them.

None of this is written into `.rail/config.toml`: it is added to what the config holds each time the config is
read, so a Python rule holds in `api/**` when `api/` is the Python project and nowhere else.

| Profile | Suppression markers, in these files | Migration paths | Generated files |
|---|---|---|---|
| `python` | `# type: ignore`, `# pyright: ignore`, `@pytest.mark.skip`, `@pytest.mark.xfail` in `**/*.py` | `**/alembic/versions/**` | `**/*_pb2.py`, `**/*_pb2_grpc.py` |
| `typescript` | `@ts-expect-error`, `@ts-nocheck`, `oxlint-disable`, `biome-ignore`, `.only(` in `**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}` | `**/drizzle/**` | none |
| `rust` | `#[allow(`, `#![allow(`, `#[ignore` in `**/*.rs` | none | none |
| `go` | `//nolint`, `t.Skip(` in `**/*.go` | none | `**/*.pb.go` |

The seed's own `no-new-suppressions` rule stays, on every file.

## The commands

The package manager is the one whose lockfile is tracked beside the manifest. With no lockfile tracked, a
tracked `requirements*.txt` picks `pip`, and the pip commands name the file that was found, as
`pip-audit -r requirements-dev.txt`. With neither, it is the first manager in the row: a `pyproject.toml` alone
gets `uv`.

| Profile | Manager, by lockfile | `setup` | `verify`, in order |
|---|---|---|---|
| `python` | `uv` (`uv.lock`), `poetry` (`poetry.lock`), `pip` (`requirements.txt`, or with no lockfile a tracked `requirements*.txt`) | `uv sync --locked` | format `uv run ruff format --check --extend-exclude .rail --extend-exclude .claude .`; lint `uv run ruff check --extend-exclude .rail --extend-exclude .claude .`; types `uv run basedpyright --level error`; tests `uv run pytest -q`; audit `uv export --locked --no-emit-project --format requirements-txt \| pip-audit --disable-pip --no-deps -r /dev/stdin` |
| `typescript` | `pnpm` (`pnpm-lock.yaml`), `npm` (`package-lock.json`), `yarn` (`yarn.lock`), `bun` (`bun.lock`) | `pnpm install --frozen-lockfile --ignore-scripts` | lint `pnpm exec oxlint --deny-warnings`; types `pnpm exec tsc --noEmit`; tests `pnpm test`; audit `pnpm audit` |
| `rust` | `cargo` (`Cargo.lock`) | `cargo fetch --locked` | format `cargo fmt --check`; lint `cargo clippy --all-targets --locked -- -D warnings`; tests `cargo test --locked`; audit `cargo deny check advisories` |
| `go` | `go` (`go.sum`) | `go mod download` | format `test -z "$(gofmt -l .)"`; lint `go vet ./...` and `golangci-lint run`; tests `go test -race ./...` (the race detector needs cgo and a C compiler); audit `govulncheck ./...` |

The other managers of a profile run the same parts through their own runner. How the parts are put together:

- The parts are joined with `&&`, so the first failure ends the project's `verify`.
- Each command runs in the project's folder, so no command names it.
- `types` is left out where type checking is off: a `package.json` with no `tsconfig.json`.
- Python's `types` asks basedpyright for errors only (`--level error`). With no settings of the project's own,
  basedpyright also fails on its warnings, and those are matters of style: a call's result that is not assigned,
  a method not marked as an override. A project that wants them writes its own settings and command.
- TypeScript's `lint` runs oxlint with `--deny-warnings`: oxlint reports its default rules, a `debugger`
  statement among them, as warnings and exits 0 on them.
- An audit runs only on a change that touches the project's lockfile:
  `{ git diff --quiet "$RAIL_BASE"...HEAD -- ':(top)uv.lock' || AUDIT; }`. A new advisory on an old dependency
  then doesn't fail a ticket that has nothing to do with it.
- ruff leaves out `.rail` and `.claude`: Rail's engine and the agent's files are tracked in the project,
  and they are not its code.
- An install runs no dependency's lifecycle scripts where the manager can turn them off (`--ignore-scripts`).
  Cargo can't: a build always runs the dependencies' build scripts and procedural macros.

Every tool a command names has to be on the machine that runs it: a command the shell can't find is recorded
as could not run (`rail docs retries`).

## Workspaces

A workspace gives one project for each member, with commands that name the member, and the members'
dependencies on each other become `uses`. Rail reads the workspace's own files and runs no tool for it.

| Workspace | Read from | A member's commands | `uses` |
|---|---|---|---|
| uv | `[tool.uv.workspace]` `members` and `exclude` in a `pyproject.toml` | `setup` is `uv sync --locked --package {name}`; `verify` as above, in the member's folder; the audit reads the workspace's `uv.lock` | a dependency that `[tool.uv.sources]` marks `workspace = true`, in the member's file or the workspace root's |
| pnpm | `packages` in `pnpm-workspace.yaml` | `setup` is `pnpm install --frozen-lockfile --ignore-scripts --filter {name}...`; `pnpm --filter {name} exec oxlint --deny-warnings`, `pnpm --filter {name} exec tsc --noEmit`, `pnpm --filter {name} test`; the audit reads the workspace's `pnpm-lock.yaml` | a dependency whose version starts with `workspace:` |
| Cargo | `[workspace]` `members` and `exclude` in a `Cargo.toml` | `cargo fmt --check -p {name}`, `cargo clippy -p {name} --all-targets --locked -- -D warnings`, `cargo test --locked -p {name}`; the audit reads the workspace's `Cargo.lock` | a dependency with a `path` that is a member's folder |
| Go | the `use` lines of `go.work` | the module's own, in its folder | a `require` of another module of the `go.work` |

`{name}` is the member's package name. A workspace root that holds no package of its own is no project. The
root of a pnpm workspace always has a `package.json`, which mostly holds the tools: it is a project only when
a member depends on its package with `workspace:`, and it then runs the commands of a project outside a
workspace, in the root: `pnpm --filter` matches no package at the root and exits 0. A file
of the workspace itself (its manifest, its lockfile, the workspace file at its root) reaches the workspace's
members and no project outside it.

No command filters by what changed since the base: the set a change reaches does that work for every language.

## `[[projects]]`

The config holds only what can't be worked out. An entry either names a derived project and changes it, or
declares a project no manifest marks:

```toml
[[projects]]
name = "web"                      # a derived project: its own test command in the default's place,
verify = "pnpm run check"         # and a dependency no import shows
uses = ["api"]

[[projects]]
name = "infra"                    # declared: no manifest marks it
paths = ["infra/**"]
setup = "terraform -chdir=infra init -backend=false"
verify = "terraform fmt -check -recursive infra && terraform -chdir=infra validate"
```

- `paths`, `setup` and `verify` replace the derived ones; `uses` adds to what the workspace's files show.
- A derived project's commands run in its folder, an entry's or not. A declared project's commands run at the
  repository's root.
- The config is refused when a `uses` names no project, when the `uses` go in a circle, and when a declared
  project has no `paths`.
- Where Nx, Turborepo, Bazel or Pants already works out what a change affects, one entry makes the workspace a
  project whose `verify` calls that tool with `$RAIL_BASE`.

`[commands] setup` and `verify` hold only what belongs to the whole repository, such as the secret scan over
the branch's commits. They run at the repository's root on every change, after the projects' own.

## What a change reaches

- The projects whose paths match a changed file, and every project that uses one of them, followed through
  `uses` to the end. A project runs before the projects that use it.
- A changed file inside no project reaches every project: a root manifest, a CI workflow,
  `.rail/config.toml`.
- A workspace's own file reaches that workspace's members.
- The projects are worked out from the base and from the branch, so a manifest a change adds makes a project in
  its own ship, and a file counts for the projects it is inside on either side.

At the claim, `setup` runs for the projects the ticket's `scope_paths` reach, each as its own step
`setup:NAME`, then `[commands] setup` as `setup`. At ship and in CI, `verify` runs for the projects the changed
files reach, each as `verify:NAME`, after `setup:NAME` for any of them this checkout has not set up, and then
`[commands] verify` as `verify`. Retries, flaky checks and time are counted for each step, and `rail stats` has
a split by project.

`rail ci` works the same set out from the pull request's diff against the base, so the check GitHub requires
stays the one check `rail`. No workflow uses a path filter: a required check that a path filter skips never
reports, and the pull request then waits for good.

`uses` decides which checks run, and nothing more. Whether a frontend still works against a changed backend is
shown only by a check that drives both.

## What no project holds

A tracked file inside no project is read by no check, and Rail says so instead of leaving it unnoticed. Left
out of this: the files at the repository's root, the folders Rail and the host own (`.rail/`, `.claude/`,
`.github/`), vendored, installed and built folders, and a workspace's own files.

- **The fact.** At each ship the engine lists the folders that hold such files, with their file types. `rail
  doctor` has a line `coverage` that names the ones nothing has been answered about. The reviewer's brief names
  the files of the change that no check read.
- **The question.** Each such folder raises the triage question `uncovered` once (`rail docs triage`). Answered
  `nothing-to-check` (docs, assets, data, examples), the answer is recorded and the folder is asked about again
  only when it gets a file of a type the answer did not see. Answered `needs-checks`, the engine files a ticket
  `coverage:FOLDER`.
- **The record.** A ticket whose ship was answered has the answers in `.rail/journal/NN-coverage.json`, which
  only the engine writes: `{folder: {types, answer, holds, covered_by}}`. Each ticket writes its own file, so
  two tickets never change the same one. Where several name a folder, the latest ticket's answer counts and the
  types are everyone's.
- **The ticket that covers a folder.** Its work is to look up the checks this kind of file has, write the
  `[[projects]]` entry with them, and add the folder's path under its kind in `[kinds]` when it is of one, as a
  Terraform folder is `infrastructure`. It changes `.rail/config.toml`, so it is PERSON under `controls`: a
  person merges the checks for a new kind of thing once. While a folder's ticket is open, the folder is not
  asked about again.
- **Until that ticket merges** the folder's files are checked by nothing, and the change that added them is not
  held for it. The reviewer sees them named and names their kind, which makes the change PERSON without any
  path (`rail docs kinds`).
- **A commit no ticket made.** When the base branch has moved by one, `rail next` looks at the base's folders.
  If one is unanswered, the engine files a ticket that changes no file of the project's, and that ticket's ship
  asks the questions (`ASK_COVERAGE`).
- **Removing a manifest and keeping the code** leaves that code in no project, so its folder is asked about in
  the same ship.
- **Kind paths.** When a reviewer names a kind on a file that no path of that kind in the config matches, and
  no coverage ticket is open for its folder, the sweep's summary lists the file so that a ticket adds the path.

The wording of the `uncovered` question, of the coverage ticket's request, of the reviewer's section and of the
sweep's line has not been tested with a model run.

## What `rail init` writes

- Into a new `.rail/config.toml`, when the repository holds a project: the secret scan as `[commands] verify`,
  `gitleaks git --no-banner --redact -v --log-opts="$RAIL_BASE..HEAD"`. `-v` makes a finding name its file and
  line, and `--redact` keeps the secret itself out of the output. An existing config is never touched.
- Into `.gitattributes`: the generated files of the projects found, marked `linguist-generated`.
- Into `.claude/settings.json`, whether the config is new or not: each found profile's package registry in
  `sandbox.network.allowedDomains`, so the agent's own installs reach it with the sandbox on. Python:
  `pypi.org`, `files.pythonhosted.org`. TypeScript: `registry.npmjs.org`, `registry.yarnpkg.com`. Rust:
  `index.crates.io`, `static.crates.io`. Go: `proxy.golang.org`, `sum.golang.org`. A mirror, a private
  registry or a Git dependency is the project's to add.

Its receipts name the projects it found. The init task tells the agent where a `[[projects]]` entry belongs:
where a Makefile target, a `package.json` script or a CI step already runs a part, that goes in the default's
place, because it holds what the project knows.

A false finding of the secret scan has one answer. The scan reads every commit of the branch, and a branch is
never rewritten, so changing the line it found does not help: its first commit still fails. Put the finding's
`Fingerprint:`, which the scan prints, on a line of `.gitleaksignore` at the repository's root and ship. The
file is in every ticket's scope. The line raises the triage question `secret`: a run that did not write the
change says whether the string is a credential, and a real one waits for a person, who rotates it (`rail docs
triage`).

## What Rail's own tests run

They run each profile on a small real project of that language, from `rail init` to a merged ticket: each
project's `setup` and `verify` pass, and one planted mistake for each part fails it. A fifth project is a
Python service, a TypeScript app and a library both use, in a uv workspace and a pnpm workspace: a ticket in
the library runs the library's checks and both users', with the members' own commands, to a merge. No mistake
is planted for a member's command there: a failing test fails its project's `verify`, and that is all.

Each of the four projects is then carried on, a ticket for each feature, to show that the features work
together with a real toolchain. A ticket adds a second project that uses the first (a member of a uv
workspace, a member of a pnpm workspace, a third crate, a module of a `go.work`), and a later change to the
first runs both projects' checks. A ticket that edits an old test raises `old-test`; one on a workflow waits
for a person's one act; one that keeps failing gets its diagnosis and starts again; one that adds a folder
of Terraform raises `uncovered` in the Rust project, whose crates do not cover the repository, and nothing in
the other three, whose project is the repository's root. The last ticket starts the sample's service, seeds
it, drives it and stops it, and fails while the sample's planted fault is switched on; the Rust sample has no
service, and its command line is driven. `rail stats` is then read for the number of each. The worker, the
reviewer and the triage run are stand-ins and there is no remote, so no wording a model reads is tested here,
and nothing GitHub does.

| Profile | Run by Rail's tests | Not yet run by them |
|---|---|---|
| `python` | uv's setup, format, lint, types, tests, audit, for one project and for a uv workspace's members, its root among them | an audit that finds an advisory; every Poetry and pip line |
| `typescript` | pnpm's setup, lint, types, tests, audit, for one project and for a pnpm workspace's members, its root among them | an audit that finds an advisory; every npm, Yarn and Bun line |
| `rust` | setup, and a Cargo workspace member's format, lint, tests, audit | the same parts for a package in no workspace; an audit that finds an advisory |
| `go` | setup, format, both lints, tests, for one module and for the modules of a `go.work`; audit, for one module | an audit that finds an advisory |

The secret scan is run by them too, on a key planted in a commit. All of this holds on a machine that has
every tool: a part whose tool is missing is left out there and printed as "not run". Which projects a change
reaches, and what a workspace's files give, is tested with stand-ins for the tools. Plant a mistake for each
part on your own project before you rely on it.

## Generated Go files

A Go file whose generator marked it is left out of the size count wherever it lives: a line that reads
`// Code generated ... DO NOT EDIT.` on its own, anywhere before the `package` line, which is the mark Go's
own tools read. The same words after `package`, or at the end of another line, mark nothing.
