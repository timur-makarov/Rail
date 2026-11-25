# marimo (marimo-team/marimo, a reserve): bench settings

Files: `marimo.toml` (project, commands, Rail commands), `marimo.travel.json`. Nothing was installed or run against
marimo; every command carries `# unverified` in the TOML. Checked locally: the file loads through the bench's own
`sets.load` (dummy situation), every command passes `bash -n`, `package_of` over the changed source files of all 27
candidates, the travel globs against all hidden tests (no mismatch), and the `failed` regex on sample pytest lines.
The test commands were not run against a fake tree (they only pass test module paths through).

## What I read

At the oldest start (marimo-27, `3599fe4e`, 2026-07-01) and the newest (marimo-01, `35660bbe`, 2026-11-25):
`pyproject.toml` (requires-python, `[dependency-groups]`, `[tool.uv]`, `[tool.pytest.ini_options]`),
`.python-version`, `.github/workflows/test_be.yaml`, `.github/actions/test-python/action.yaml` (the static-file copy
and the pytest calls), `Makefile`, `CONTRIBUTING.md`, `AGENTS.md`, `tests/conftest.py`, `.gitignore`; existence of
`frontend/index.html`, `frontend/public/favicon.ico` and `tests/_ast/test_app.py` at both; the `marimo/` folder
listing at the newest; the `start..fix` file lists of all 27 candidates.

## Toolchain and pins

- Python: `.python-version` is 3.13 at both ends; `requires-python` `>=3.10` (oldest) and `>=3.11` (newest). CI's main
  Python job runs 3.13 with the `test-optional` group. setup installs what `.python-version` says (3.13).
- Build backend: `uv_build` (pure Python). Editable install writes a `.pth` with the copy path; setup makes it
  relative as for the other Python projects.
- Test dependencies: group `test` (pytest ~9, pytest-xdist, pytest-timeout, pytest-asyncio, pytest-rerunfailures,
  inline-snapshot, hypothesis, dirty-equals, pytest-sugar, pytest-picked, ...) and `test-optional` (adds polars,
  pandas, pyarrow, duckdb `>=1,<2` at the newest, sqlglot, sqlalchemy, altair, plotly, ibis, geopandas, chdb,
  pydantic-ai-slim, basedpyright, ...). jax/flax/torch only for Python 3.12, so not installed on 3.13. ruff is in the
  dev group only; setup adds it (marimo-26's test skips without it).
- `[tool.uv]` at the newest has `exclude-newer = "7 days"`, `exclude-newer-package`, `required-environments` and a
  pytorch index; setup passes `--no-config` so uv 0.11 neither reads nor chokes on them, and sets `--exclude-newer`
  to the start's commit time.
- No frontend build: CI's Python job copies `frontend/index.html` and `frontend/public/favicon.ico` into
  `marimo/_static/` (gitignored) because some server tests read index.html; setup and Rail setup do the same.

## Commands

| Command | What | Status |
|---|---|---|
| `setup` | uv Python from `.python-version`; venv in `$BENCH_CACHE/venvs/KEY` (pyproject, Python, date): `--group test-optional -e . ruff`; .pth relative; `.venv` symlink; static files; smoke import | unverified |
| `test_files` | the listed `tests/**/test_*.py` modules: `pytest -p no:sugar -rfE -n 0 -m "not network" --inline-snapshot=disable`; non-Python hidden files skipped | unverified |
| `test_package` | nearest existing `tests/<package>` folder, `-n 4`; `.` -> `tests/_ast/test_app.py` | unverified |
| `package_of` | `regex:^marimo/(.+)/[^/]+$` (`_plugins/ui/_impl` 7, `_ast` 6, `_sql/engines` 4, `.` 8, ...) | applied to all 27 fixes |
| `failed` | `^(?:FAILED|ERROR) (\S.*?)(?: - .*)?$` | sample lines only |
| Rail `setup` | link the venv, copy the two static files | unverified |
| Rail `verify` | `ruff check` on changed .py; pytest on tests/_ast/test_app.py plus test folders of changed marimo/ files and changed test modules | unverified |

env: `MARIMO_SERVER_SKIP_UPDATE_CHECK=1` (CI), `UV_OFFLINE`, `UV_PYTHON_DOWNLOADS=never`. The pytest config's own
addopts (`-ra -q -v --ignore ...`) and `timeout = 120` apply as well.

## Sizes and times (estimates)

- Source tree about 156 MB, 6,600 files (frontend included); copy about 220 MB with `.git`. The test-optional venv is
  large: about 2-3 GB in the uv cache (pyarrow, polars, duckdb, chdb, geopandas stack, basedpyright's bundled node).
- setup: 3-6 minutes the first time, under a minute when the cache has the wheels; one venv per start (the key holds
  the date), which costs directories, not data.
- `test_files` on one module: 5-60 s; `test_package` of a deep folder under 2 minutes, `_server`, `_runtime` or
  `_plugins` 3-6 minutes on 4 cores. timeout_minutes is 45.

## Traps

- Network at test time: tests marked `network` are deselected; some tests start a local server on loopback (fine
  offline). The update check is off by env.
- `-k "not test_cli"` in CI: CI runs the CLI tests against a built wheel in another job. The bench does not exclude
  them, because a hidden test may be a CLI test (marimo-13). CLI tests that spawn `marimo` via `sys.executable -m
  marimo` work with the editable install; ones that need the built frontend would fail at the start and be caught by
  admission.
- `pytest-sugar` is installed; `-p no:sugar` keeps the summary lines plain for the `failed` regex.
- Snapshots: `--inline-snapshot=disable` as in CI, so a mismatch fails instead of rewriting the test file.
- `.gitignore` covers `.venv`, `marimo/_static/`, `.claude` and a `*skills*` pattern; the symlink `.venv` is added to
  `.git/info/exclude` anyway.
- Rail clash: `.gitignore` ignores `.claude` and `*skills*`, which would hide Rail's installed files from git in a
  marimo checkout. The admission session should check that Rail's install still works there.

## Candidates unlikely to pass admission

- marimo-04: one hidden file is a Pyodide `.mjs` matrix test (needs node and a Pyodide download); test_files skips it
  and runs the Python shim tests, which the notes say stand alone.
- marimo-08: the test only discriminates with duckdb >= 2.0; test-optional pins `duckdb>=1,<2` at the newest, so it
  likely passes without the fix (null discrimination).
- marimo-05: a 1 s wait emulating Windows exec on POSIX; timing-sensitive under load, check 10/10.
- marimo-13: a CLI test; may depend on what CI's wheel job provides.
- marimo-19: type-level test through basedpyright (installed with test-optional; its bundled node must run offline).
- marimo-23: needs Python 3.12+ (3.13 is used, fine).
- marimo-26: needs ruff (installed by setup).

## For the admission session to try first

1. `setup` at marimo-01 and marimo-27: the install resolves under `--no-config --exclude-newer`, smoke import names
   the copy's path, `du -sh` of the copy and the venv.
2. Run the start's tests of marimo-13 (CLI) and marimo-19 (basedpyright) offline to see whether they can run at all.
3. Check marimo-08's duckdb version in the venv; drop the situation if < 2.
4. Run `test_package _server` for the time.
5. Rail setup + verify in a `.claude/worktrees/01` worktree, and check the `.claude`/`*skills*` ignore patterns
   against Rail's install.
