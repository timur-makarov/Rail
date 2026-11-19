# Cold read of Rail's documentation

Read on 2026-11-19, in a Claude Code cloud session, at commit `a670168` (main). The reader is an agent that had
never seen Rail and went by the docs only. It did not read `engine/rail/*.py` or `tests/`.

Each statement is marked **confirmed** (I ran it or read it) or **inferred** (I concluded it without running or
reading it directly). Line numbers refer to `a670168`. "Blocks" means the reader can't go on without guessing or
reading the code. "Slows" means the reader gets there, but only after a failure or by reading a second page.
"Cosmetic" means it costs little.

## Findings

| # | Page:line | What is wrong | How bad |
|---|---|---|---|
| 1 | `engine/docs/tickets.md:44-45` | Tickets on `migration_paths` must set `reversibility` and `rollback`, but no page says where they go (front matter or section) or what values they take | Blocks (for a migration ticket) |
| 2 | INIT_TASK brief (from `rail next`); `README.md:138-140` | The setup task only describes pushing a branch and opening a PR. Nothing says how the setup reaches `main` in a repository with no remote | Slows |
| 3 | `README.md:32-36`, `engine/docs/tickets.md:3-6` | `## Why` is required by ticket lint, but the docs name only three enforced parts and two optional sections | Slows |
| 4 | none (undocumented) | `rail add` answered `SCOPE_OVERLAP` ("can't be claimed while ticket 3 changes the same paths"). No page describes this rule | Slows |
| 5 | VERIFY_ASSUMPTIONS brief (from `rail next`) | The brief says "ask the person and stop", which contradicts `rail-build` and `guides.md`: nobody is there in an unattended run | Slows |
| 6 | `README.md:59-63` vs `engine/docs/loop.md:81-83` | README says a person merges a PERSON ticket and the engine merges AUTO "once CI is green". With no remote, a person runs `rail accept NN` and the engine merges | Slows |
| 7 | `README.md:38-40` vs `engine/docs/contract.md:12-14` | README says an amend on a PERSON ticket waits for a person; contract.md says a wider scope is accepted at once and only a changed Done Contract waits | Slows |
| 8 | `engine/docs/review.md:9`, `journal.md:67,131,141`, `stats.md:56` | "product file" decides the scope step, the review skip and `patch_id`, and is never defined | Slows |
| 9 | `engine/docs/loop.md:10-13`, `guides.md:16` | The answer's `reason.code` (IMPLEMENT, VERIFY_ASSUMPTIONS, STEP_FAILED, MERGE_BY_PERSON, RETRY_CAP, SCOPE_OVERLAP …) is never listed. `guides.md` keys a situation on "IMPLEMENT brief" | Slows |
| 10 | `README.md:42-45` | The ship-step list names "migration fields" and "the architecture map" without saying what they are. Elsewhere the map turns out to be `ARCHITECTURE.md`'s `## Areas`, checked by doc-lint | Slows |
| 11 | `README.md:129-136` vs the brief's start path | After `python3 <repo>/bin/rail init`, `rail` is not on `PATH`; the docs never mention `.rail/bin/rail` (only `init`'s output does) | Slows |
| 12 | `seed/skills/rail-grill`, `rail-blast-radius` descriptions | For "a fix to existing code", both descriptions say to use them before drafting the ticket; I can't tell which to open first | Slows |
| 13 | `seed/config.toml:64` vs `rail docs config` line 24 | The seed sets `consult.model = "claude-fable-5-2"`; the config reference gives the default as `''` | Cosmetic |
| 14 | `seed/config.toml:12` vs `rail docs config` line 11 | The seed says `setup`'s readers are "claim … and CI"; the reference says "the claim; rail adopt" | Cosmetic |
| 15 | `README.md:46-47` vs `engine/docs/retries.md:12-14` | README says consult advises once, with no condition; retries.md adds "without the pack, it waits for a person at the budget". Only `packs.md:20` says the pack is installed by default | Cosmetic |
| 16 | `engine/docs/review.md:3` vs `review.md:8-9` | The page says the review "can't be skipped", then gives the paths that skip it | Cosmetic |
| 17 | `engine/docs/loop.md:32` | `.worktreeinclude` is used and never explained | Cosmetic |
| 18 | `engine/docs/environments.md:9` | "run the smoke check": no page says what the smoke check is | Cosmetic |
| 19 | RETRY_CAP answer; `journal.md:37` | Running out of the retry **budget** is reported as `RETRY_CAP` and recorded as `trigger: "retry_cap"`, though the docs keep budget and cap apart | Cosmetic |
| 20 | `seed/skills/rail-clarity/SKILL.md:8,40` | The skill needs a person to answer and says so, but doesn't say what to do when nobody is there | Cosmetic |

