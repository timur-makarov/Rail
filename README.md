# Rail

Rail keeps coding agents on a railroad: it says what is legal next, what counts as done, and when a person
must act. The agent writes the code; the engine owns ticket state. It is built for git, GitHub and Claude
Code, first of all for Claude Code cloud sessions, and for macOS and Linux, with Python 3.11 or newer.
It serves projects in Python, TypeScript, Rust and Go first: `rail init` finds them and writes what it knows
about each (`rail docs languages`).

## How it works

An agent left alone decides three things for itself: what to work on, when the work is done, and whether
it is good enough to merge. Rail takes those three decisions away from it. A small engine, copied into the
project's `.rail/` folder, makes them from what is in git. The agent keeps the part it is good at: writing
the code.

The agent runs one loop:

```text
rail next       the engine picks a ticket, makes its worktree, and says what to do
                (the agent works there)
rail advance    the engine checks the work and moves the ticket on, or says what failed
```

For a ticket's work, `rail next` also names a model and effort: a cheaper one for a fresh ticket, one rung
higher after each failed attempt. An unattended runner, a cloud session a scheduled task starts, hands each
ticket to a subagent on that model and runs `rail advance` itself.

A ticket goes through these states. The engine derives the state each time; the agent can't set it.

```text
new -> accepted -> implementing -> reviewing -> in-ci -> merge-ready -> merged
```

**A ticket is a contract.** It is a markdown file on its own branch with three parts the engine enforces:

- a Done Contract: commands that must pass (`Check:` lines);
- `scope_paths`: the only paths the change may touch;
- a tier, `AUTO` or `PERSON`: who merges.

The contract freezes when the ticket is accepted. From then on the agent can't weaken a check or widen the
scope quietly: a change goes through `rail amend`, which is recorded and shown to the reviewer, and on a
PERSON ticket to the person who merges.

**The engine decides what "done" means.** `rail advance` commits the change and runs the ship checks in
order: a rebase onto the base branch, ticket lint, open assumptions, scope, structure rules, the migration
fields of a migration ticket (`reversibility` and `rollback`), size, the architecture map (the `## Areas`
table in `ARCHITECTURE.md`), the project's own `verify` command (tests, lint, scans), each `Check:` line, and any
sensor the project has set up (a tool whose findings fail only on the lines the change adds). A failure sends the ticket back with the output. A failure counts as stuck only when it
repeats: when a step fails the same way twice in a row, a second opinion (`rail consult`) advises once, and
after one more failure the ticket is stuck. Five failures at one step are stuck whatever they were. A stuck AUTO
ticket is dropped with a record (nothing merged, so nothing needs undoing), and its issue says why; label the issue
again to retry. A stuck PERSON ticket waits for a person.

**A fresh agent reviews every change, and the author can't steer it.** The engine starts the reviewer
itself, in the ticket's worktree, with a brief built from the ticket and the diff, and binds the result to
the exact patch. A blocking finding holds the merge. The author answers every blocking finding. When it disputes a
blocking one, a second fresh agent, the refuter, decides: it sees the finding and its evidence, not the
author's argument. The only changes that skip the reviewer are those to paths you list in
`[review] skip_paths`, such as docs, and a sweep reads those afterwards.

**Two tiers say when a person acts.**

| | AUTO | PERSON |
|---|---|---|
| Accepts the contract | The engine, once the ticket is well formed | The engine; a person, for a kind the project names in `approve_contract` |
| Review | The reviewer, with a security checklist | The reviewer and a security seat |
| Merges | The engine, once CI is green | A person |

In a project with no remote there is no CI and no pull request: the engine merges both tiers, and a PERSON
ticket waits for a person's `rail accept NN` first.

A person is asked only about what a revert doesn't undo: deleted data, a data shape, credentials, code that runs
with secrets, Rail's own gates, money and the rest of the kinds in `rail docs kinds`. A ticket is PERSON when its
author names such a kind in `person_reason`, when it touches the paths `[kinds]` lists for one (the paths you
name, such as auth, schemas and infrastructure, plus the CI workflows and agent settings), `person_paths` (Rail's
own files) or a migration, or when the reviewer finds something of a kind in the change. Size raises no tier: a change past `[size] cap`
(600 changed lines) is offered a split once, because a reviewer checks a small change better. The engine raises a
tier and never lowers one.

**GitHub is the wall.** Every ticket is a pull request. The `rail` workflow runs `rail ci`, which repeats
every ship check on the pull request's head and fails when the patch has no complete review. A ruleset makes
that check required, so nothing reaches the base branch without it, whatever an agent does on its machine.
Hooks and permission rules in Claude Code catch mistakes earlier: no force push, no push to the base
branch, no merge outside the engine, no edit to the journal, no `.env` file.

