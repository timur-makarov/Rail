# Hardness runs of set 2026-12: plain Haiku 5.5, three runs per admitted situation

```
LANGUAGE        =            # fill in: python, typescript, rust or go
PROJECTS        =            # empty: the names in admission/IN-PLAY.txt on the results branch
CC_VERSION      =            # the Claude Code version every child runs (README); empty: npm's "stable" tag, recorded
RESULTS_BRANCH  =            # empty: LANGUAGE; give the same value the admission session was given
SETS_BRANCH     =            # empty: bench-sets-<RESULTS_BRANCH as given here>
```

You are a Claude Code session on a cloud machine, started on the Rail repository. The admission session for this
language has admitted situations and pushed working project settings. Your job: run plain Claude Code with Haiku 5.5
(arm `plain-haiku`) three times on every admitted situation of the projects in play, through the bench, with every
child's network locked and its cost read through the bench's proxy; then drop the easy ones (solved 3 of 3) and draw
fifteen per project. Haiku has no arm of its own: these runs are never counted in the results. You work alone and
nobody watches; the person reads your final message. Every step can be started again: if your context was compacted,
the machine paused, or a person sent "go on", read `/srv/rail-bench/session/PROGRESS-HARDNESS.md` and continue at
the first step not marked done.

If LANGUAGE is empty, stop at once and say so.

## Rules

1. **Never end your turn while work runs.** Runs go as background jobs with `bench/cloud/jobs.py`; you wait with a
   foreground Bash call, `jobs.py wait STATE --minutes 55` (two runners: alternate between them), with the Bash
   tool's `timeout` set to 7200000. The machine pauses a few minutes after your turn ends and kills every process
   (files stay), so your turn ends only with the final message. If `jobs.py wait` exits 4 (the runner is gone: the
   machine paused), start it again with the same `jobs.py start` command: finished runs are not run again, and a run
   cut off part-way starts again (a plain run has no stages to resume from).
2. **Start every Bash call with `. /srv/rail-bench/session.env &&`** once step 2 has written it.
3. **Progress.** Append a line to `/srv/rail-bench/session/PROGRESS-HARDNESS.md` when a step starts and ends
   (`HARDNESS step N start`, `HARDNESS step N done: <one line>`), and keep there what you need after a compaction
   (state folders, which projects, what was retried). Other prompts keep their own progress files.
4. **Credentials.** Never print, log, store or commit a credential: no token, key, password, cookie, or the value of a
   variable that holds one; no `env`, `printenv` or `set` without a filter that drops values. The sign-in probe prints
   names only; keep it that way. Never put a token in a git remote, a URL, a file or the bench config.
