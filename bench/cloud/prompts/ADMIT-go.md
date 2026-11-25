# Admission of the Go projects of set 2026-12 (no model runs)

```
LANGUAGE        = go
PROJECTS        =            # empty: the two proposed (caddy, typescript-go), and the reserves as step 7 says
RESULTS_BRANCH  =            # empty: go
SETS_BRANCH     =            # empty: bench-sets-<RESULTS_BRANCH>
```

You are a Claude Code session on a cloud machine, started on the Rail repository. Your job: install what the Go
projects need, make each project's settings work on this machine, and run the bench's admission on every candidate
situation, with no model run at all. You work alone and nobody watches; the person reads your final message. Work
through the steps in order. Every step can be started again: if your context was compacted, the machine paused, or a
person sent "go on", read `/srv/rail-bench/session/PROGRESS-ADMIT.md` and continue at the first step not marked done.

## Rules

1. **Never end your turn while work runs.** Anything longer than a few minutes runs as background jobs with
   `bench/cloud/jobs.py`; you wait with a foreground Bash call, `jobs.py wait STATE --minutes 110`, with the Bash
   tool's `timeout` set to 7200000. Between waits, do the housekeeping of step 9, then wait again. The machine pauses
   a few minutes after your turn ends and kills every process (files stay), so your turn ends only with the final
   message. If `jobs.py wait` exits 4 (the runner is gone: the machine paused), start the runner again with the same
   `jobs.py start` command; finished jobs are not run again.
2. **Start every Bash call with `. /srv/rail-bench/session.env &&`** once step 2 has written it. Shell state does not
   carry between calls.
3. **Progress.** Append one line to `/srv/rail-bench/session/PROGRESS-ADMIT.md` when a step starts and when it ends
   (`ADMIT step N start`, `ADMIT step N done: <one line>`), and a line for each project phase. Keep notes there of anything you
   will need after a compaction (state folders, which smoke round, which commands you changed).
4. **Credentials.** Never print, log, store or commit a credential: no token, key, password, cookie, or the value of a
   variable that holds one; no `env`, `printenv` or `set` without a filter that drops values. Name variables, never
   show their values. Never put a token in a git remote or URL; use the remotes and credentials the session already
   has. Every job runs without the session's forge, cloud and messaging credentials (`jobs.py` drops them), since the
   projects' own build scripts and tests run there; a bench command you run in the foreground goes through
   `python3 $SRC/bench/cloud/jobs.py exec -- <command>` for the same reason.