### Quotes and evidence for each finding

1. tickets.md:44-45: "Tickets touching `migration_paths` must set `reversibility` and `rollback`." The ticket
   example (tickets.md:9-16), `TEMPLATE.md` and the config reference have neither key. `journal.md:69` only
   says the step fails when they are missing. `rail-blast-radius/SKILL.md:41` repeats the names. (Confirmed:
   `grep -rn reversibility` over README, engine/docs and the skills finds only these.)
2. The INIT_TASK brief (confirmed: the output of `rail next` in a fresh project with no remote): "Then commit what rail init
   added together with these changes to a new branch, push it, and open a pull request with `gh api`". Also
   ".rail/config.toml isn't on main." Nothing covers a repository with no remote. I committed straight to
   `main`. That worked (confirmed), but it was a guess.
3. README.md:32: "It is a markdown file on its own branch with three parts the engine enforces". tickets.md:5-6:
   "`## Request` and `## Split` are optional sections." A ticket with front matter and a Done Contract only
   failed: `ticket-lint: ran, fail ('## Why' is missing or empty)` (confirmed). The same ticket with a one-line
   `## Why` and no Out of scope, Assumptions or Look at sections passed lint (confirmed). So "the other sections
   are required" is not true either.
4. `rail add` of a ticket with `scope_paths = ["calc.py"]`, while ticket 3 also held `calc.py`: "ticket 6 ·
   accepted · owner none · SCOPE_OVERLAP … Ticket 6 can't be claimed while ticket 3 changes the same paths."
   (Confirmed.) `grep -rniE "overlap|same paths"` over README, engine/docs and seed/AGENTS.md finds nothing
   (confirmed).
5. Brief (confirmed): "If you can't verify one, ask the person and stop." `rail-build/SKILL.md:9`: "No person
   is present unless the brief says one is." `rail-build/SKILL.md:18`: "Nobody is there to ask".
   `guides.md:56-57`: "In an unattended session nobody answers. Say what the agent does instead". (Inferred:
   an unattended runner that follows this brief stops with no wait recorded.)
6. README.md:63: "| Merges | The engine, once CI is green | A person |". loop.md:81-83: "With no remote, a ready
   AUTO ticket is merged by the next `advance` … a PERSON ticket waits for `rail accept NN` first." Seen
   (confirmed): "Ticket 2 (PERSON) is ready to merge. A person reviews branch … and approves the merge: rail
   accept 2. The engine then merges it."
7. README.md:38-40: "a change goes through `rail amend`, which is recorded, and on a PERSON ticket waits for a
   person." contract.md:12-14: "A wider or narrower scope, or a change from AUTO to PERSON, is accepted again at
   once. … A PERSON ticket waits until a person runs `rail accept NN`" (that is, for a changed Done
   Contract). Not run.
8. review.md:9: "An AUTO ticket merges without a review when every product file it changes matches that list."
   journal.md:67: "A changed product file is outside `scope_paths`". No page defines it (confirmed by grep).
   (Inferred: it means every file except the ticket file and the journal, from tickets.md:36.)
9. loop.md:10-13 documents `owner` and `action.kind` but not `reason`. `rail next --json` returned
   `'reason': {'code': 'VERIFY_ASSUMPTIONS'}` (confirmed). Of the codes I saw, `grep` finds none of
   VERIFY_ASSUMPTIONS, STEP_FAILED, MERGE_BY_PERSON, RETRY_CAP or SCOPE_OVERLAP in the docs (confirmed). Only
   SPLIT, REBASING and SWEEP_EMPTY are named, each in passing.
10. README.md:43-45: "ticket lint, open assumptions, scope, structure rules, migration fields, size, the
    architecture map, the project's own `verify` command". The README never names `ARCHITECTURE.md` or
    doc-lint. The INIT_TASK brief was where I learnt the map's format (confirmed).
