# ha-core (home-assistant/core): bench settings

Files: `ha-core.toml` (project, commands, Rail commands), `ha-core.travel.json`. Nothing was installed, built or run
against Home Assistant; every command carries `# unverified` in the TOML. What was checked locally: the file loads
through the bench's own `sets.load` (with a dummy situation), every command (with `{files}`/`{package}` filled) passes
`bash -n`, `package_of` was applied to the changed source files of all 147 candidates, the travel globs were checked
against every candidate's hidden tests (no mismatch), the `failed` regex was tried in Python on sample pytest lines,
and `test_files`, `test_package` and Rail `verify` were run (with a `mapfile` shim; local bash is 3.2) against a fake
tree with HA's folder shape to see the pytest arguments they build.

## What I read

At the oldest starts (ha-core-146 `5eada1d9`, ha-core-147 `54ad0665`, both 2026-07-02) and the newest (ha-core-01,
`f487f4d1`, 2026-11-25): `.github/workflows/ci.yaml` (jobs prepare-base, pytest-full, pytest-partial, the
`info` job that reads `.python-version`), `.github/actions/restore-or-build-venv/action.yml` (new; at the old start
the same steps sit inline in ci.yaml), `script/setup`, `script/bootstrap`, `.python-version`, `pyproject.toml`
(requires-python, `[tool.pytest.ini_options]`), `requirements.txt`, `requirements_all.txt` (newest),
`requirements_test.txt`, `homeassistant/package_constraints.txt`, `.gitignore`. Also the trees of `packages/` at
`61e6a866` (2026-11-11, has `packages/pytest-homeassistant` and `packages/hassfest`) and `b00174a3` (2026-10-25,
neither), the start dates of all 147 candidates, and the `start..fix` file lists of all 147 (gh compare).

## Toolchain and pins

- Python: `.python-version` is 3.14.5 at the oldest start and 3.14.10 at the newest; `requires-python >=3.14.2`.
  CI uses exactly `.python-version`. setup installs that version with uv into `$BENCH_CACHE/python`, falling back to
  the newest 3.14 uv knows when uv 0.11.32 does not know the patch release (3.14.10 may be newer than its list).
- Packages: `requirements.txt` (61 lines, core), `requirements_all.txt` (about 1,190 `==` pins, every integration's
  library), `requirements_test.txt` (48), `homeassistant/package_constraints.txt` (pins for transitive packages).
  There is no `requirements_test_all.txt` any more; CI installs `-r requirements_all.txt -r requirements_test.txt`.
- OS packages CI installs first: bluez, ffmpeg, libturbojpeg, libxml2-utils, libudev-dev, the libav*-dev set, g++,
  pkg-config. setup installs them best-effort with apt (names checked against Ubuntu 24.04 by memory only).
- From 2026-11 on, the pytest plugin, test helpers (`tests/common.py` moved) and hassfest live in
  `packages/pytest-homeassistant` and `packages/hassfest`, installed editable; the plugin is found through its
  `pytest11` entry point, so it must be installed, not just on the path.

## Commands