5. **Children.** Start model children only through the bench (`bench run`, `bench check-arm`) and its scripts
   (`signin_probe.py`, `lock_check.py`): they give each child a scrubbed environment (only `pass_env`, a fresh HOME
   and TMPDIR), a fixed tool list and a locked network. Never run `claude -p` yourself, and never add a GitHub, cloud
   or messaging variable to `pass_env`. Every job runs without the session's forge, cloud and messaging credentials
   (`jobs.py` drops them: the projects' tests and the graded code run there); run the bench and its scripts in the
   foreground the same way: `python3 $SRC/bench/cloud/jobs.py exec -- <command>`.
6. **What you may change.** The bench config at `/srv/rail-bench/bench-config.toml` (step 7), and, through
   `choose.py --apply` only, the project files' `half` and `bench/sets/2026-12/CHOSEN.toml`. Nothing else in the
   repository. A fault of the bench is reported, not fixed; if a script under `bench/cloud/` stops a step, you may
   make the smallest fix, commit it on its own on `SETS_BRANCH`, and list it in the final message.
7. **Git.** No `git stash`, no force push, no merge, no rebase of a branch others push to. Push only `SETS_BRANCH` to
   the Rail repository's `origin`, and the results branch. Never change the branch of the folder the session started
   in.
8. **Keep results often:** at least every two hours, and at the end of every step.
9. **Stop rules.** Stop starting runs (`touch STATE/STOP` in every state folder), wait for the running ones to end,
   keep everything, and write the final message with `stopped:` and the reason when:
   - the sign-in probe fails, `check-arm` fails, or runs end "to run again" because of sign-in;
   - `usage_check.py` exits 3 (the account's usage limit is near or hit);
   - free disk of `/srv` stays under 3 GB after `prune_runs.py`, or inode use is over 95%;
   - the same step fails three times in a row (a runner stopped for "3 jobs in a row failed" counts once per stop);
   - the network lock check shows the web reachable from a locked child.

## Step 1. The checkout

```
mkdir -p /srv/rail-bench/session /srv/rail-bench/jobs /srv/rail-bench/hardness
RAIL_REPO=$(git rev-parse --show-toplevel)       # in the folder the session started in
```

`RESULTS_BRANCH` defaults to LANGUAGE; `SETS_BRANCH` to `bench-sets-<RESULTS_BRANCH as given>`. The settings branch
must exist: the admission session pushed it.

```
git -C "$RAIL_REPO" fetch -q origin "+refs/heads/$SETS_BRANCH:refs/remotes/origin/$SETS_BRANCH" \
  || { echo "no $SETS_BRANCH on origin: admission has not pushed its settings"; exit 1; }
if [ ! -e /srv/bench-src/.git ]; then
  git -C "$RAIL_REPO" worktree add -B "$SETS_BRANCH" /srv/bench-src "origin/$SETS_BRANCH"
else
  git -C /srv/bench-src status --short; git -C /srv/bench-src log -1 --format='%H %s'
fi
```

If `/srv/bench-src` exists (this machine ran the admission, or a restart), it must be on `SETS_BRANCH` and not behind
`origin/$SETS_BRANCH` (`git -C /srv/bench-src merge-base --is-ancestor origin/$SETS_BRANCH HEAD`); if it is behind and
has no commits of its own, `git -C /srv/bench-src merge --ff-only origin/$SETS_BRANCH`; otherwise stop and say so.

## Step 2. The session's environment file

Write `/srv/rail-bench/session.env` (or check it, if the admission left one; no secrets in it, ever):

```
export BENCH_STORE=/srv/rail-bench
export SRC=/srv/bench-src
export SET=/srv/bench-src/bench/sets/2026-12
export RESULTS=/srv/results
export RESULTS_BRANCH=<as worked out>
export SETS_BRANCH=<as worked out>
export BENCH_LANGUAGE=<LANGUAGE>
export RAIL_REPO=<the folder the session started in>
if [ -f /srv/rail-bench/toolchain.env ]; then . /srv/rail-bench/toolchain.env; fi
export PATH=/srv/claude-code/node_modules/.bin:$PATH
export DISABLE_AUTOUPDATER=1
if [ -f /srv/rail-bench/bench-config.toml ]; then export BENCH_CONFIG=/srv/rail-bench/bench-config.toml; fi
```

Write the whole file, every time this step runs: the last three lines matter to steps 5 and 7 (the pinned Claude Code
and the bench config), and the file must load cleanly before they exist.

## Step 3. Results

Results go to the private repository `timur-makarov/rail-bench-results`, branch `RESULTS_BRANCH`, folder `hardness/`,
next to the admission's `admission/`. Do this step in one Bash call and name the folder in every git command
(`git -C "$RESULTS"`): a `cd` does not carry to the next call, and a git command run in the session's own checkout
by mistake would move its branch. If `$RESULTS` is a clone on that branch already, `git -C "$RESULTS" pull --ff-only
origin "$RESULTS_BRANCH"`. Otherwise:

```
mkdir -p "$RESULTS"; [ -d "$RESULTS/.git" ] || git -C "$RESULTS" init -q
probe() { GIT_TERMINAL_PROMPT=0 timeout 60 git ls-remote "$1" >/dev/null 2>&1; }
```

`origin` (`git -C "$RESULTS" remote add origin <url>` or `remote set-url`): the first URL `probe` accepts,
(a) `https://github.com/timur-makarov/rail-bench-results.git`, (b) the Rail origin URL (`git -C "$RAIL_REPO" remote
get-url origin`) with its last path part replaced by `rail-bench-results`. Never write a token into a URL. Then
`git -C "$RESULTS" fetch -q origin "$RESULTS_BRANCH" && git -C "$RESULTS" checkout -q -B "$RESULTS_BRANCH"
FETCH_HEAD`. If neither URL answers, or the branch has no `admission/` folder there, try the fallback the admission
may have used: `origin` = the Rail origin URL, branch `bench-results-<RESULTS_BRANCH>`; if that has `admission/`, set
`RESULTS_BRANCH` to it in `session.env` and say so in the final message. If no branch holds `admission/`, stop: the
admission's results are not to be found.

A new machine (`/srv/rail-bench/runs` empty) whose results branch already has `hardness/runs/`: copy the kept runs
back before step 10, so finished runs are not run again (a run with a `result.toml` is skipped), and join any file
`keep.py` cut into pieces:

```
mkdir -p $BENCH_STORE/runs && cp -r $RESULTS/hardness/runs/. $BENCH_STORE/runs/
find $BENCH_STORE/runs -name '*.part000' | while read -r f; do b=${f%.part000}; cat "$b".part[0-9][0-9][0-9] > "$b" && rm -f "$b".part[0-9][0-9][0-9]; done
```

`PROJECTS`: if empty, the names in `$RESULTS/admission/IN-PLAY.txt` (the first word of each line: the admission
writes `name reason`). Each project P
must have `$RESULTS/admission/P/*.json` and `$SET/P.toml`.

Keeping: `python3 $SRC/bench/cloud/keep.py --repo $RESULTS --branch $RESULTS_BRANCH --dest <folder> <paths...>`;
each path lands at `<folder>/<its last name>` (`--dest hardness $BENCH_STORE/runs` lands at `hardness/runs/`).
Build folders and run copies are left out; big files are cut into pieces under 90 MB.

## Step 4. The toolchain

`bash $SET/notes/toolchain-$BENCH_LANGUAGE.sh` as root (the admission wrote it; it is safe to run again). If it is
missing, stop: the admission did not finish. Then `session.env` must load cleanly: `. /srv/rail-bench/session.env &&
echo ok`.

## Step 5. Claude Code for the children

Every child must run the same Claude Code version, never an auto-updated one.

```
V=<CC_VERSION, or if empty: npm view @anthropic-ai/claude-code dist-tags.stable>
[ -x /srv/claude-code/node_modules/.bin/claude ] && /srv/claude-code/node_modules/.bin/claude --version | grep -q "^$V " \
  || npm i --prefix /srv/claude-code "@anthropic-ai/claude-code@$V"
```

`session.env` (step 2) already puts `/srv/claude-code/node_modules/.bin` first on PATH and sets
`DISABLE_AUTOUPDATER=1`. Check: `command -v claude` is `/srv/claude-code/node_modules/.bin/claude` and `claude --version` starts with V. Write
V into `$BENCH_STORE/session/claude-version` and into the progress file.

## Step 6. Session facts

Write `$BENCH_STORE/session/facts-hardness.md` and keep it (`--dest . $BENCH_STORE/session`): the date (UTC),
`uname -a`, `nproc`, `free -g`, `df -h /srv`, `df -i /srv`; `git -C $SRC rev-parse HEAD` (the Rail and bench commit
the runs use) and `git -C $SRC rev-parse origin/bench-sets`; the children's `claude --version`; the toolchain's
versions (as the admission's facts file lists them); PROJECTS.

## Step 7. Sign-in and the bench config

```
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/signin_probe.py --write-config $BENCH_STORE/bench-config.toml
```

It finds which variables a scrubbed child with a fresh HOME needs to sign in, printing names only, and writes a copy
of the bench config whose `pass_env` is that set. Exit 1: stop (sign-in). Then lock the network and pass the
auto-updater switch:

```
python3 - <<'EOF'
import re
p = "/srv/rail-bench/bench-config.toml"
t = open(p).read()
t, a = re.subn(r'^network_lock = "[a-z]*"', 'network_lock = "required"', t, count=1, flags=re.M)
t, b = re.subn(r'^pass_env = \[', 'pass_env = ["DISABLE_AUTOUPDATER", ', t, count=1, flags=re.M)
assert a == 1 and b == 1, (a, b)
open(p, "w").write(t)
EOF
. /srv/rail-bench/session.env && python3 -c 'import sys; sys.path.insert(0, "/srv/bench-src"); from bench.common import settings; c = settings(); print(c["network_lock"], c["pass_env"])'
```

The last line prints `required` and the variable names (no values); `session.env` now sets `BENCH_CONFIG`, since the
file exists. Keep the config file in the results
(`--dest hardness`; it holds names, no secrets; check with `grep -v '^#' $BENCH_STORE/bench-config.toml` before).

## Step 8. The sealed copies

The store may have lost them (a new machine) or the admission may have parked them for disk. For each project P,
rebuild what is missing, as a job (it runs setup with the network and can take long):

```
printf 'restore-%s\tpython3 %s/bench/cloud/restore_store.py %s/admission/%s %s/%s.toml\n' P $SRC $RESULTS P $SET P \
  > $BENCH_STORE/jobs/restore-P.txt
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/restore-P $BENCH_STORE/jobs/restore-P.txt -j 1
python3 $SRC/bench/cloud/jobs.py wait $BENCH_STORE/jobs/restore-P --minutes 110
```

It prints `there`, `restored` or `could not build` per admitted situation. A situation that could not be built is
left out of this step (record it). For Rust, restore one project, run its hardness (steps 10-11), then the next, if
disk is short.

## Step 9. Checks before the runs

For each project P (a few minutes each, foreground):

```
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/lock_check.py --project $SET/P.toml
```

It starts one locked Haiku child the way the bench does and asks it to run five commands. Required: `answered: yes`,
`web blocked: yes`, `forge token absent: yes`. Expected today and recorded as findings: `store listable: yes`,
`hidden file readable: yes` (the bench does not hide its folders from a child). The cache lines must show
`BENCH_CACHE=/srv/rail-bench/cache/P` and the project's own variables (Go: `GOMODCACHE` and `GOCACHE` under it and
`go env` agreeing; Rust: `CARGO_HOME` and `RUSTUP_HOME` under `/srv/rail-bench/cache/rust`; tailscale: a `tsgo` folder
under the HOME's `.cache`, which only `go-env.sh` through `BASH_ENV` makes: if it is missing, write that down; it
means `BASH_ENV` is not read by the child's shell). Keep the output (`$BENCH_STORE/hardness/lock-P.txt`).

Then the arm itself, end to end on the bench's fixture:

```
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/bench check-arm plain-haiku
```

It must end with `check-arm plain-haiku: pass`. If not: read the run's streams (`$BENCH_STORE/runs/check.*`); a
sign-in failure is a stop.

## Step 10. The runs

For each project P, a job list in rounds (run 1 of every admitted situation in a seeded order, then run 2, then run
3; each job prunes the working copies of graded runs after it):

```
python3 $SRC/bench/cloud/joblist.py runs $SET/P.toml --arm plain-haiku --runs 3 --admitted-from $RESULTS/admission/P \
  > $BENCH_STORE/jobs/hard-P.txt
```

Leave out, with `grep -v`, any situation step 8 could not build. Start one runner per project:

```
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/hard-P $BENCH_STORE/jobs/hard-P.txt -j 1 \
  --stop-after-failures 3 --min-free-gb 3
```

Concurrency: python, typescript and go: the two projects' runners side by side, each `-j 1` (two runs at a time).
rust: one project at a time, `-j 1` (a run and its grade build several GB of `target/` and use every processor).
caddy: never more than one caddy job at a time (`-j 1`): its tests bind fixed ports.

A job exits 1 when its run ended "to run again" (rate limit, overload, sign-in) and also on an uncaught Python error
(read the log to tell which), 2 on a bench error; three in a row
stop the runner (`STATE/stopped`). A run that ended wrong, or with no change, exits 0: that is a result.

## Step 11. Waiting, and between waits

Alternate `jobs.py wait $BENCH_STORE/jobs/hard-<P> --minutes 55` over the running state folders. After each wait:

- `python3 $SRC/bench/cloud/usage_check.py --hours 3`: exit 3 is a stop (rule 9). Write its first line to the progress
  file every hour.
- `df -h /srv; df -i /srv`. Under 5 GB free: `python3 $SRC/bench/cloud/prune_runs.py`; for Go, a project's
  `$BENCH_STORE/cache/P/gocache` over 6 GB may be cleaned between its runs (`BENCH_CACHE=$BENCH_STORE/cache/P; .
  $BENCH_CACHE/go-env.sh; go clean -cache`) only while its runner is stopped.
- At least every two hours: `keep.py --dest hardness $BENCH_STORE/runs` and `keep.py --dest hardness $BENCH_STORE/jobs`.
- A runner that stopped itself (exit 5): read `STATE/stopped` and the last three logs in `STATE/logs/`. Rate limit or
  overload: run `usage_check.py`; if it does not say stop, wait 30 minutes (one foreground `python3 -c 'import time;
  time.sleep(1800)'` with timeout 2000000), `rm -f STATE/STOP STATE/stopped` and start again. Sign-in: stop. A bench
  error (exit 2): read it; the same error three times is a stop.

When a project's runner has finished (exit 0) and some jobs failed (exit 1, "to run again"), start it once more with
`--retry-failed`, if usage allows. A run whose result is tainted (the taint search found the fix in its streams)
exits 0 and is not scored; to run it again, move its folder aside (`mv RUN RUN.tainted-1`) and start that one job
again in a new state folder.

## Step 12. Drop the easy ones, choose fifteen

When every runner has finished, from `/srv/bench-src` (choose.py records the project files' paths relative to it):

```
cd $SRC && python3 bench/cloud/choose.py bench/sets/2026-12/<P1>.toml bench/sets/2026-12/<P2>.toml \
  > $BENCH_STORE/hardness/CHOOSE.md
```

It reads each admitted situation's `admission.toml` from the store (step 8 put them back) and every plain-haiku
result: a situation is easy when all three scored runs were merged and right ("solved alone"), and not settled with
fewer than three scored runs (runs to run again and tainted runs do not count). Of the rest, fifteen are drawn per
project, stratified by kind, seed 20261127; the last three are held out. A project with fewer than fifteen left is
reported and not chosen.

- A not-settled situation: if usage allows, run its missing runs once more (`--retry-failed`), then choose again.
- A project with fewer than fifteen left: if a reserve of this language has admission records with at least fifteen
  admitted in `$RESULTS/admission/<reserve>/` and is not in play, run steps 8 to 11 for that reserve and choose with
  it in place of the short project. If no reserve is admitted, choose what you can and say in the final message that
  the short project needs a reserve's admission (`ADMIT-<language>.md` with PROJECTS set to the reserve).

Then write the choice: first make sure no earlier `--apply` is half done (`git -C $SRC status --short
bench/sets/2026-12` shows nothing; if it shows changes that are not committed, `git -C $SRC checkout --
bench/sets/2026-12/` and `rm -f $SRC/bench/sets/2026-12/CHOSEN.toml` unless CHOSEN.toml is committed), then the same
command with `--apply` (it sets `half = "held"` in the project files and writes
`bench/sets/2026-12/CHOSEN.toml`). Check `cd $SRC/tests && python3 -m unittest test_bench_sets`, then commit and push:

```
git -C $SRC add bench/sets/2026-12
git -C $SRC commit -m "Choose fifteen situations per project of <language> after the hardness runs" \
  -m "choose.py, seed 20261127; easy (solved 3 of 3 by plain Haiku 5.5) dropped first"
git -C $SRC push origin "HEAD:refs/heads/$SETS_BRANCH"
```

Keep `CHOOSE.md`, `CHOSEN.toml` and the project files (`--dest hardness`).

## Step 13. Cost and odd runs

```
python3 - <<'EOF' > /srv/rail-bench/hardness/COST.md
import glob, os, tomllib, collections
tot = collections.defaultdict(lambda: collections.Counter())
for p in glob.glob("/srv/rail-bench/runs/*.plain-haiku.*/result.toml"):
    r = tomllib.load(open(p, "rb"))
    t = tot[r.get("project", "?")]
    t["runs"] += 1
    t["again"] += bool(r.get("again"))
    t["usd_cli"] += float(r.get("cost_usd") or 0)
    t["minutes"] += float(r.get("minutes") or 0)
    for role, u in (r.get("usage") or {}).items():
        for k in ("input", "output", "cache_write", "cache_read", "requests"):
            t[k] += int(u.get(k) or 0)
print("| Project | Runs | Again | USD (CLI) | Minutes | Requests | Input | Output | Cache write | Cache read |")
print("|---|---|---|---|---|---|---|---|---|---|")
for k, t in sorted(tot.items()):
    print(f"| {k} | {t['runs']} | {t['again']} | {t['usd_cli']:.2f} | {t['minutes']:.0f} | {t['requests']} | "
          f"{t['input']} | {t['output']} | {t['cache_write']} | {t['cache_read']} |")
EOF
python3 $SRC/bench/cloud/odd_runs.py --limit 5 --arms plain-haiku > $BENCH_STORE/hardness/ODD.md
grep -hoE '"claude_code_version": *"[^"]*"' $BENCH_STORE/runs/*.plain-haiku.*/streams/*.jsonl | sort | uniq -c
python3 $SRC/bench/cloud/usage_check.py --hours 48 > $BENCH_STORE/hardness/USAGE.txt
```

The `claude_code_version` line counts the versions the children reported (if the streams carry none, say so). Keep
`$BENCH_STORE/hardness`, `$BENCH_STORE/runs`, `$BENCH_STORE/jobs` and `$BENCH_STORE/session` (with
PROGRESS-HARDNESS.md).

## Step 14. The final message

End with exactly this shape (Markdown):

```
HARDNESS <language>: done            (or: stopped: <reason>)
Results: <repository URL without credentials> branch <branch> at <commit>   (fallback used: yes/no)
Settings: Rail branch <SETS_BRANCH> at <commit>; CHOSEN.toml written: yes/no
Claude Code for children: <V> (versions in the streams: <counts, or "none recorded">); Rail and bench commit <sha>
Sign-in: pass_env names <names>; network_lock required
Lock check: <project>: answered <y/n>, web blocked <y/n>, store listable <y/n>, hidden readable <y/n>, forge token absent <y/n>, cache paths <ok / what differed>
check-arm plain-haiku: pass/fail

| Project | Admitted | Run | Runs graded | To run again | Tainted | Easy (3/3) | Not settled | Left | Chosen |
|---|---|---|---|---|---|---|---|---|---|

Chosen (seed 20261127):
- <project>: work <12 ids>; held <3 ids>

Cost: <the COST.md table>; usage at the end: <usage_check first line>
Odd runs (up to five): <run id> — <why> — <stream path>
Faults found in the bench or its scripts (file, what, how it showed): ...
Not done, and why: ...
```

Nothing after that message.
