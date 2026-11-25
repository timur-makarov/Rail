# pandas (pandas-dev/pandas): bench settings

Files: `pandas.toml` (project, commands, Rail commands), `pandas.travel.json`. Nothing was installed, built or run
against pandas; every command carries `# unverified` in the TOML. Checked locally: the file loads through the bench's
own `sets.load` (dummy situation), every command passes `bash -n` (with `{files}`/`{package}` filled), `package_of`
over the changed source files of all 29 candidates, the travel globs against all hidden tests (no mismatch), the
`failed` regex on sample pytest lines, and `targets.sh` (the source-path -> test-target map) run against a copy of the
newest start's `pandas/tests` folder tree (empty files) for every candidate's source files.

## What I read

At the oldest start (pandas-29, `518f2a3c`, 2026-08-14) and the newest (pandas-02, `717bcd3e`, 2026-11-22):
`pyproject.toml` (build-system, requires-python, `[tool.pytest.ini_options]`), `meson.build`, `meson.options`,
`requirements-dev.txt`, `environment.yml`, `pixi.toml` (tasks build-pandas, uninstall-pandas, ci-test-pandas),
`.github/workflows/unit-tests.yml`, `.github/actions/build_pandas/action.yml`, `.github/actions/setup-conda/action.yml`,
`ci/run_tests.sh`, `.gitignore`, `AGENTS.md`; `pandas/conftest.py` at both (hypothesis import); the trees at both
commits; the `start..fix` file lists of all 29 candidates (gh compare).

## Toolchain and pins

- Python: no `.python-version`; `requires-python >=3.11`, CI tests 3.11-3.14. The bench uses 3.13 from uv (with
  headers, needed to compile) for all starts.
- Build: meson-python `>=0.19,<1`, meson `>=1.2.3,<2`, Cython `>3.1.0,<4`, numpy `>=2.0.0,!=2.5.0` (same at both
  ends; `wheel` and `versioneer[toml]` at the oldest, `versioneer` at the newest). No `setup.py`; no `build_ext`.
  meson fetches the `fast_float` and `xsimd` wraps into `subprojects/` (gitignored) at the first configure, so the
  first build must have network: setup does it.
- Test environment: `requirements-dev.txt` (87 lines old, 86 new) is the pip mirror of `environment.yml`; setup drops
  the docs/typing/GUI lines (sphinx, numpydoc, mypy, PyQt5, pytest-qt, asv, ...) and installs the rest with
  `--exclude-newer` at the start's commit time, then uninstalls the pandas some dependencies pull in (CI's
  `uninstall-pandas` task). Kept: pytest >=8.3.4, pytest-xdist, pytest-localserver, numba, numexpr, pyarrow, scipy,
  matplotlib, the io libraries. hypothesis is in the oldest list and `pandas/conftest.py` imports it; the newest has
  neither, so the old venvs get it and the new ones do not need it.
- Compilers: g++ and pkg-config via apt (Ubuntu 24.04 has gcc 13.3), ccache if apt can install it.

## Commands

| Command | What | Status |
|---|---|---|
| `setup` | apt g++/pkg-config/ccache; uv Python 3.13; venv in `$BENCH_CACHE/venvs/KEY` (hash of filtered requirements, build requires, Python, date) with build requirements + pip; writes `.git/bench/build.sh` and `.git/bench/targets.sh`; runs build.sh (wheel with `--no-build-isolation`, builddir `build/bench`, unpack `*.so` and `pandas/_version_meson.py` into the tree); removes `build/bench`; smoke import | unverified |
| `test_files` | build.sh (no-op unless compiled sources changed), then `python -m pytest -rfE -n 0 -m "not network and not db"` on the listed `pandas/tests/**/test_*.py` | unverified |
| `test_package` | build.sh, then `targets.sh PACKAGE` -> test folders/modules, `-n 4 -m "not slow and not network and not db and not single_cpu"`; docs-only packages run nothing and exit 0 | unverified; targets.sh fake-tree tested |
| `package_of` | `regex:^((?:pandas|doc|web|asv_bench)/[^.]*)` (the path without extension; targets.sh places it) | applied to all 29 fixes |
| `failed` | `^(?:FAILED|ERROR) (\S.*?)(?: - .*)?$` | sample lines only |
| Rail `setup` | link the venv; in a worktree copy `subprojects/*`, the built `*.so` and `_version_meson.py`, and `build/bench.stamp` from the main checkout; build.sh | unverified |
| Rail `verify` | build.sh; `test_common.py` plus targets.sh of changed files, same markers as test_package; no lint (pandas lints through pre-commit hooks fetched from the network) | unverified |