**State lives in git and nowhere else.** The engine keeps a journal for each ticket in `.rail/journal/`:
every step it ran, every decision, every review finding. The journal is committed on the ticket's branch and
merges with the code. So any session on any machine can take up any ticket, two sessions never take the
same one (a claim is a push to the remote), and a machine that goes away costs minutes: hooks save the work
in flight at the end of each turn and every ten minutes.

**Work starts from a conversation.** Before a ticket exists, an agent questions the person who wants the
work: it reads the code first, then asks only what changes the contract, each question with its own
recommendation. That can happen in a Claude Code session or in any chat bot, such as Slack or Telegram, that
can clone the repository: the bot files the confirmed ticket as a GitHub issue labelled `rail`, and Rail takes
it in as it is. The ticket keeps a record of the questions and how each recommendation was taken.

**Your part is small, and it is on GitHub.** A ticket that needs you carries the label `rail:needs-you`.
You answer with the label `rail:go`, a comment, or the merge button. The agent never waits for you: it takes
the next ticket.

**Afterwards you can check what happened.** Each merge is one squash commit with the ticket, the tier, a
table of every step that ran, and a `Review:` trailer that says who reviewed it. `rail status` lists every
ticket and what it waits for. `rail stats` counts, over the merged tickets, how many needed a person, how
many were reverted, which steps failed, what the reviewer cost and how often its findings ended in a fix, and how the grilling went. Every 20
merged tickets, a sweep gathers the findings reviewers parked and the checks they proposed, reads any changes
that merged with no review, and turns what it finds into tickets. A source does the same for any other
signal, such as failed CI runs or last week's merges: a prompt in `.rail/sources/` that files tickets and
never edits.

**What Rail leaves to others.** It schedules nothing: a session or a cloud scheduled task starts the work,
and one person owns that task for a repository (`rail docs cloud` says why). Inside that session the engine
can start the worker for a ticket itself (`rail work`), on the model and effort it names, as it starts the
reviewer. It doesn't say how to write, test or debug code: that is the agent's craft. It doesn't deploy: a
ticket ends at its merge.

## Start in a Claude Code cloud session

A cloud session is Rail's standard place to work. Open one on your repository and say:

> Set this repository up for Rail, from https://github.com/timur-makarov/Rail

Claude clones the framework, runs `rail init`, writes the project's checks, map and `[kinds]`, installs what
the checks need, and opens one pull request. Then three things are yours:

1. Merge the pull request.
2. Make three settings on GitHub, which a cloud session can't change: import the ruleset, set the squash
   message, and delete merged branches. The ruleset is one file,
   [`seed/ruleset.json`](seed/ruleset.json) here and `.rail/ruleset.json` in your project: download it and
   choose it under Settings > Rules > Rulesets > New ruleset > Import a ruleset. `rail doctor` links each page.
3. Approve the environment's setup script when Claude proposes it, so later sessions start ready. Or paste it
   yourself: it is one file, [`engine/environment-setup.sh`](engine/environment-setup.sh), the same for every
   project.

After that, hand work over: say what you want in a session, or label a GitHub issue `rail`. Claude runs
`rail next`, does what the brief says, and runs `rail advance`, until a ticket needs you. Tickets that need
you carry the label `rail:needs-you`, and you answer with the label `rail:go`. `rail docs cloud` covers
running with no session open.

## Run with no session open

Scheduled tasks start the work for you: label an issue `rail` and a cloud session picks it up. Make them
once, in Claude Code's scheduled tasks, on the environment whose setup script you approved. One person makes
them for a repository; two people's tasks would each run on every event.

Make three tasks with these triggers, and one more on a schedule (hourly or nightly) as a net:

| Trigger | Filter | Why |
|---|---|---|
| Issue labelled | none | New work: the label `rail` |
| Pull request labelled | Labels contains `rail:go` | Your approval |
| Pull request closed | Is merged | A merge unblocks the next ticket |

Give every task this prompt:

```text
You are the Rail runner for this repository. Nobody is here to answer questions.

Repeat these steps:
1. Run `rail next --json`.
2. If `action.kind` is `agent_task`: give the brief to a subagent. Use the subagent already working this
   ticket if there is one and `action.model` has not changed; otherwise start one on `action.model` and
   effort. Give it `action.brief` word for word. Tell it to work in `cwd`, not to run `rail advance`, and
   to reply in one line: done, or what stopped it. When it replies, run `rail advance NN --json`, where
   NN is that ticket's number. If that answer is another `agent_task` for the same ticket, do this step again with it.
3. If `action.kind` is `script`: run `action.command`.
4. After any other answer from `rail advance`, go back to step 1.
5. Stop only when `rail next` itself answers that only a person can act or that there is no work.

Don't check or change a member's work yourself: `rail advance` does that. End with one message that
says which tickets wait for a person and what each one needs.
```