11. README.md:136: "`install` links `rail` into `~/.local/bin`". The brief has the reader start with
    `python3 <repo>/bin/rail init`, after which `which rail` found nothing (confirmed). `rail init`'s output
    says "wrote .rail/bin/rail" (confirmed). `rail doctor` then failed at `provision` until `rail provision`
    linked it into `/usr/local/bin` (confirmed). The doctor's fix line said so.
12. rail-grill: "Use when someone asks for a feature, a fix or a change in a project that runs on Rail."
    rail-blast-radius: "Use before drafting a Rail ticket for a change to existing code". `rail-grill/SKILL.md:10-11`
    gives the order (blast-radius may come before grill), but neither description does.
13. seed/config.toml:64: `model = "claude-fable-5-2"`. `rail docs config`: "| `consult.model` | `''` |"
    (confirmed, both read).
14. seed/config.toml:12: `setup = ""  # reader: claim (after each worktree is made) and CI`. `rail docs config`:
    "the claim: runs in each new ticket worktree … rail adopt: runs in the throwaway worktrees". The config
    reference doesn't say whether CI runs `setup` (confirmed, both read).
15. README.md:46-47: "a second opinion (`rail consult`) advises once". retries.md:12-14: "the consult pack
    advises once … Without the pack, it waits for a person at the budget." packs.md:20: "The `consult` pack is
    installed by default". `rail init` copied it (confirmed).
16. review.md:3: "The engine launches it, so it can't be skipped or written by hand". review.md:8: "**Which
    changes skip it.**"
17. loop.md:32: "copies the files `.worktreeinclude` lists". This is its only mention (confirmed by grep).
18. environments.md:9: "after a deploy, run the smoke check". No other page has the term (confirmed by grep).
19. The answer after the third failure (confirmed): "owner human · RETRY_CAP … failed the same way 2 times in
    a row, then once more after consult ([retry] budget)". The journal (confirmed):
    `"event":"consulted","trigger":"retry_cap"`. retries.md:11-18 keeps `[retry] budget` and `[retry] cap`
    apart.
20. rail-clarity:8: "**Assumes:** a person is present and can answer." :40: "Go on only when the person says
    so". (Inferred: a guide or runner could open it with nobody present.) `rail-blast-radius:18-19`,
    `rail-build:78`, `rail-deepen:8` and `rail-slice:56` do say what to do when nobody is there.

## Step 1: README and its pointers, then answers from memory

I read `README.md`, then each page its table points to: loop, adopt, tickets, contract, grill, bots, review,
states, retries, cloud, github-runner, github, guards, guides, journal, sweep, sources, stats. Then I wrote
these answers without looking back:

| Question | My answer from memory | Checked against | Right? |
|---|---|---|---|
| What Rail is for | It keeps coding agents on rails: the engine decides what to work on next, when the work is done, and whether it may merge, from state in git. The agent only writes code, and GitHub's required check is the wall | README.md:3-12, 71-73 | Right (confirmed) |
| The loop's two commands | `rail next` and `rail advance` | README.md:16-20, loop.md:7 | Right (confirmed) |
| What a ticket must contain | Front matter with `title`, `tier` and `scope_paths`; a Done Contract with at least one `Check:` line in backticks that can fail; Why, Out of scope, Assumptions, Look at | `rail add` (finding 3) | Partly wrong: `## Why` is required, while Out of scope, Assumptions and Look at are not required at `add`. Look at is only asked for before ship (confirmed). Misled by README.md:32 ("three parts") and the template, which shows every section |
| Who merges AUTO / PERSON | AUTO: the engine, once CI is green. PERSON: a person, with the merge button | loop.md:81-86, and run | Wrong for a repository with no remote. AUTO merges at the next `advance` with no CI. PERSON is approved with `rail accept NN`, then the engine merges (confirmed). Misled by README.md:63 (finding 6) |
| A step that fails twice the same way | Consult advises once, the agent gets one more attempt, and if that fails the ticket waits for a person. Five failures of any kind also wait | retries.md:11-19, and run | Right (confirmed by a run: 2 identical `checks` failures, a `consulted` event, a third failure, then `owner human`). The README leaves out that this depends on the consult pack (finding 15) |

## Step 2: setting Rail up in a new project

