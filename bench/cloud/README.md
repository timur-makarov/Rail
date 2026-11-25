# Scripts for the cloud sessions

A cloud session's machine pauses a few minutes after the session's turn ends and kills every process; files stay
(fulltest `CLOUD-CHECK-RESULT.md`). These scripts let a session run long work in the background, wait on it with
foreground calls, start it again after a pause, and keep the results. They use the bench's own code and change none
of it. The store is `/srv/rail-bench` (`BENCH_STORE`): the Rust project files of set 2026-12 name paths under it.

| Script | What it does |
|---|---|
| `jobs.py` | A resumable job runner: `start` (background), `wait` (foreground, at most M minutes), `status`. A job is one line, ID, a tab, a bash command; a job cut off by a pause runs again. It stops starting jobs on a `STOP` file, under 3 GB of free disk or 5% of inodes, or after N failures in a row. Jobs run without the session's forge, cloud and messaging tokens; `exec` runs one foreground command the same way. |
| `joblist.py` | Writes a job list: one admission per situation, or an arm's runs in rounds (run 1 of every situation, then run 2, ...), each run followed by `prune_runs.py`. |
| `admit_one.py` | `bench admit` on one situation, then the two checks every agent run depends on, with the network cut: the hidden tests with the fix, and Rail's setup and verify in a new worktree. Writes `OUTDIR/ID.json` with times and sizes. |
| `admission_table.py` | The admission results as Markdown tables per project, the reasons counted, the admitted ids. |
| `signin_probe.py` | Which variables a scrubbed child needs to sign in (names only, never values); writes a bench config with that `pass_env`. |
| `lock_check.py` | A locked child as the bench makes one: does it answer, is the web blocked, can it read the store, has it a forge token; with `--project`, the cache paths its shell sees. |
| `proxy_vs_cli.py` | A run's proxy token counts against the CLI's own totals, per role. |
| `restore_check.py` | A saved stage unpacked as saved against the same stage restored as `bench run --from` restores it. |
| `killtree.sh` | Kill a process and everything under it, sessions of their own included (to kill a run mid-way). |
| `odd_runs.py` | The failed or odd runs, each with its streams, for reading by hand. |
| `choose.py` | After the hardness runs: the hardness table, the easy ones dropped, fifteen drawn per project (twelve work, three held), written with `--apply`. |
| `usage_check.py` | How near the account's usage limit the runs are, from the rate-limit events in the streams; exit 3 at the stop line. |
| `restore_store.py` | Build the admitted situations' sealed copies again from the admission records (a new or reclaimed machine, or a store pruned for disk). |
| `prune_runs.py` | Delete the working copy and temp folder of every graded run (the bench keeps them; a Rust copy is gigabytes), and old scratch. |
| `keep.py` | Copy results into a clone of the results repository, in pieces under 90 MB, commit and push; `--no-stages` leaves out runs' saved stages. |

The prompts that drive them are kept outside this repository, in the fulltest folder's `cloud/`.