Don't add "edited" or "synchronized" triggers: the engine edits its own pull requests, and each edit would
start a run. To stop a ticket, add the label `rail:hold` to its pull request. To stop everything, open an issue
with the label `rail:stop`: nothing moves until you close it. To take a merged ticket out again, add the label
`rail:revert` to its merged pull request: Rail files the revert as a ticket. `rail docs cloud` has the rest.

## Start on your own machine

```bash
git clone https://github.com/timur-makarov/Rail ~/rail && ~/rail/install
```

```bash
cd /path/to/project && rail init
```

`install` links `rail` into `~/.local/bin`; there is no package. `rail init` copies the engine into `.rail/`,
adds a `## Rail` section to `AGENTS.md`, merges hooks and guard rules into `.claude/settings.json`, and adds
the `rail` workflow. It never overwrites a file of yours. Then open Claude Code in the project and ask it to
run `rail next`: the first answer is the init task, which proposes the project's checks, its map and its
`[kinds]` for you to confirm. On your own machine Rail installs nothing: you install the tools the checks
need, and the guard asks before `sudo` and other commands that could hurt your machine.

## Use it

Write a ticket like `.rail/tickets/TEMPLATE.md` and run `rail add <file>`, or label a GitHub issue `rail`.
Then tell Claude Code to work through the backlog, or drive one ticket with `rail next --ticket NN`. A local
session is for work you are there for; unattended work runs in the cloud (`rail docs cloud`). Work you already did on a branch with no ticket comes in
with `rail adopt BRANCH`: the agent writes its ticket, and its checks must fail on the base and pass on the
branch.

**Guides and skills.** Whatever Rail wants an agent to read, the engine puts in the brief: a page of craft
for building a ticket, debugging a repeated failure, answering review findings or resolving a conflict. The
`[guides]` table in `.rail/config.toml` says which page, or which of its sections, each situation's brief
carries. `rail init` also adds Claude Code skills to `.claude/skills/` that help a person turn an idea into a
ticket (`rail-blast-radius`, `rail-grill`, `rail-slice`). A guide is a hint: nothing fails when an agent
ignores it, and `rail stats` shows whether it helps. [`guides`](engine/docs/guides.md) has the situations and how to write a page.

Everything else is in the docs that ship with the engine, readable before `rail init` too. `rail docs` lists
the pages, which are also in [`engine/docs/`](engine/docs):

| To learn | Read |
|---|---|
| The loop, and what `next` and `advance` do | [`loop`](engine/docs/loop.md) |
| Putting work already on a branch onto the rail | [`adopt`](engine/docs/adopt.md) |
| How to write a ticket, and the tiers | [`tickets`](engine/docs/tickets.md), [`contract`](engine/docs/contract.md) |
| Questioning a request into a ticket, from a session or a chat bot | [`grill`](engine/docs/grill.md), [`bots`](engine/docs/bots.md) |
| The review, findings and the refuter | [`review`](engine/docs/review.md) |
| Questions the engine raises about a shipped change, and the run that answers them | [`triage`](engine/docs/triage.md) |
| States, retries and waits | [`states`](engine/docs/states.md), [`retries`](engine/docs/retries.md) |
| Cloud sessions, and running with no session open | [`cloud`](engine/docs/cloud.md), [`github-runner`](engine/docs/github-runner.md) |
| GitHub settings and pull requests | [`github`](engine/docs/github.md) |
| Structure rules and sensors | [`rules`](engine/docs/rules.md), [`sensors`](engine/docs/sensors.md) |
| Services, keys and MCP servers the work uses | [`tools`](engine/docs/tools.md) |
| The guards | [`guards`](engine/docs/guards.md) |
| Guides named in the brief, and the skills | [`guides`](engine/docs/guides.md) |
| The journal's files and events | [`journal`](engine/docs/journal.md) |
| The sweep, sources and the numbers | [`sweep`](engine/docs/sweep.md), [`sources`](engine/docs/sources.md), [`stats`](engine/docs/stats.md) |
| Every setting and every verb | `rail docs config`, `rail docs cli` |

## This repository

`engine/` is copied into each project by `rail init`; `seed/` holds the files it copies once; `packs/` holds
optional features; `tests/` holds the end-to-end tests: `python3 tests/run.py` runs them on several workers,
and `python3 -m unittest discover -s tests` one after another. `python3 tests/run.py --languages` takes a
small real project in each language from `rail init` to a merged ticket; a check whose tool the machine lacks
is left out and printed as "not run". [`tests/tools.sh`](tests/tools.sh) installs those tools on a machine
made for the work, and on your own machine only lists what is missing. A cloud environment for work on Rail
itself needs one line as its setup script:

```bash
[ -f Rail/tests/tools.sh ] && RAIL_CLOUD=1 bash Rail/tests/tools.sh || true
```

`CHANGELOG.md` says why each change was made.