Project: a temporary folder outside the repository, `git init -b main`, with `calc.py` (`add`),
`tests/test_calc.py` and one passing test. No remote. All of the following was run and seen (confirmed) unless
marked otherwise.

| # | Command | Result | Did the docs say what to do next? |
|---|---|---|---|
| 1 | `python3 /home/user/Rail/bin/rail init` | exit 0, `INITIALISED`. It copied the engine and the consult pack, wrote config, template, workflow, a source, the ruleset, 11 skills, AGENTS.md and `.claude/settings.json`, and said "Next: rail next" | Yes |
| 2 | `rail next` | `rail` not on PATH; used `.rail/bin/rail next` instead. It answered `INIT_TASK`, written for a cloud session: commands, ARCHITECTURE.md, person_paths, rules, then push a branch and open a PR | Partly: there was no path for a repo with no remote (finding 2), and `rail` wasn't on PATH (finding 11) |
| 3 | Set `verify = "python3 -m unittest discover -s tests -t ."`, wrote `ARCHITECTURE.md` with `## Areas`, then ran `rail doctor` | exit 3: `provision` and `environment` failed; the fix lines said to use the environment's setup script or `rail provision` | Yes, from doctor's output |
| 4 | `rail provision`, with `HOME` pointed at a scratch folder so this session's own Claude settings weren't changed | exit 0, "rail linked into /usr/local/bin; hooks written to ~/.claude/settings.json" | Yes |
| 5 | `git commit` of the setup straight on `main`, then `rail doctor` | exit 0, "Everything Rail needs is in place." | Committing on `main` was my guess (finding 2). Because of the scratch HOME, doctor's "machine's hooks do their work" was not true of this session (inferred) |
| 6 | `rail next` | `NO_WORK`, "New work starts with: rail add <ticket file>" | Yes |
| 7 | `rail add` with a ticket (AUTO, `scope_paths = ["calc.py", "tests/**"]`, one Check, one ASSUMED row) | exit 0, ticket 1 accepted, "rail next --ticket 1" | Yes |
| 8 | `rail next --json` | `agent_task`, `VERIFY_ASSUMPTIONS`, model `claude-sonnet-5-5`/medium, worktree `.claude/worktrees/1`. The journal had `base_checks` with `red` | Yes, apart from "ask the person and stop" (finding 5) |
| 9 | Changed ASSUMED to VERIFIED, then `rail next` | `IMPLEMENT` brief with the `rail-build` guide and "Nothing saves your work for you in this session. Run rail save 1…" | Yes |
| 10 | Implemented `sub` and its test, wrote `## Look at`, then `rail advance 1` in the worktree | exit 0 in 9 s: every step passed, the review ran with 0 findings, `merge-ready`, "rail advance 1" with `cwd: .` | Yes |
| 11 | `rail advance 1` from the project root | `MERGED`: one squash commit on `main` with Why, Look at, Evidence, Risk and the `Ticket:`, `Tier:`, `Review:` trailers | Yes. GitHub was not involved, so this is as far as the flow goes without a remote |
| 12 | PERSON ticket 2: `rail add`, then `rail accept 2 "ok"`, implement, `rail advance 2` | `APPROVE_CONTRACT`, then claimed; ship passed with a `review` and a `security` run; `MERGE_BY_PERSON`; after `rail accept 2` and `rail advance 2`, `MERGED` | The README table says otherwise (finding 6); loop.md is right |
| 13 | Ticket 3 with a check that fails, `rail advance 3` three times with no change | 1: STEP_FAILED (ladder moved to sonnet/high). 2: STEP_FAILED, consult ran ("change (same-model)"), `rail-debug` guide named. 3: `RETRY_CAP`, `owner human` | Yes; matches retries.md (finding 19 is the naming) |
| 14 | `rail add` of a ticket with only front matter and a Done Contract, then with `tier` left out, then with Check `` `true` `` | Lint failed on `## Why`, on the tier, and on the vacuous check, each with a clear message | Finding 3 |
| 15 | `rail add` of ticket 6, which overlaps ticket 3's paths | `SCOPE_OVERLAP` | Finding 4 |

I didn't go further: CI, the pull request flow and GitHub labels need a remote. I did not run the README's
`git clone … ~/rail && ~/rail/install` (not attempted: it writes into the home folder and the brief starts from
`bin/rail init`).

