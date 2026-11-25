# Pilot of the bench (PLAN T9, cut to two arms)

```
LANGUAGE        =            # fill in: python, typescript, rust or go
PROJECTS        =            # empty: this language's projects in bench/sets/2026-12/CHOSEN.toml on SETS_BRANCH
CC_VERSION      =            # the same version the hardness session pinned (its final message); empty: read it from
                             # session/claude-version on the results branch
RESULTS_BRANCH  =            # empty: LANGUAGE; give the same value the admission and hardness sessions were given
SETS_BRANCH     =            # empty: bench-sets-<RESULTS_BRANCH as given here>
```

**Left out of this pilot, because they are not built yet:** the planted fault for the reviewer (PLAN 4c), the invited
vulnerability (PLAN 4b), and the chain of three situations (PLAN 4d). Nothing here tests them; the final message
says so again.

You are a Claude Code session on a cloud machine, started on the Rail repository. The admission and hardness
sessions for this language have admitted situations, run the hardness filter and chosen fifteen per project. Your
job: one situation per project, both arms of the first run, three runs each; and the checks the pilot must show:
a run killed part-way and resumed, a restart from a saved stage giving the same tree, the network lock as root on
Linux, the proxy's token counts against the CLI's own, `bench report`, and the ten failed or odd runs to read by hand.

The arms (`bench/arms/`): `rail-ladder` is Rail at this commit, nobody to ask, worker ladder Sonnet 5.5 medium then
Opus 5.5 medium (from the project files), contract and review Opus 5.5 high, consult Fable 5.2 high; `plain-opus`
is plain Claude Code, Opus 5.5 medium. The pilot's numbers are not results: six runs per arm show whether the bench
works, nothing about the arms.

You work alone and nobody watches; the person reads your final message. Every step can be started again: if your
context was compacted, the machine paused, or a person sent "go on", read `/srv/rail-bench/session/PROGRESS-PILOT.md`
and continue at the first step not marked done. If LANGUAGE is empty, stop at once and say so.

## Rules

1. **Never end your turn while work runs.** Runs go as background jobs with `bench/cloud/jobs.py`; you wait with a
   foreground Bash call, `jobs.py wait STATE --minutes 55` (alternate when two runners run), with the Bash tool's
   `timeout` set to 7200000. The machine pauses a few minutes after your turn ends and kills every process (files
   stay), so your turn ends only with the final message. If `jobs.py wait` exits 4 (the runner is gone: the machine
   paused), start it again with the same `jobs.py start` command: a Rail run goes on from its last saved stage, a
   plain run starts again.
2. **Start every Bash call with `. /srv/rail-bench/session.env &&`** once step 2 has written it.
3. **Progress.** Append a line to `/srv/rail-bench/session/PROGRESS-PILOT.md` when a step starts and ends
   (`PILOT step N start`, `PILOT step N done: <one line>`), and keep there what you need after a compaction (the
   situations picked, run ids, state folders, what was checked). Other prompts keep their own progress files.
4. **Credentials.** Never print, log, store or commit a credential: no token, key, password, cookie, or the value of a
   variable that holds one; no `env`, `printenv` or `set` without a filter that drops values. Never put a token in a
   git remote, a URL, a file or the bench config.
5. **Children.** Start model children only through the bench (`bench run`, `bench check-arm`) and its scripts
   (`signin_probe.py`, `lock_check.py`): they give each child a scrubbed environment, a fresh HOME and TMPDIR, a fixed
   tool list and a locked network. Never run `claude -p` yourself, and never add a GitHub, cloud or messaging
   variable to `pass_env`. Every job runs without the session's forge, cloud and messaging credentials (`jobs.py`
   drops them: the projects' tests and the graded code run there); run the bench and its scripts in the foreground
   the same way: `python3 $SRC/bench/cloud/jobs.py exec -- <command>`.
6. **What you may change.** The bench config at `/srv/rail-bench/bench-config.toml`. Nothing in the repository; a
   fault of the bench is reported, not fixed. If a script under `bench/cloud/` stops a step, you may make the smallest
   fix, commit it on its own on `SETS_BRANCH`, and list it in the final message.