| Command | What | Status |
|---|---|---|
| `setup` | apt (best effort); uv Python from `.python-version`; venv in `$BENCH_CACHE/venvs/KEY` (KEY: hash of Python path, requirement files, constraints, pyproject, packages/*): `uv pip install --no-config --exclude-newer START_TIME`, requirements then all+test, with a one-by-one fallback that records failures in `bench-skipped.txt`; editable `-e . [-e packages/...]` with `editable_mode=compat`; .pth made relative; `.venv` symlink; `script.translations develop --all`; `git repack`; smoke import + `pytest --co tests/test_core.py` | unverified |
| `test_files` | translations, then CI's pytest flags (`-b -X dev -m pytest -qq -p no:sugar -o console_output_style=count --numprocesses=4`) with `-rfE` and `--timeout=60`; snapshot `.ambr` -> its test module, conftest.py -> its whole integration folder, other fixtures -> their folder unless a module there is listed | unverified; fake-tree tested |
| `test_package` | the nearest existing `tests/<package>` folder, `--dist=loadfile`; `.` and `components` alone -> core subset (test_core, test_config_entries, test_setup, test_loader) | unverified; fake-tree tested |
| `package_of` | `regex:^homeassistant/(.+)/[^/]+$` (components/NAME, helpers, helpers/template/extensions, ...) | applied to all 147 fixes |
| `failed` | `^(?:FAILED|ERROR) (\S.*?)(?: - .*)?$` | checked on sample lines (not on real HA output) |
| Rail `setup` | link the main checkout's `.venv` target, regenerate translations | unverified |
| Rail `verify` | ruff check + format --check on changed .py; pytest on tests/test_core.py + changed integrations' test folders + changed test files | unverified; fake-tree tested |

How each copy imports its own code: the venv is not in the copy. setuptools' compat editable mode writes a `.pth`
holding the setup copy's absolute path; setup rewrites it to `../../../..` (and `../../../../packages/...`), which
Python resolves against the site-packages path it reached through the copy's own `.venv` symlink (sys.prefix comes
from the unresolved executable path). Commands also export `PYTHONPATH` to the copy and run `python -m pytest` from
the root. Rail worktrees link the same venv target and so import the worktree's code. Not run anywhere yet: this is
the first thing to confirm (setup's smoke import asserts it for the setup copy only).

## Sizes and times (estimates)

- Source tree about 235 MB, 35,500 files at the newest start; with `.git` repacked and translations about 300-330 MB
  and 36k inodes per copy. The bench keeps a sealed copy plus graded copies per situation: for 147 situations that
  is far beyond the 30 GB disk. Even 40 situations (x2 copies) is about 25 GB.
- The uv cache for one requirement set is about 4-8 GB of unpacked wheels (opencv, numpy/scipy, pandas, pyarrow and
  ~1,200 smaller libraries; a guess, not measured). Each later start adds only the changed pins.
  Each venv is hardlinked (no file data) but costs ~25k directories; no bytecode is compiled ahead (UV_COMPILE_BYTECODE
  off for HA on purpose).
- First venv: 20-40 minutes (download plus a few sdist builds); later venvs a few minutes from the cache. Translations
  about 30 s. A hidden-test run of one integration module: 20 s to 2 min; `test_package` of a large integration
  (mqtt, zha, recorder, homekit) 10-15 minutes on 4 cores; the core subset about 4 minutes. timeout_minutes is 90.

## Traps

- Disk and inodes: the biggest risk. 147 starts on 75 distinct days; requirements_all changes most days, so dozens of
  venvs and a large uv cache. Admit HA in batches and drop copies/venvs of rejected situations, or cap it at ~30-40.
- Absolute paths: only in the editable `.pth` files (rewritten) and in `__pycache__` (harmless). The venv's own
  scripts (`bin/pytest`, `bin/hass`) have the cache path in their shebangs, which is fine since the venv does not move.
- Generated files: `homeassistant/components/*/translations/en.json` (gitignored) from `strings.json`. Eight fixes
  change a `strings.json`, so every test command regenerates them first (otherwise config-flow tests check stale
  strings). `.venv` is a symlink, which `.venv/` patterns in .gitignore do not match, so setup adds `/.venv` to
  `.git/info/exclude`.
- Compiled parts: none in HA; a few requirements may need building from sdist on 3.14 (g++, libudev-dev, ffmpeg dev
  headers). The fallback installs the rest and lists what failed; a hidden test of an integration whose library did
  not install fails at import (admission will then reject it, which is correct but should be looked at).
- Network at test time: HA's tests block sockets themselves (pytest-socket 0.8.1 is in requirements_test.txt, used by
  HA's plugin) and the bench runs offline; nothing in the candidates needs network.
- Timeout: CI uses `--timeout=9`; here 60 because the first import on a fresh copy writes bytecode and 4 workers on 4
  CPUs are slower than CI's runners. A hidden test that relies on a 9 s timeout to fail would not exist.
- `-qq`: CI's verbosity. pytest still prints the `-rfE` summary lines at -qq in recent versions; if it does not, use
  `-q`. Check on the first real run.
- `PYTHONASYNCIODEBUG=1` is CI's setting (env); it slows tests a little and makes some leaks into failures, as in CI.
- Rail verify must pass at the start: with no changes it runs tests/test_core.py only. ruff comes in through
  `requirements_test.txt` -> `-r requirements_test_pre_commit.txt` (ruff 0.15.19 old, 0.17.5 new), so `python -m
  ruff` is in the venv; `--force-exclude` keeps it to the files pyproject's ruff config covers.

## Candidates unlikely to pass admission

- ha-core-121, ha-core-33: the hidden change is a conftest/fixture only; the conftest mapping runs the whole
  integration folder, which should discriminate, but folder-wide tests may include unrelated failures at the start.
- ha-core-138: the test helper in `common.py` changes (tests/components/X/common.py, travels with tests); fine if the
  helper is under tests/, as the file list says.
- Situations whose integration library needs an sdist build that fails on 3.14 (unknown until setup runs): the
  fallback list `bench-skipped.txt` names them.
- ha-core-130, ha-core-110: timing tests (freezer, reconnect) under 4 workers; watch for flakes in the 10/10 rule.
- Starts before 2026-11-11 have `tests/common.py` and the plugin in `tests/`; starts after use
  `packages/pytest-homeassistant`. Both are handled (the editable list adapts), but the first run of each kind should
  be watched.

## For the admission session to try first

1. Run `setup` for ha-core-01 (newest) and ha-core-147 (oldest) and confirm: Python install, `bench-skipped.txt`
   empty or short, the smoke import, `du -sh` and `df -i` of the copy and of `$BENCH_CACHE`.
2. Copy the folder elsewhere (`cp -a`) and run `test_files` there with the hidden tests of one situation: confirm the
   imported `homeassistant` is the copy's (`python -c 'import homeassistant; print(homeassistant.__file__)'`).
3. Check that `-qq -rfE` prints `FAILED ...` lines (break one assertion by hand).
4. Rail setup + verify in a `.claude/worktrees/01` worktree at the start: passes, and ruff is present.
5. Decide the HA cap from the measured per-copy size and cache growth before admitting more.
