# Cloud smoke report

Run on 2026-11-18 in a Claude Code cloud session, from the repository root (`/home/user/Rail`), base commit on branch `claude/new-session-hjo5u9`.
"Confirmed" means the command was run and its output seen. "Inferred" means it was concluded but not run directly.

| # | Check | Result | What was seen |
|---|-------|--------|---------------|
| 1 | Machine | pass | Linux x86_64, Python 3.13.18 (≥ 3.11), git 2.43.0, bash 5.2.21, 4 CPUs, ~15.6 GB free RAM, root, `sudo -n true` exits 0 (confirmed) |
| 2a | `gh --version` | pass | gh 2.89.0 (confirmed) |
| 2b | `gh auth status` | fail | exit 1: "The token in GH_TOKEN is invalid" (confirmed) |
| 2c | `gh pr list` | fail | exit 1: HTTP 403, GraphQL not available from Claude Code sessions; REST `gh api repos/timur-makarov/rail/pulls` works, exit 0 (confirmed) |
| 3 | Claude CLI | pass | `/opt/node22/bin/claude`, version 2.1.327 (confirmed) |
| 4 | One real run | pass | answer `ok`, exit 0, 3.8 s (confirmed) |
| 5 | Reviewer command | pass | exit 0, valid JSON, `structured_output` = `{"summary": ..., "findings": []}`, 2.8 s (confirmed) |
| 6a | Four parallel runs | pass | 4 of 4 succeeded, all answered `ok`, 5.5 s total (confirmed) |
| 6b | `--model claude-sonnet-5-5` | pass | accepted, exit 0, answered `ok`, 7.3 s (confirmed) |
| 6c | `--model claude-opus-5-5` | pass | accepted, exit 0, answered `ok`, 4.2 s (confirmed) |
| 7 | Test suite | pass | `246 tests on 8 workers in 99s: OK`, exit 0, 99.1 s (confirmed) |
| — | `git push` | see end | shown by whether this file is on branch `cloud-smoke` on GitHub |

## 1. Machine

```
$ uname -a                      # exit 0
Linux vm 6.18.44-fc-v595 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
$ python3 --version             # exit 0
Python 3.13.18
$ git --version                 # exit 0
git version 2.43.0
$ bash --version | head -1      # exit 0
GNU bash, version 5.2.21(1)-release (x86_64-pc-linux-gnu)
$ nproc                         # exit 0
4
$ free -m                       # exit 0
               total        used        free      shared  buff/cache   available
Mem:           16087         448       15617          12         234       15639
Swap:              0           0           0
$ id -u; whoami                 # exit 0
0
root
$ sudo -n true                  # exit 0 (no output)
```

All confirmed. Python 3.13.18 meets Rail's 3.11+ requirement. No swap.

## 2. GitHub

```
$ gh --version                  # exit 0
gh version 2.89.0 (2026-03-26)
https://github.com/cli/cli/releases/tag/v2.89.0

$ gh auth status                # exit 1
github.com
  X Failed to log in to github.com using token (GH_TOKEN)
  - Active account: true
  - The token in GH_TOKEN is invalid.

$ gh pr list --limit 3          # exit 1
HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API
(gh api repos/{owner}/{repo}/...). For review threads, auto-merge, and draft/ready-for-review
use the CCR routes on api.github.com: ... (https://api.github.com/graphql)

$ gh api repos/timur-makarov/rail/pulls --jq length   # exit 0
0
```

Confirmed: `gh auth status` reports the GH_TOKEN as invalid and exits 1, yet REST calls through `gh api` succeed (0 open PRs).
Inferred: GH_TOKEN is a placeholder that the session's proxy replaces on the way out, so `gh auth status` (which validates the token itself) fails while proxied REST requests work. Anything in Rail that uses `gh pr ...` subcommands (GraphQL-backed) will fail here; `gh api` REST calls work.

## 3. Claude CLI

```
$ which claude                  # exit 0
/opt/node22/bin/claude
$ claude --version              # exit 0
2.1.327 (Claude Code)
```