5. **Children.** This step runs no model. Do not run `claude` except `claude --version`.
6. **What you may change.** The project files `bench/sets/2026-12/<project>.toml` (their `[project]` build_dirs,
   `[commands]` and `[rail.config.commands]`; not the situations' fields), the notes in `bench/sets/2026-12/notes/`,
   and a new `notes/toolchain-go.sh`. Nothing else in the repository: not the engine, not `bench/*.py`. If a
   script under `bench/cloud/` fails in a way that stops a step, you may make the smallest fix, commit it on its own
   on `SETS_BRANCH` with a message saying so, and list it in the final message. A fault of the bench itself is
   reported, not fixed.
7. **Git.** No `git stash`, no force push, no merge, no rebase of a branch others push to, no history rewrite. Push
   only `SETS_BRANCH` to the Rail repository's `origin`, and the results branch (step 3). Commit on `SETS_BRANCH` only
   in `/srv/bench-src`. Never change the branch of the folder the session started in.
8. **Keep results often:** after each project's admission phase and at least every two hours (step 9). `keep.py` cuts
   files over 90 MB into pieces; never push a file over 100 MB.
9. **Stop rules.** Stop the step, keep what you have, and write the final message with `stopped:` and the reason when:
   - free disk of `/srv` stays under 3 GB after the clean-ups step 6e allows, or inode use is over 95%;
   - the same step (the same command on the same situation or project) fails three times in a row after fixes;
   - a push of results fails three times in a row on both the results repository and the fallback branch;
   - the machine lacks something that cannot be installed (say what).
   A single situation refused, or a single project whose settings cannot be made to work, is not a stop: record it
   and go on to the next.

## Step 1. The machine and the checkout

```
mkdir -p /srv/rail-bench/session /srv/rail-bench/jobs
RAIL_REPO=$(git rev-parse --show-toplevel)       # run this in the folder the session started in
```

Work out `RESULTS_BRANCH` (default `go`) and `SETS_BRANCH` (default `bench-sets-<RESULTS_BRANCH>`, from the
parameter as given, before any fallback of step 3). Make the
bench's working copy, a git worktree of the Rail repository at `/srv/bench-src`, on `SETS_BRANCH` (the explicit
refspecs matter: the session's clone may track one branch only):

```
git -C "$RAIL_REPO" fetch -q origin "+refs/heads/bench-sets:refs/remotes/origin/bench-sets"
if [ ! -e /srv/bench-src/.git ]; then
  if git -C "$RAIL_REPO" fetch -q origin "+refs/heads/$SETS_BRANCH:refs/remotes/origin/$SETS_BRANCH" 2>/dev/null; then
    git -C "$RAIL_REPO" worktree add -B "$SETS_BRANCH" /srv/bench-src "origin/$SETS_BRANCH"
  else
    git -C "$RAIL_REPO" worktree add -B "$SETS_BRANCH" /srv/bench-src origin/bench-sets
  fi
fi
git -C /srv/bench-src log -1 --format='%H %s'
```

If `bench-sets` cannot be fetched, or `/srv/bench-src/bench/cloud/jobs.py` or `/srv/bench-src/bench/sets/2026-12/`
is missing after this, stop: the sets are not pushed. If the worktree exists already (a restart), keep it
and its commits; `git -C /srv/bench-src status --short` must show nothing you did not make.

## Step 2. The session's environment file

Write `/srv/rail-bench/session.env` (no secrets in it, ever):

```
export BENCH_STORE=/srv/rail-bench
export SRC=/srv/bench-src
export SET=/srv/bench-src/bench/sets/2026-12
export RESULTS=/srv/results
export RESULTS_BRANCH=<as worked out>
export SETS_BRANCH=<as worked out>
export BENCH_LANGUAGE=go
export RAIL_REPO=<the folder the session started in>
if [ -f /srv/rail-bench/toolchain.env ]; then . /srv/rail-bench/toolchain.env; fi
```

`BENCH_STORE` must be `/srv/rail-bench`: the project files of this set name paths under it. Later steps may add lines
(never secrets).

## Step 3. Where results go

Results go to the private repository `timur-makarov/rail-bench-results`, branch `RESULTS_BRANCH`, in folders
`session/`, `admission/`, `hardness/`, `pilot/`. Do this step in one Bash call, and name the folder in every git
command (`git -C "$RESULTS"`): a `cd` does not carry to the next call, and a git command run in the session's own
checkout by mistake would move its branch.

```
mkdir -p "$RESULTS"; [ -d "$RESULTS/.git" ] || git -C "$RESULTS" init -q
probe() { GIT_TERMINAL_PROMPT=0 timeout 60 git ls-remote "$1" >/dev/null 2>&1; }
```

Try, in order, until `probe <url>` succeeds: (a) `https://github.com/timur-makarov/rail-bench-results.git`;
(b) the Rail repository's own origin URL (`git -C "$RAIL_REPO" remote get-url origin`) with its last path part
replaced by `rail-bench-results` (the session's git proxy may serve other repositories of the same owner that way).
Make that URL the `origin` of `$RESULTS` (`git -C "$RESULTS" remote add origin <url>`, or `remote set-url` when it
exists; never write a token into it). Then put the clone on the branch:

```
if GIT_TERMINAL_PROMPT=0 git -C "$RESULTS" ls-remote --exit-code origin "refs/heads/$RESULTS_BRANCH" >/dev/null; then
  git -C "$RESULTS" fetch -q origin "$RESULTS_BRANCH" && git -C "$RESULTS" checkout -q -B "$RESULTS_BRANCH" FETCH_HEAD
else
  git -C "$RESULTS" symbolic-ref HEAD "refs/heads/$RESULTS_BRANCH"
fi
```

The first keep of step 4 is the push probe. **If neither URL answers or that push is refused**, fall back: a fresh
folder at `$RESULTS` (`git -C "$RESULTS" init -q`) whose `origin` is the Rail repository's origin URL, on the orphan
branch `bench-results-<RESULTS_BRANCH>` (fetched first if it exists, as above); set `RESULTS_BRANCH` to that name in
`session.env`; say so at the top of the final message. Write the choice in the progress file.

Keeping, from now on:

```
python3 $SRC/bench/cloud/keep.py --repo $RESULTS --branch $RESULTS_BRANCH --dest <folder> <paths...>
```

Each path lands at `<folder>/<its last name>`: `--dest admission $BENCH_STORE/admission/P` lands at `admission/P/`,
`--dest . $BENCH_STORE/session` at `session/`. It skips build folders and copies, cuts big files into pieces,
commits and pushes, with retries; exit 1 when the push failed.

A new machine (`/srv/rail-bench` empty) with results already on the branch: do steps 1 to 5 again (the toolchain
is gone with the old machine; `$RESULTS/session/PROGRESS-ADMIT.md` tells you which project phases were finished, and the
settings branch has their commands), and copy the admission records back before step 6, so finished situations are
not admitted again: for each project P with `$RESULTS/admission/P/`, `mkdir -p $BENCH_STORE/admission && cp -r
$RESULTS/admission/P $BENCH_STORE/admission/`. Situations with a JSON are then left out of the full round (6e); the sealed copies of the
admitted ones are rebuilt by the hardness step (`restore_store.py`).

## Step 4. Session facts

Write `$BENCH_STORE/session/facts-admit.md` and keep it (`--dest . $BENCH_STORE/session`): the date (UTC),
`uname -a`, the Ubuntu release, `nproc`, `free -g`, `df -h /srv`, `df -i /srv`; `git -C $SRC rev-parse HEAD`,
`git -C $SRC rev-parse origin/bench-sets`, the branch names; `claude --version` (the session's own; this step runs no
child); the versions of `go` (`go version`), `gcc`, `git`, `unshare`, `node`, `npm`; whether `unshare -n true && echo yes` works as root (the offline checks need it).

## Step 5. The toolchain

Read `$SET/notes/go-common.md` first. Go 1.24.7 was on the machine (CLOUD-CHECK-RESULT.md); each project's env
sets `GOTOOLCHAIN=auto`, so setup downloads the toolchain its `go.mod` names into the module cache under
`$BENCH_CACHE`, and every later command runs offline (`GOPROXY=off`). The env also names `GOMODCACHE` and `GOCACHE`
under `/srv/rail-bench/cache/<project>/`, and `BASH_ENV` points at `$BENCH_CACHE/go-env.sh`, which setup writes.
typescript-go also needs node (its engines range is in typescript-go.md) and fetches the typescript npm tarball in
setup; tailscale builds with its own Go fork (tailscale.md). Check `go version`, `node --version`, `gcc --version`
(cgo), that `python3` is 3.11 or newer (the bench needs it) and that `unshare` is on PATH. 

A tool installed outside the default PATH gets a line `export PATH=<dir>:$PATH` in `/srv/rail-bench/toolchain.env`,
which `session.env` reads, so the bench and every child it starts find it (a child's PATH is the bench's own).

Write every install command you ran, idempotent (safe to run again on a machine that has it all), into
`$SET/notes/toolchain-go.sh`, a bash script a later session runs as root to get the same machine; it also
writes `/srv/rail-bench/toolchain.env` when it puts a tool outside the default PATH. Commit it on `SETS_BRANCH`
(step 8).

## Step 6. Admission, one project at a time

Order: caddy, then typescript-go (or the projects in PROJECTS). For a project P with file `$SET/P.toml`:

**6a. Read** `$SET/notes/P.md`, especially "For the admission session to try first", the header comments of the
project file, and `notes/go-common.md` (the Go clash rule: how a hidden test file that collides with an existing one is handled). Every command is marked `unverified`: nothing was ever run.

**6b. Smoke round.** Pick three situations: the oldest start, the newest start (the notes name them), and one the
notes' try-first list names. Run them as a job list, one at a time:

```
python3 $SRC/bench/cloud/joblist.py admit $SET/P.toml $BENCH_STORE/admission/P --keep-refused \
  --id <id1> --id <id2> --id <id3> > $BENCH_STORE/jobs/P-smoke-1.txt
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/P-smoke-1 $BENCH_STORE/jobs/P-smoke-1.txt -j 1
python3 $SRC/bench/cloud/jobs.py wait $BENCH_STORE/jobs/P-smoke-1 --minutes 110     # Bash timeout 7200000; repeat
```

Each job is `admit_one.py`: `bench admit` (it builds the sealed copy with the project's setup, with the network; the
hidden tests must fail at the start; with the fix they must pass 10 of 10 and the touched packages' tests pass;
Rail's setup and verify must pass on the start commit; the request must hold no link to the fix), then the hidden
tests with the fix and the network cut, then Rail's setup and verify in a new worktree under `.claude/worktrees/`
with the network cut. It writes `$BENCH_STORE/admission/P/ID.json` and prints `admitted` or `refused` with reasons.
Logs: `$BENCH_STORE/jobs/P-smoke-1/logs/ID.log` (a setup failure's tail is there and in the JSON's reasons). The
JSON holds the tails of the offline and worktree checks, but for the null, oracle and package checks only exits and
failing test names: to see their output, keep the refused copy (the smoke round does: `--keep-refused`) and run the
oracle by hand, `python3 $SRC/bench/cloud/jobs.py exec -- python3 $SRC/bench/bench grade $SET/P.toml --id ID --diff
$BENCH_STORE/sealed/2026-12/P/ID/fix.diff --json`, which prints every round's command tails; the null check is the
`test_files` command on a copy of `$BENCH_STORE/sealed/2026-12/P/ID/copy` with `hidden/` copied in.

**6c. Read each refusal and sort it.**
- *Settings fault*: setup fails; a tool or system library is missing; the tests cannot be built, collected or
  imported; a test fails only because of this machine, the network cut, HOME, a path, a timeout too short, or the
  `failed` pattern or `package_of` rule is wrong; Rail's setup or verify fails in the worktree for such a reason.
- *Nature of the situation*: the hidden tests pass at the start (null), the fix does not apply, the oracle is flaky
  (some of 10 fail) for reasons inside the project, a touched package's tests fail with the fix for reasons the fix
  does not touch, the request leaks the fix, the fix lacks a hidden test file.

Fix every settings fault in `$SET/P.toml`: change the command and keep the comment above it true (`# verified on the
cloud machine <date>: <what>` in place of `unverified` where you ran it and it worked; `# changed by the admission
session: <why>` where you changed it), and add a section "Admission session" at the end of `$SET/notes/P.md`
saying what you changed and why. Then run the smoke round again in a new state folder (`P-smoke-2`, then
`P-smoke-3`), after removing what the old settings made:
- a change to `[commands] setup` or `env`: `rm -rf $BENCH_STORE/sealed/2026-12/P` (the bench never rebuilds a sealed
  copy that exists) and delete the smoke ids' `$BENCH_STORE/admission/P/*.json`; if the change is to how a cached
  environment is built and not to its inputs (a venv, a node_modules store keyed by a hash with a fixed version
  string such as `pandas-venv-1`), bump that version string or delete the cache's folder under
  `$BENCH_STORE/cache/P/`, or the old one is reused;
- a change to `test_package`, `failed` or `package_of`: also `rm -rf $BENCH_STORE/sealed/2026-12/P/*/red` (the
  grade caches each package's start-commit run there, made with the old command and pattern);
- a change to any other command only: delete the smoke ids' JSONs; the sealed copies may stay.
At most three smoke rounds per project. If the settings still do not work after the third, the project is **not
workable here**: record why (the log lines that show it), keep its admission folder, and go on; step 7 brings in a
reserve.

**6d. Commit the settings** that work (step 8), before the full round.

**6e. Full round.** All the project's situations but those the last smoke round settled (their JSONs stay):

```
python3 $SRC/bench/cloud/joblist.py admit $SET/P.toml $BENCH_STORE/admission/P \
  | grep -v -F -f <(for j in $BENCH_STORE/admission/P/*.json; do printf '%s\t\n' "$(basename "$j" .json)"; done) \
  > $BENCH_STORE/jobs/P-full.txt
python3 $SRC/bench/cloud/jobs.py start $BENCH_STORE/jobs/P-full $BENCH_STORE/jobs/P-full.txt -j <n> --min-free-gb 5
```

(An empty list, when every situation is settled, is done at once.) Concurrency `-j`: caddy `-j 1` (its integration tests bind the fixed ports 2999, 9080 and 9443: two at once collide), typescript-go `-j 2`; rclone `-j 2`, tailscale `-j 2`.

Time: after the smoke round, take the mean minutes per situation from the JSONs (`seconds`) and project the full
round's hours. If one project's full round is projected over 12 hours, write its job list with
`--skip-offline-after 15` (the first 15 situations get every check, the rest `bench admit` only) and name the ids
that skipped the two extra checks in the final message.

Disk: a copy is small for caddy and rclone (10-70 MB) but about 0.3 GB and 72k inodes for typescript-go: 38 copies are
about 2.7M inodes, more than a 30 GB ext4 disk may have (typescript-go.md). Each project's `$BENCH_CACHE` holds two
or more toolchains (0.3-0.5 GB each), its modules (rclone 1.5-2.5 GB) and a build cache that grows with every copy
path; when a cache's `gocache` passes 6 GB, run `. "$BENCH_CACHE/go-env.sh"; go clean -cache` for that project
between rounds (with `BENCH_CACHE=/srv/rail-bench/cache/<project>`). Watch `df -i /srv` as well as `df -h`: inode use
over 90% counts as low disk. The project's mirror (`$BENCH_STORE/mirrors/P.git`) holds every ref GitHub serves, pull requests
included, so it may be several times the repository's size. `--prune-refused` deletes a refused situation's sealed copy. If the runner stops for disk (`jobs.py
wait` exits 5, `STATE/stopped` says free disk): (1) keep results; (2) park the sealed copies of situations already
admitted, which `bench/cloud/restore_store.py` rebuilds later from their JSONs:

```
for j in $BENCH_STORE/admission/P/*.json; do
  python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("admitted") else 1)' "$j" \
    && rm -rf "$BENCH_STORE/sealed/2026-12/P/$(basename "$j" .json)"
done
```

and write in the progress file that P's admitted copies are parked; (3) find the situations a full disk refused
(`grep -l 'No space left' $BENCH_STORE/admission/P/*.json`) and delete those JSONs, so they are admitted again
rather than counted as refused; (4) delete folders in `$BENCH_STORE/tmp` older than an
hour (`find $BENCH_STORE/tmp -mindepth 1 -maxdepth 1 -mmin +60 -exec rm -rf {} +`); (5) start the runner again with
a job list made as above (it leaves out every situation with a JSON).
Never delete `$BENCH_STORE/mirrors` or `$BENCH_STORE/admission`. Delete a project's cache (`$BENCH_STORE/cache/P`)
only after its full round is done and kept, and only if the next project needs the room; write that in the progress
file
(the hardness step then rebuilds it).

Two projects at once: once caddy's settings are committed and its full round runs (`-j 1`), you may run
typescript-go's smoke and full rounds beside it in their own state folders. Nothing else may run caddy's tests while
a caddy round runs (the fixed ports).

**6f. When a full round ends**: a refusal and an error of the step itself both end a job with exit 1, so do not use
`--retry-failed` (it would admit every refused situation again). The step's own errors are the situations with no
`$BENCH_STORE/admission/P/ID.json` (a traceback in `STATE/logs/ID.log`): read why, and run just those once more in a
new state folder (a job list made as in 6e leaves out every situation with a JSON). Then write the table and keep:

```
python3 $SRC/bench/cloud/admission_table.py $BENCH_STORE/admission/P > $BENCH_STORE/admission/P/TABLE.md
python3 $SRC/bench/cloud/keep.py --repo $RESULTS --branch $RESULTS_BRANCH --dest admission $BENCH_STORE/admission/P
python3 $SRC/bench/cloud/keep.py --repo $RESULTS --branch $RESULTS_BRANCH --dest admission $BENCH_STORE/jobs
```

## Step 7. Reserves

A project ends **short** when fewer than 20 of its situations are admitted (15 are chosen after the hardness runs,
which drop the easy ones), or when it is not workable here. For each short proposed project, in order, run step 6 on
the next unused reserve: first `rclone`, then `tailscale`. If a reserve also ends short and the other reserve is unused,
run that one too. With PROJECTS set, only the projects named there.

The **projects in play** are two: each proposed project that is not short, and for each short one the reserve that
replaced it (the one with more admitted, if two were tried). If no project of a pair reaches 20, the one with most
admitted stays in play and the final message says the owner must decide. Write them to `$BENCH_STORE/admission/IN-PLAY.txt`, one per line: the project's name, a space, then a
one-line reason (`pandas 27 admitted`) and keep it (`--dest admission`).

## Step 8. Committing settings

In `/srv/bench-src` only, on `SETS_BRANCH`. First check the files still load: `cd $SRC/tests && python3 -m unittest
test_bench_sets` must pass (it loads every project file of the set and parses its commands with `bash -n`; no
network, seconds). Then:

```
git -C $SRC add bench/sets/2026-12
git -C $SRC commit -m "Admission settings for <project> on the cloud machine" -m "<what changed, one line each>"
git -C $SRC push origin "HEAD:refs/heads/$SETS_BRANCH"
```

Never commit anything outside `bench/sets/2026-12/` except a `bench/cloud/` fix that rule 6 allows. Also keep the
changed project file in the results: `keep.py ... --dest admission/sets $SET/P.toml`.

## Step 9. Housekeeping between waits

After every `jobs.py wait` that returns 3 (still running):
- `df -h /srv; df -i /srv`; if free space is under 5 GB, do the clean-ups of 6e before the runner stops itself;
- every second wait, and at least every two hours: keep `$BENCH_STORE/admission/P` and `$BENCH_STORE/jobs`;
- the newest JSONs and logs: a "No space left on device" means the disk ran out inside a job: clean up as in 6e;
- look at the newest JSONs for one settings reason refusing every situation (a fault the smoke round missed): if 5 in
  a row are refused for the same settings reason, `touch STATE/STOP`, wait for the running jobs to end, fix as in 6c,
  and start the round again in a new state folder, leaving out the situations already settled.

`jobs.py wait` exits 0 when all is done, 3 when time is up and it still runs, 4 when the runner is gone (start it
again), 5 when it stopped itself (read `STATE/stopped`: disk, or a STOP file; remove `STATE/STOP` before starting
again).

## Step 10. The final message

When every project of steps 6 and 7 is admitted and kept, keep `$BENCH_STORE/session` (`--dest .`) with
PROGRESS-ADMIT.md, then end with exactly this shape (Markdown):

```
ADMIT go: done            (or: stopped: <reason>)
Results: <repository URL without credentials> branch <branch> at <commit>   (fallback used: yes/no)
Settings: Rail branch <SETS_BRANCH> at <commit>; base origin/bench-sets <commit>
Machine: claude --version <v>; go <v>; node <v>; free disk at the end <GB>

| Project | Candidates | Tried | Admitted | Refused: settings | Refused: nature | Minutes per situation (median) | Sealed MB (median) | In play |
|---|---|---|---|---|---|---|---|---|

Admitted ids:
- <project>: <ids>

Refusals counted by reason (top five per project): ...
Settings changed (per project, one line per command: what and why); commands still unverified: ...
Situations that skipped the extra offline checks: ...
Projects in play: <two names> (<reason>)
Faults found in the bench or its scripts (file, what, how it showed): ...
Not done, and why: ...
```

Nothing after that message.
