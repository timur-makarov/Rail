# The bench

The bench measures Rail against plain coding agents on real issues with hidden tests. The plan it is built from is
the fulltest `PLAN.md`, sections 3 to 5. It needs Python 3.11 and git, and nothing outside the standard library.

Run it as `bench/bench VERB ...` from anywhere. Everything it builds goes into the store: `$BENCH_STORE`, or
`store` in `bench/config.toml`, or `~/.rail-bench`.

## Add a project

1. Make `bench/sets/SET/PROJECT.toml`. SET is the month of the set, such as `2026-12`.
2. `[project]` names the repository (`repo`, a URL git can clone), its `language` (python, typescript, rust or go),
   the project's own package name (`package`, for the taint search), and `tests`, globs that match its test files.
3. `[commands]` says how to test it:
   - `setup` runs once when a sealed copy is built, with the network. Fetch every dependency here, into the copy or
     into `$BENCH_CACHE`, so the copy builds offline later.
   - `test_files` runs the given test files: `{files}` is replaced by them.
   - `test_package` runs one package's tests: `{package}` is replaced by it.
   - `package_of` says how a changed path gives its package: `root` (the whole project), `dir` (its folder), `top`
     (its first folder), `nearest:Cargo.toml` (the nearest folder above it holding that file), or
     `regex:PATTERN` (the pattern's first group).
   - `failed` is a regex whose first group names a failing test in the output, such as `^--- FAIL: (\S+)` for Go.
   - `env` is set for every command, such as `CARGO_NET_OFFLINE = "true"`.
4. `[rail.config]` is the project's `.rail/config.toml`, written once before any situation is read. Its
   `[rail.config.commands]` needs `setup` and `verify`.

The loader refuses a key it does not know, and says which.

## Add a situation

Add a `[[situation]]` table to the project file:

| Key | Holds |
|---|---|
| `id` | Stable, such as `ripgrep-07`. |
| `request` | The issue's title on the first line, then its first message, as first posted. |
| `start` | The commit before the fix. |
| `hidden_tests` | The test files the fix added or changed. They are kept outside the sealed copy. |
| `fix` | The fix's commit. Only the oracle grade uses it. |
| `closed` | The date the issue was closed, YYYY-MM-DD. |
| `kind` | crash, race, wrong-result, missing-behaviour or vague-request. |
| `extra` | Empty for now: hidden security tests and planted faults come later. |
| `half` | `work` or `held`. |
| `issue`, `pull` | The issue's URL and the fix's pull request number, for the taint search. |

Then admit it: `bench/bench admit bench/sets/SET/PROJECT.toml --id ID`. It builds the sealed copy and prints why a
situation fails: the hidden tests pass on the start commit (null), they fail with the fix or fail some of ten runs
(oracle), a package the fix touches fails, Rail's `setup` or `verify` fails on the start commit, or the request
links the fix.

## The sealed copy

A sealed copy is a new repository with one commit, the tree at `start`. It has no remote and no other ref, so the
fix is nowhere in it. The hidden tests and the fix sit beside it in the store, never inside. It is built once per
situation, under `store/sealed/SET/PROJECT/ID/`.

## The grade

`bench/bench grade PROJECT.toml --id ID --diff CHANGE.patch` grades a change, a git patch from the start commit. It
applies the change to a new copy, sets aside the change's test files that clash with the hidden ones (the same path;
with `clash = "dir"`, as for Go, any test file in a hidden test's folder), puts the hidden tests in place, and runs
three rounds. A round passes when the hidden tests pass and every package the change touches passes. Tests already
red on the start commit are left out. The change is right only when all three rounds pass.