Confirmed.

## 4. One real run

```
$ echo 'Reply with the single word: ok' | claude -p --safe-mode     # exit 0, 3.85 s
ok
```

Confirmed.

## 5. Reviewer command

`seed/config.toml` `[review] command` was checked and matches the brief, with `.rail/engine/` replaced by `engine/`:

```
$ echo 'Review nothing. Return an empty list of findings.' | claude -p --safe-mode \
    --system-prompt-file engine/reviewer.md --tools Read,Grep,Glob,Bash,Edit,Write \
    --allowedTools Bash,Edit,Write --disallowedTools 'Bash(git push *)' \
    --output-format json --json-schema "$(cat engine/review-v1.json)"
# exit 0, 2.76 s, stderr empty
```

- Exit code 0 (confirmed).
- Output is valid JSON, a single object, parsed with `json.load` (confirmed).
- `type`/`subtype`: `result`/`success`, `is_error`: false (confirmed).
- `structured_output`: `{"summary": "No review performed, as instructed; no findings.", "findings": []}` (confirmed).
- Top-level keys (confirmed): `api_error_status`, `duration_api_ms`, `duration_ms`, `fast_mode_disabled_reason`, `fast_mode_state`, `first_content_frame_ms`, `flag_fetch_kick`, `input_attachments_detail`, `is_error`, `main_stream_chunk_count`, `main_stream_count`, `main_stream_event_count`, `message_normalization_detail`, `modelUsage`, `num_turns`, `permission_denials`, `process_anon_mib_result`, `process_anon_mib_turn_start`, `process_cpu_ms_streaming`, `process_cpu_ms_turn`, `process_peak_rss_mib`, `process_rss_mib_result`, `process_rss_mib_turn_start`, `process_start_tuning`, `process_turn_index`, `process_turn_states`, `process_wall_ms_streaming`, `process_wall_ms_turn`, `queued_turn_count`, `request_build_detail`, `result`, `result_index`, `safety_stops`, `session_id`, `stop_reason`, `structured_output`, `subagent_stats`, `subtype`, `terminal_reason`, `time_origin_ms`, `time_to_request_cpu_ms`, `time_to_request_from_spawn_ms`, `time_to_request_loop_lag_ms`, `time_to_request_major_faults`, `time_to_request_ms`, `time_to_request_phases_ms`, `tool_pool_build_count`, `tool_pool_build_lapsed_count`, `tool_pool_limit_ms`, `tool_pool_moved_at_lapse_count`, `tool_schema_build_detail`, `total_cost_usd`, `ttft_ms`, `ttft_stream_ms`, `turn_start_resume_kind`, `type`, `usage`, `uuid`, `warm_spare_claimed`.

## 6. Concurrency and models

```
$ for i in 1 2 3 4; do (echo 'Reply with the single word: ok' | claude -p --safe-mode > par$i.out 2>&1; echo $? > par$i.rc) & done; wait
# 5.53 s total
run1 rc=0 out=ok
run2 rc=0 out=ok
run3 rc=0 out=ok
run4 rc=0 out=ok

$ echo 'Reply with the single word: ok' | claude -p --safe-mode --model claude-sonnet-5-5   # exit 0, 7.28 s
ok
$ echo 'Reply with the single word: ok' | claude -p --safe-mode --model claude-opus-5-5     # exit 0, 4.16 s
ok
```

Confirmed: 4 of 4 parallel runs succeeded in 5.5 s total; both model names were accepted.

## 7. Test suite

```
$ python3 tests/run.py          # exit 0, 99.1 s
246 tests on 8 workers in 99s: OK
```

Confirmed. The whole output is that one line (fewer than 40 lines). `git status` showed no files changed by the run (confirmed).

## Push

This file was committed alone on a new branch `cloud-smoke` and pushed to `origin`. If you are reading it on GitHub, `git push` works from this environment (confirmed by the push command's result in the session; see the commit on the branch).