Why not CI's editable install: meson-python's editable mode installs a loader that records the absolute build and
source paths and rebuilds on import; in a moved copy it points at the setup folder. A wheel built once and unpacked
leaves ordinary extension modules next to the `.py` files, so `python -m pytest` from the root imports the copy's own
pandas with no install. `pandas/_version_meson.py` (written by the build, not covered by .gitignore) goes into
`.git/info/exclude` so it never shows in a diff; the `*.so` files are gitignored.

Fixes touching `.pyx`/`.pxd`/`.c`/`.h`: build.sh hashes every compiled source plus `meson.build`/`generate_*.py`
and compares with `build/bench.stamp`. If they differ (the oracle fix or an agent's change touched them), it rebuilds
offline (`pip wheel --no-index --no-build-isolation`, subprojects already present) and swaps in the new modules. Seven
of the 29 fixes do this (pandas-06, 18, 21, 23, 24, 26, 29: tslibs/timezones, window/aggregations, testing.pyx,
lib.pyx). `build` is in `build_dirs`, so the stages restore it from the sealed copy rather than carry a stale one.

## Sizes and times (estimates)

- Source tree about 63 MB, 3,000 files; with the built modules (~120 MB of `.so`) and subprojects about 200 MB per
  copy. Venv about 1.5-2 GB in the uv cache (pyarrow, numba/llvmlite, scipy, matplotlib), hardlinked per venv.
- First build: 6-10 minutes on 4 cores (about 50 Cython modules); a rebuild after a `.pyx` change is a full rebuild
  (the build folder is dropped after setup because it holds absolute paths), 6-10 minutes again, less with ccache
  warm (the C compile of unchanged modules is cached by content; Cython still re-runs).
- `test_files` on one module: 10 s to 2 min (`pandas/tests/frame/test_constructors.py` is among the largest);
  `test_package` 1-6 minutes, the io folders up to 10-15. timeout_minutes is 60.

## Traps

- Compiled parts: the one real cost. Every graded copy whose fix (or agent change) touches compiled code rebuilds in
  the test step; the 10/10 rule then runs build.sh ten times, but only the first rebuilds (the stamp is written in the
  copy). Watch the grading budget for those seven.
- Absolute paths: none left in the copy (build folder removed; `.so` files carry no source paths that matter). The
  venv's scripts point at the cache, which does not move.
- Generated files: `pandas/_version_meson.py` (excluded), `pandas/_libs/**/*.so` (gitignored), `subprojects/*/`
  (gitignored), `build/bench.stamp` (in build_dirs).
- Warnings as errors: `filterwarnings = error` plus `--strict-markers --strict-config` in pytest config; a newer
  dependency than CI had can turn a DeprecationWarning into a test error. `--exclude-newer` at the start time keeps
  versions close to CI's.
- `PYTHONWARNDEFAULTENCODING=1` is CI's env; kept.
- Network at test time: tests marked `network` (and `db`, which need MySQL/Postgres) are deselected; a few io tests use
  `pytest-localserver` on loopback, which works offline with loopback up.
- `--capture=no` is in addopts; output is long but the `-rfE` summary still ends it.
- Rail clash: the newest start has `AGENTS.md`, `.claude/` and `.agents/` at the root (tracked); Rail's install may
  collide with them. The TOML sets no `clash`; the admission session should decide after a Rail install.
- `subprojects/` holds tracked `*.wrap` files and `packagefiles/`; only the downloaded `fast_float*`/`xsimd*` folders
  are gitignored (`/subprojects/*` with exceptions), which is what Rail setup copies into worktrees.

## Candidates unlikely to pass admission

- pandas-06: the tests bite only with python-dateutil >= 3; at its start date (2026-11-03) that release may not exist
  under `--exclude-newer`, so the hidden tests could pass without the fix (null discrimination).
- pandas-04: needs numexpr installed (it is, from requirements-dev); the test monkeypatches the engine; fine if numexpr
  imports on 3.13.
- pandas-16: online ewm needs numba; numba must support Python 3.13 at the start date (it does from 0.61).
- pandas-24: builds its own TZif file and asserts strictly increasing transitions; touches `timezones.pyx`, so it also
  depends on the rebuild path working.
- pandas-15, pandas-22: plotting/io paths that may need optional libraries (matplotlib present; openml repro is
  network-only but the hidden test is local).

## For the admission session to try first

1. Run `setup` for pandas-02 (newest) and pandas-29 (oldest): build succeeds offline after the first, smoke import
   names the copy's path, `du -sh` of the copy.
2. `cp -a` the copy and run `test_files` with pandas-29's hidden tests on the fix: build.sh must rebuild
   (testing.pyx changed) and the tests pass; time the rebuild.
3. Run `test_package` with `pandas/core/indexes/range` to see targets.sh pick `pandas/tests/indexes` and the time.
4. Check pandas-06 discriminates at all (python-dateutil version in the venv).
5. Rail setup + verify in a `.claude/worktrees/01` worktree: the copied modules import and build.sh is a no-op.
