# sqlfluff (sqlfluff/sqlfluff, a reserve): bench settings

Files: `sqlfluff.toml` (project, commands, Rail commands), `sqlfluff.travel.json`. Nothing was installed or run
against sqlfluff; every command carries `# unverified` in the TOML. Checked locally: the file loads through the bench's
own `sets.load` (dummy situation), every command passes `bash -n`, `package_of` over the changed source files of all
40 candidates, the travel globs against all hidden tests (no mismatch), the `failed` regex on sample pytest lines, and
`test_files`/`test_package`/Rail `verify` run against a fake tree shaped like sqlfluff's `test/` (with real fixture
names) to see the pytest arguments, e.g. a hidden `test/fixtures/rules/std_rule_cases/ST03.yml` plus
`test/fixtures/dialects/oracle/select_into_record_fields.sql` gives
`test/dialects/dialects_test.py test/rules/yaml_test_cases_test.py -k "([ST03_) or ([oracle-select_into_record_fields.sql)"`.

## What I read

At the oldest start (sqlfluff-40, `4d335e9c`, 2026-07-09) and the newest (sqlfluff-01, `11d4de0a`, 2026-11-22):
`pyproject.toml` (requires-python, build backend, entry points, pytest options and markers), `requirements_dev.txt`,
`tox.ini` (`[testenv]`, envlist), `.github/workflows/ci-tests.yml` (and the reusable `ci-test-python.yml` it calls),
`.gitignore`, `test/conftest.py` (`get_parse_fixtures`), `test/dialects/dialects_test.py`,
`test/rules/yaml_test_cases_test.py`, `test/rules/std_fix_auto_test.py`; `src/sqlfluff/utils/testing/rules.py`
(`load_test_cases`, the `RULE_case` ids) at the newest; the `start..fix` file lists of all 40 candidates.

## Toolchain and pins

- Python: `requires-python >=3.10` at both; CI tests 3.10-3.14 (lint jobs on 3.14). No `.python-version`. The bench
  uses 3.13 from uv for every start.
- Dependencies: few and loose (platformdirs, chardet, click <8.6, colorama, diff-cover, Jinja2, pathspec, pyyaml,
  regex, tblib, tqdm); `requirements_dev.txt` (about 30 lines: ruff, hypothesis, pytest, pytest-xdist, mypy, types-*,
  tox, ...) installed with `--exclude-newer` at the start's commit time.
- `sqlfluffrs/` (Rust, optional parser backend) exists at the newest start; CI runs the Python suites with and without
  it (`with-rust: ""` legs are pure Python). The bench uses the pure-Python legs; no Rust toolchain needed.
- The rules, dialects and templaters are registered through the package's own entry points (group `sqlfluff`), so the
  package must be installed (editable, compat mode) for its metadata; the code still comes from the copy (relative
  `.pth`, `PYTHONPATH=src`). tox also installs `plugins/sqlfluff-plugin-example`, which some tests expect; setup does
  too.

## Commands

| Command | What | Status |
|---|---|---|
| `setup` | uv Python 3.13; venv in `$BENCH_CACHE/venvs/KEY` (pyproject, requirements_dev, plugin pyproject, Python, date): `-r requirements_dev.txt`, then `-e . -e plugins/sqlfluff-plugin-example` (compat), .pth made relative; `.venv` symlink; smoke: copy's sqlfluff imported and `list_rules()` non-empty | unverified |
| `test_files` | test modules run whole; dialect fixtures `test/fixtures/dialects/D/NAME.sql|.yml` -> `-k "[D-NAME.sql"` on dialects_test.py; rule yml -> `-k "[RULE_"` on yaml_test_cases_test.py (rule read from the file's `rule:` line); autofix case folders -> `-k "[D-CASE]"` on std_fix_auto_test.py; all with `-n 0` | unverified; fake-tree tested |
| `test_package` | nearest existing `test/<package>` folder, `-n 4`; `.` -> `test/api test/core/config` | unverified; fake-tree tested |
| `package_of` | `regex:^src/sqlfluff/(.+)/[^/]+$` (dialects 28, rules/* 13, utils/reflow 2, core/* 5, cli 1, "." 3) | applied to all 40 fixes |
| `failed` | `^(?:FAILED|ERROR) (\S.*?)(?: - .*)?$` | sample lines only |
| Rail `setup` | link the venv | unverified |
| Rail `verify` | `ruff check` on changed .py; pytest on test/api plus the folders of changed sources and fixtures and changed test modules | unverified; fake-tree tested |

env: `SQLFLUFF_TESTENV=1` (tox's setenv), `UV_OFFLINE`, `UV_PYTHON_DOWNLOADS=never`.

## Sizes and times (estimates)

- Source tree about 28 MB, 7,000 files (mostly fixtures); copy about 40 MB. Venv about 300 MB in the uv cache.
- setup: 1-2 minutes first time, seconds later. `test_files` with `-k` selections: 10-60 s (collection of the
  parametrized dialect tests takes most of it). `test_package` of `dialects` (about 10,000 parametrized cases) or
  `rules`: 5-8 minutes on 4 cores; other folders under 2. timeout_minutes is 30.

## Traps

- The `-k` mapping is the main risk: it relies on parametrize ids `D-NAME.sql`, `RULE_case` and `D-CASE` staying as
  read at both starts. If an id format differs at some start, `-k` selects nothing and pytest exits 5 (no tests),
  which fails admission visibly rather than passing silently. A `.yml` parse-tree fixture whose `.sql` sibling is not
  hidden maps to the same `[D-NAME.sql` id, which is right (the yml is the expected tree of that sql).
- Fixture files that are hidden but not tests (e.g. a new `.sqlfluff` config inside a fixture folder) ride along
  unused; their effect shows through the test that reads them only if that test is selected.
- Generated files: `test/generate_parse_fixture_yml.py` regenerates the `.yml` parse trees; the fixes ship them, so
  nothing is generated at test time.
- `-n 0` in test_files: `std_fix_auto_test` and the dialect tests are deterministic, but xdist workers would add
  collection time for small selections.
- No absolute paths in the copy except the relative-made `.pth`; no compiled parts; no network at test time.
- Starts that change `requirements_dev.txt` or `pyproject.toml` get their own venv (key includes them and the date).

## Candidates unlikely to pass admission

- sqlfluff-05: cross-drive test needs `os.path.relpath` to raise ValueError (a Windows behaviour emulated with a
  monkeypatch); fine on Linux if it is mocked, else skipped (null discrimination). Its fix also touches `.editorconfig`/
  docs (package ".").
- sqlfluff-20: autofix case; the case folder id must match `[D-CASE]`; check the fixture path depth.
- sqlfluff-36: hidden tests are a dialect fixture plus an ST03 rule yml; the `-k` expression combines both (tested
  on the fake tree).
- sqlfluff-02, 14, 15, 18, 22, 24, 26, 28, 30: the parse-tree `.yml` pins the exact tree; they discriminate, but an
  oracle check that the fix's tree matches is only as good as the yml hash in the fixture (sqlfluff checks it).

## For the admission session to try first

1. `setup` at sqlfluff-01 and sqlfluff-40; smoke prints a rule count.
2. `test_files` for sqlfluff-36 (dialect + rule yml) without and with the fix: the `-k` selection collects > 0 tests
   and fails without the fix.
3. `test_files` for one autofix situation (sqlfluff-20) to confirm the `[D-CASE]` id.
4. `test_package dialects` time on 4 cores.
5. Rail setup + verify in a `.claude/worktrees/01` worktree at the start.