## Step 3: every page `rail docs` lists

`rail docs` lists 24 topics: 22 pages in `engine/docs/` plus `config` and `cli` (confirmed). I read each one.

Method for pointers and commands, all confirmed:

- Every relative Markdown link in README.md, engine/docs and the skills resolves to an existing file.
- Every `rail docs TOPIC` reference names a listed topic.
- Commands shown in the docs, run as written in the test project: `rail stats`, `rail stats --since 2026-01-01`,
  `rail source`, `rail context 1`, `rail intake --external-id PROJ-1 --title T --brief FILE`,
  `rail consult 3 "…"`, `rail sweep`, `rail next --ticket 3`, `rail accept NN "note"`, `rail docs cli`. All
  worked. `rail intake github` exited 2 with "needs a GitHub remote and gh", which matches the docs' "when
  GitHub can be reached". `rail adopt` on `main` refused as adopt.md:30 says it should.

Per page. "None found" means none of the four kinds the brief asks for.

| Page | Contradiction | Term before explained | Command fails as written | Missing pointer |
|---|---|---|---|---|
| adopt | none found | none found | `rail adopt` refuses on main, as documented | none |
| adr | none found | none found | none shown | none |
| bots | none found | "Dots" (bots.md:3, also grill.md:4) is never said to be a chat product; cosmetic, left out of the table | none run (needs GitHub) | none |
| cloud | none found | none found | not run (needs GitHub and a scheduled task) | none |
| contract | finding 7 | none found | not run | none |
| environments | none found | finding 18 | none shown | none |
| github | none found | none found | not run (needs GitHub) | none |
| github-runner | none found | none found | none shown | none |
| grill | none found | none found | none run | none |
| guards | none found | none found | none run (I did not exercise the guard hook) | none |
| guides | finding 5 (with the brief) | finding 9 ("IMPLEMENT brief") | none | none |
| journal | finding 19 | finding 8 | none | none |
| loop | finding 6 (with README) | findings 9, 17 | none | none |
| packs | finding 15 (with README) | none found | none | none |
| retries | finding 15 | none found | `rail consult` and `rail accept` worked | none |
| review | finding 16 | finding 8 | not run (no findings to answer) | none |
| rules | none found | none found | none shown | none |
| sources | none found | none found | `rail source` worked | none |
| states | none found | none found | none | none |
| stats | none found | finding 8 | `rail stats` and `--since` worked | none |
| sweep | none found | none found | `rail sweep` worked (`SWEEP_EMPTY`) | none |
| tickets | finding 3 (with lint) | finding 1 | `rail intake --external-id …` worked; `rail intake github` needs a remote | none |
| config | findings 13, 14 (with the seed) | none found | none | none |
| cli | none found | none found | none | none |

## Step 4: the skills, from their descriptions alone

| Skill | When I would open it, from the description alone |
|---|---|
| `rail-blast-radius` | Before drafting a ticket for a change to existing code, to get its scope, tier and size |
| `rail-build` | When `rail next` hands me a ticket in `implementing` to work |
| `rail-clarity` | When a person doesn't know what to ask for yet |
| `rail-conflict` | When `rail next` or `rail advance` answers `REBASING`, or any rebase stops on a conflict |
| `rail-debug` | When the same step has failed twice, or a fix didn't work |
| `rail-deepen` | When a request is clear but shallow, before it becomes a ticket |
| `rail-findings` | When `rail next` returns a ticket with open review findings |
| `rail-grill` | When someone asks for new work and it should become a ticket |
| `rail-self-check` | When a ticket's work looks complete, before `rail advance` |
| `rail-slice` | When a request is several pieces of work or over the size cap |
| `rail-verify` | When setting a project up for Rail, or when a ticket asks for better verification |

- **Two I can't tell apart:** `rail-grill` and `rail-blast-radius`, for a request to change existing code
  (finding 12). `rail-clarity` and `rail-deepen` are told apart by "unsure" versus "clear but shallow".
- **Instructions that need a person and give no fallback:** `rail-clarity` (finding 20). The VERIFY_ASSUMPTIONS
  brief, which is not a skill, does the same (finding 5). `rail-grill` defers to grill.md, which states a person
  is present; it is meant for that case. Every other skill says what to do with nobody present, or needs no
  person (confirmed by reading each SKILL.md).