7. **Git.** No `git stash`, no force push, no merge, no rebase of a branch others push to. Push only the results
   branch (and `SETS_BRANCH` for a rule-6 fix). Never change the branch of the folder the session started in.
8. **Keep results often:** at least every two hours, and at the end of every step.
9. **Stop rules.** Stop starting runs (`touch STATE/STOP` in every state folder), wait for the running ones to end,
   keep everything, and write the final message with `stopped:` and the reason when:
   - the sign-in probe fails, a `check-arm` fails, or runs end "to run again" because of sign-in;
   - `usage_check.py` exits 3 (the account's usage limit is near or hit);
   - free disk of `/srv` stays under 3 GB after `prune_runs.py`, or inode use is over 95%;
   - the same step fails three times in a row;
   - the lock check shows the web reachable from a locked child.

## Step 1. The checkout

```
mkdir -p /srv/rail-bench/session /srv/rail-bench/jobs /srv/rail-bench/pilot
RAIL_REPO=$(git rev-parse --show-toplevel)       # in the folder the session started in
git -C "$RAIL_REPO" fetch -q origin "+refs/heads/$SETS_BRANCH:refs/remotes/origin/$SETS_BRANCH" \
  || { echo "no $SETS_BRANCH on origin"; exit 1; }
if [ ! -e /srv/bench-src/.git ]; then
  git -C "$RAIL_REPO" worktree add -B "$SETS_BRANCH" /srv/bench-src "origin/$SETS_BRANCH"
fi
```

`RESULTS_BRANCH` defaults to LANGUAGE, `SETS_BRANCH` to `bench-sets-<RESULTS_BRANCH as given>`. An existing
`/srv/bench-src` must be on `SETS_BRANCH` and not behind `origin/$SETS_BRANCH`; if it is behind with no commits of its
own, `git -C /srv/bench-src merge --ff-only origin/$SETS_BRANCH`; otherwise stop and say so.
`$SRC/bench/sets/2026-12/CHOSEN.toml` must exist and name this language's projects (the hardness session wrote it);
if not, stop: the hardness step has not finished. `PROJECTS`, if empty: the projects of this language in CHOSEN.toml.

## Step 2. The session's environment file

Write or check `/srv/rail-bench/session.env` (no secrets, ever):

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

Write the whole file each time this step runs; it must load cleanly before the pinned Claude Code and the bench
config exist (step 4 makes them).

## Step 3. Results

The private repository `timur-makarov/rail-bench-results`, branch `RESULTS_BRANCH`, folder `pilot/`. Do this step in
one Bash call and name the folder in every git command (`git -C "$RESULTS"`): a `cd` does not carry to the next
call, and a git command run in the session's own checkout by mistake would move its branch. If `$RESULTS` is a clone
on that branch, `git -C "$RESULTS" pull --ff-only origin "$RESULTS_BRANCH"`. Otherwise: `mkdir -p "$RESULTS"; [ -d
"$RESULTS/.git" ] || git -C "$RESULTS" init -q`; `origin` the first URL that answers `GIT_TERMINAL_PROMPT=0 timeout
60 git ls-remote <url>`, (a) `https://github.com/timur-makarov/rail-bench-results.git`, (b) the Rail origin URL with
its last path part replaced by `rail-bench-results`; then `git -C "$RESULTS" fetch -q origin "$RESULTS_BRANCH" && git
-C "$RESULTS" checkout -q -B "$RESULTS_BRANCH" FETCH_HEAD`. If neither answers or the branch has no `admission/`, try
the fallback: the Rail origin URL, branch `bench-results-<RESULTS_BRANCH>`; if it has `admission/`, use it, set
`RESULTS_BRANCH` in `session.env`, and say so. Never write a token into a URL.

Keeping: `python3 $SRC/bench/cloud/keep.py --repo $RESULTS --branch $RESULTS_BRANCH --dest <folder> <paths...>`;
each path lands at `<folder>/<its last name>`.

## Step 4. Toolchain, Claude Code, sign-in

1. `bash $SET/notes/toolchain-$BENCH_LANGUAGE.sh` as root (safe to run again).
2. Claude Code for the children: V = CC_VERSION, or if empty the first line of `$RESULTS/session/claude-version`
   (the hardness session's), or if that is missing too, `npm view @anthropic-ai/claude-code dist-tags.stable` (say so
   in the final message: the pilot then may not match the hardness runs).
   ```
   [ -x /srv/claude-code/node_modules/.bin/claude ] && /srv/claude-code/node_modules/.bin/claude --version | grep -q "^$V " \
     || npm i --prefix /srv/claude-code "@anthropic-ai/claude-code@$V"
   ```
   Check that `command -v claude` is `/srv/claude-code/node_modules/.bin/claude` and that `claude --version` starts
   with V. Write V to `$BENCH_STORE/session/claude-version`.
3. Sign-in: `python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/signin_probe.py --write-config
   $BENCH_STORE/bench-config.toml` (names only; exit 1 is a stop), then set `network_lock = "required"` and put `"DISABLE_AUTOUPDATER"` first in `pass_env`:
   ```
   python3 - <<'EOF'
   import re
   p = "/srv/rail-bench/bench-config.toml"
   t = open(p).read()
   t, a = re.subn(r'^network_lock = "[a-z]*"', 'network_lock = "required"', t, count=1, flags=re.M)
   if '"DISABLE_AUTOUPDATER"' not in t:
       t, b = re.subn(r'^pass_env = \[', 'pass_env = ["DISABLE_AUTOUPDATER", ', t, count=1, flags=re.M)
   assert a == 1
   open(p, "w").write(t)
   EOF
   . /srv/rail-bench/session.env && python3 -c 'import sys; sys.path.insert(0, "/srv/bench-src"); from bench.common import settings; c = settings(); print(c["network_lock"], c["pass_env"])'
   ```
   It must print `required` and names only (`session.env` sets `BENCH_CONFIG` now that the file exists).
4. Session facts: write `$BENCH_STORE/session/facts-pilot.md` (date UTC, `uname -a`, `nproc`, `free -g`, `df -h /srv`,
   `df -i /srv`, `git -C $SRC rev-parse HEAD`, `git -C $SRC rev-parse origin/bench-sets`, the children's
   `claude --version`, the toolchain versions) and keep it (`--dest . $BENCH_STORE/session`).

## Step 5. The situations

One per project. Prefer a situation outside the fifteen, so the pilot does not touch the set: admitted, run by the
hardness step, not easy, not unsettled, and neither work nor held. Pick it with:

```
python3 - P <<'EOF'
import glob, json, os, random, sys, tomllib
p = sys.argv[1]
c = tomllib.load(open(f"/srv/bench-src/bench/sets/2026-12/CHOSEN.toml", "rb"))[p]
admitted = sorted(os.path.basename(j)[:-5] for j in glob.glob(f"/srv/results/admission/{p}/*.json")
                  if json.load(open(j)).get("admitted"))
out = [s for s in admitted if s not in set(c["easy"]) | set(c["not_settled"]) | set(c["work"]) | set(c["held"])]
random.Random(20261129).shuffle(out)
print(out[0] if out else c["work"][0], "(outside the fifteen)" if out else "(no situation outside the fifteen: the first work one)")
EOF
```

(`/srv/results` is `$RESULTS`.) Write the picks in the progress file. Then put back their sealed copies, if missing:
`python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/restore_store.py $RESULTS/admission/P $SET/P.toml
--id <pick>` (with the network; for a
setup that takes long, run it as a one-line job list through `jobs.py` and wait).

## Step 6. The network lock, as root

For each project P, foreground (a few minutes):

```
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/lock_check.py --project $SET/P.toml \
  | tee $BENCH_STORE/pilot/lock-P.txt
```

It makes a locked child exactly as the bench does (`unshare -n`, a relay to the cost proxy, the scrubbed environment,
a fresh HOME) and has it run five commands. Required: `answered: yes` (the locked child signed in and answered
through the proxy), `web blocked: yes` (`curl https://example.com` from its Bash failed), `forge token absent: yes`.
Recorded as findings, expected `yes` today: `store listable` and `hidden file readable` (the bench's own folders,
with the hidden tests, are readable by a child; the taint search only detects use). The proxy line must show
requests with status 200 and tokens. Also check `id -u` is 0 and `uname -s` is Linux, and write both in the file.

## Step 7. The arms on the fixture

```
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/bench check-arm rail-ladder
python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/bench check-arm plain-opus
```

Each must end with `check-arm <arm>: pass` (one trivial situation of the bench's fixture, end to end: merged, right,
not tainted). The fixture project has no ladder of its own, so `check-arm rail-ladder` runs Rail's seed ladder with
the arm's contract, review and consult models; the two-rung ladder is first exercised in step 8. Run each in the
foreground with timeout 7200000; if one takes longer, it is still a pass or fail when it
returns. A fail: read `$BENCH_STORE/runs/check.<arm>-*/` (log.jsonl, streams, result.toml); sign-in is a stop.

## Step 8. A run killed part-way, then resumed

Take the first project's pick, X1. Start its first Rail run alone, in the background, and note its process id:

```
cd $BENCH_STORE && setsid nohup python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/bench run $SET/<P1>.toml --id <X1> --arm rail-ladder --runs 1 \
  > $BENCH_STORE/pilot/kill-run.log 2>&1 < /dev/null & echo $! > $BENCH_STORE/pilot/kill-run.pid
```

The run's folder is `$BENCH_STORE/runs/<P1>.<X1>.rail-ladder.1`. Wait (foreground, at most 90 minutes) until its
`stages/stages.jsonl` has two lines (intake, contract) and its `streams/` has a worker stream, then two more minutes,
so the kill lands in the middle of the first worker run (one foreground call, Bash `timeout` 7200000):

```
python3 - "$BENCH_STORE/runs/<P1>.<X1>.rail-ladder.1" <<'EOF'
import glob, os, sys, time
run = sys.argv[1]
for _ in range(540):
    stages = os.path.join(run, "stages", "stages.jsonl")
    n = sum(1 for _ in open(stages)) if os.path.exists(stages) else 0
    worker = glob.glob(os.path.join(run, "streams", "*worker*"))
    if n >= 2 and worker:
        time.sleep(120)
        print("stages", n, "worker streams", len(worker)); break
    time.sleep(10)
else:
    print("no worker run within 90 minutes")
EOF
bash $SRC/bench/cloud/killtree.sh "$(cat $BENCH_STORE/pilot/kill-run.pid)"
pgrep -af 'bench/bench run|netlock.py|claude -p' | grep -v pgrep || echo "nothing left"
```

(If the run ended before the kill, note it and do this step with the second project's pick.) Then go on with the
same run: `bench run $SET/<P1>.toml --id <X1> --arm rail-ladder --runs 1`, as the first job of step 9 does. Check
afterwards that its `log.jsonl` has a line with `"kind": "resume"` naming the last stage saved before the kill, and
that it ended with a result. Write what you saw (stages at the kill, the resume line, the end) to
`$BENCH_STORE/pilot/KILL.md`.

## Step 9. The pilot runs

For each project P and its pick X, three runs of each arm, the arms interleaved:

```
python3 $SRC/bench/cloud/joblist.py runs $SET/P.toml --arm rail-ladder --runs 3 --id X > $BENCH_STORE/jobs/rl-P.txt
python3 $SRC/bench/cloud/joblist.py runs $SET/P.toml --arm plain-opus --runs 3 --id X > $BENCH_STORE/jobs/po-P.txt
paste -d '\n' $BENCH_STORE/jobs/rl-P.txt $BENCH_STORE/jobs/po-P.txt | grep -v '^$' > $BENCH_STORE/jobs/pilot-P.txt
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/pilot-P $BENCH_STORE/jobs/pilot-P.txt -j 1 \
  --stop-after-failures 3 --min-free-gb 3
```

For the first project, the first job goes on with the run step 8 killed. Concurrency: python, typescript and go: the
two projects' runners side by side, each `-j 1`; rust: one project after the other. A Rail run may take up to two
hours (the bench's `run_minutes`).

Waiting and between waits, as in the hardness step: alternate `jobs.py wait ... --minutes 55`; after each,
`usage_check.py --hours 3` (exit 3: stop), `df -h /srv; df -i /srv` (under 5 GB: `prune_runs.py`, then delete the stage pieces, `stages/*.tar.gz*`, of Rail runs that have ended and
that step 10 will not use), and every two
hours keep: `keep.py --no-stages --dest pilot/runs $BENCH_STORE/runs/*.rail-ladder.* $BENCH_STORE/runs/*.plain-opus.*
$BENCH_STORE/runs/check.*` (`--no-stages`: a saved stage is a whole copy, hundreds of MB; only `stages.jsonl` is
kept) and `keep.py --dest pilot $BENCH_STORE/jobs`. A runner that stopped itself: read
`STATE/stopped` and the last logs; rate limit or overload: `usage_check.py`, then wait 30 minutes (a foreground
command that does nothing for 1800 s) and start again with `--retry-failed`; sign-in: stop. Jobs that ended "to run
again" get one `--retry-failed` round when the runner finishes.

## Step 10. A restart from a saved stage

Take a Rail run of step 9 that ended with at least three saved stages (`stages/stages.jsonl`), preferably one with a
`review-1` stage. First, every saved stage must restore to the tree it saved:

```
for s in $(python3 -c 'import json,sys; [print(json.loads(l)["name"]) for l in open(sys.argv[1])]' $BENCH_STORE/runs/<RUN>/stages/stages.jsonl); do
  python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/cloud/restore_check.py <RUN> "$s"
done 2>&1 | tee $BENCH_STORE/pilot/RESTORE.md
```

Each line must say `SAME` (it compares refs, HEAD, the worktrees, the files of each checkout and `.git/rail/`).
Each check copies and restores a whole run and runs Rail's setup in each worktree: for a project with a long setup,
run this loop as a one-line job through `jobs.py` and wait. Then restart the run from the stage before `review-1`
(or, with no review stage, from its last stage) on the same arm, as a job:

```
printf 'restart\tpython3 %s/bench/bench run --from <RUN> --stage <review-1 or the last stage> --arm rail-ladder\n' $SRC \
  > $BENCH_STORE/jobs/restart.txt
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/restart $BENCH_STORE/jobs/restart.txt -j 1
```

Its run is `<RUN>.from-<stage>.rail-ladder.1`; its `log.jsonl` must have a `"kind": "resume"` line naming the stage
before, and it must end with a result. Write both to `RESTORE.md`.

## Step 11. Reading the runs

```
python3 $SRC/bench/cloud/proxy_vs_cli.py $BENCH_STORE/runs/*.rail-ladder.* $BENCH_STORE/runs/*.plain-opus.* \
  > $BENCH_STORE/pilot/PROXY.md
grep -hoE '"claude_code_version": *"[^"]*"' $BENCH_STORE/runs/*.rail-ladder.*/streams/*.jsonl \
  $BENCH_STORE/runs/*.plain-opus.*/streams/*.jsonl | sort | uniq -c > $BENCH_STORE/pilot/VERSIONS.txt
for r in $BENCH_STORE/runs/*.rail-ladder.* $BENCH_STORE/runs/*.plain-opus.*; do
  printf '%s home:%s locked:%s\n' "$(basename $r)" "$( [ -d $r/home/.claude ] && echo own || echo none)" \
    "$(grep -c '^locked = true' $r/run.toml)"
done > $BENCH_STORE/pilot/HOMES.txt
python3 $SRC/bench/bench report --arms rail-ladder,plain-opus > $BENCH_STORE/pilot/REPORT.md
python3 $SRC/bench/cloud/odd_runs.py --limit 10 --arms rail-ladder,plain-opus > $BENCH_STORE/pilot/ODD.md
python3 $SRC/bench/cloud/usage_check.py --hours 48 > $BENCH_STORE/pilot/USAGE.txt
```

What each shows: PROXY.md, per run and role, the proxy's token counts against the CLI's totals (review and consult
write no stream, so only the proxy counts them; the worker's should agree). Two runs differ by construction and are
read apart: the run killed in step 8 (its proxy logs keep the killed worker's requests, whose stream the restore
dropped) and the restarted run of step 10 (it carries its source's streams but starts with empty proxy logs); VERSIONS.txt, the Claude Code versions
the children reported (one value expected; none at all means the streams do not carry it: say so); HOMES.txt, that
every run had its own HOME, used by its children, and ran locked; REPORT.md, the bench's numbers per arm (six runs
per arm: a check that the report works, not a result); ODD.md, the ten failed or odd runs with their streams. Read
the streams of each of the ten (the last 40 lines and every error line at least) and write one line per run: what
happened. Also note whether any run ended "to run again" for a rate limit (that is how the pilot shows a limit ends
a run as "to run again", never as a grade; if none did, say "not seen").

Keep `$BENCH_STORE/pilot`, the pilot runs (`--no-stages --dest pilot/runs`, as in step 9), `$BENCH_STORE/jobs` (`--dest pilot`)
and `$BENCH_STORE/session` (with PROGRESS-PILOT.md). Then move the pilot's runs out of the store's `runs/`, so no later run or report mixes
them with the main run's: `mkdir -p $BENCH_STORE/runs-pilot && mv $BENCH_STORE/runs/*.rail-ladder.*
$BENCH_STORE/runs/*.plain-opus.* $BENCH_STORE/runs/check.* $BENCH_STORE/runs-pilot/`.

## Step 12. The final message

End with exactly this shape (Markdown):

```
PILOT <language>: done            (or: stopped: <reason>)
Left out, not built: the planted fault, the invited vulnerability, the chain of three situations.
Results: <repository URL without credentials> branch <branch> at <commit>   (fallback used: yes/no)
Rail and bench commit <sha> (SETS_BRANCH <branch>); Claude Code for children <V>
Situations: <project>: <id> (<outside the fifteen / first work one>)

| Check | Result | Where |
|---|---|---|
| Sealed copies build (<language>) | ... | |
| Lock: locked child answers | yes/no | pilot/lock-<P>.txt |
| Lock: curl https://example.com fails in the child | yes/no | |
| Lock: bench folders and hidden tests readable by the child | yes/no (finding) | |
| Lock: no forge token in the child | yes/no | |
| check-arm rail-ladder (seed ladder) / plain-opus | pass/fail, pass/fail | |
| Killed part-way and resumed | stage at the kill; resume line; end | pilot/KILL.md |
| Every saved stage restores the same tree | n of n SAME | pilot/RESTORE.md |
| Restart from a saved stage | <run id>: <end> | |
| Proxy tokens against CLI totals | agree / differ (how much, which role; the killed and the restarted run apart) | pilot/PROXY.md |
| Rate limit ends a run as "to run again" | seen / not seen | |
| One Claude Code version in every run | <values> | pilot/VERSIONS.txt |
| Own HOME and TMPDIR per run, locked | n of n | pilot/HOMES.txt |
| bench report | works / fails | pilot/REPORT.md |

| Run | Arm | End | Merged | Right at the stop | Minutes | USD (CLI) | Tainted |
|---|---|---|---|---|---|---|---|

Ten failed or odd runs:
1. <run id>: <why odd>; <what the stream shows, one line>; streams: <paths>
...

Usage at the end: <usage_check first line>
Faults found in the bench or its scripts (file, what, how it showed): ...
Not done, and why: ...
```

Nothing after that message.
