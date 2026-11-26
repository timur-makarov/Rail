# More work and more tools: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and are
no longer described here: the time lines of `rail stats` (`rail docs stats`, "WHERE THE TIME GOES"); finding a
ticket's pull request by its branch, issues read to the last page, `GITHUB_LIMIT` and writes a second apart
(`rail docs github`, "Many pull requests, and GitHub's limits"); tools declared as `[tools.NAME]` with the
missing-name wait `TOOL_MISSING`, probes after a failure, `TOOL_DOWN`, `ci = true` and the checks of `rail
doctor` on what a ticket branch can reach, doctor's tool lines and the candidates `rail init` names (`rail docs
tools`, `rail docs retries`); and the kinds of wait, `approval`, `grant` and `hold` (`rail docs retries`). Nothing
below is implemented, and nothing below was run.

**Set aside by the owner on 2026-11-26.** Nothing on this page is built until the owner takes it up again.
Other pages that wait for a part of it (the machine identity, read-only tools for the engine's agents, sources
with a schedule) wait with it.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

The owner's position (2026-11-25): build Rail to last until a model that can program unaided is public, and
build it to handle an ever larger amount of work and of tools to integrate. Lasting past that model is not a
goal.

Today more work means more sessions. Each session claims one ticket at a time by pushing a `claimed` event,
so two sessions never take the same ticket (`engine/rail/cli.py`, confirmed). Four things still stop that from
growing.

**1. One ticket's scope can hold back many.** An accepted ticket whose `scope_paths` overlap those of any
ticket still open (implementing, reviewing, in CI, merge-ready: `OPEN` in `engine/rail/state.py`) rests as
`SCOPE_OVERLAP` until that ticket merges or is dropped (`engine/docs/tickets.md`, confirmed). Overlap is judged
glob against glob (`engine/rail/util.py`, confirmed), so a ticket scoped `src/**` holds back every ticket under
`src/` for its whole life, review, CI and the wait for its merge included. `rail stats` now reports how long
tickets rest this way (`accepted to claimed`, `behind a ticket with an overlapping scope`); what to do about it
is not built.

**2. Every merge puts every other shipped ticket behind.** The ruleset requires branches to be up to date, so
each shipped pull request that falls behind is rebased with no agent work and CI runs again
(`engine/docs/github.md`; the `REBASE_BEHIND` row of `engine/rail/table.py`, confirmed). With K tickets shipped
and waiting, merging them one by one can start about K(K-1)/2 extra CI runs (inferred: each merge makes each
remaining one behind). A merge queue is mentioned only as something a project adds itself (`github.md`,
confirmed).

**3. GitHub's limits are shared, and the engine reads more than it must.**

- What the forge read is thrown away after every write and every shell command (`engine/rail/forge.py`,
  confirmed), so a command that runs `verify` reads the pull requests again. Nothing sends `If-None-Match`.
- Nothing counts the calls a command made, so nobody knows what a merged ticket costs in requests.
- GitHub's limits (confirmed on GitHub's docs, 2026-11-25): 5,000 requests an hour for a person's token,
  shared by every app and token acting as that person; 1,000 an hour per repository for `GITHUB_TOKEN`;
  a GitHub App installation gets at least 5,000, rising with repositories and users up to 12,500. Secondary
  limits: at most 100 requests at once, 900 points a minute per endpoint (a read costs 1, a write 5), and in
  general 80 content-creating requests a minute and 500 an hour. A conditional request answered `304 Not
  Modified` does not count against the primary limit. Every session, the runner and the person's own `gh`
  then likely share one person's 5,000 (inferred: the runner's work carries that person's login,
  `engine/docs/cloud.md`, "One runner for a repository"; how a cloud session picks its GitHub identity is not
  verified, see "Assumed, not verified").

**4. Every command reads every ticket ever filed.** `Project.tickets()` reads each ticket branch, every
`Ticket:` trailer on the base branch and every file under `.rail/tickets/` on it, and `derive` builds the
facts of each one, merged ones included: lint, the review ledger, the retry budgets (`engine/rail/project.py`,
`engine/rail/state.py`, confirmed). The cost grows with the project's history (inferred). It was never measured.

**5. The engine's own agents can't be given a tool.** The reviewer, the refuter and consult run with
`--safe-mode` (`seed/config.toml`, confirmed), and `--safe-mode` ignores an explicit `--mcp-config` (tested
locally and in the cloud on 2026-11-24), so a `[tools.NAME]` with `review = true` reaches their brief as text
but never as a server they can call. Nothing writes down how a person grants the machine an identity, an admin
right or a sudo rule; each wait that needs one has no name for it beyond `grant`.

## Part 1: fewer tickets held back

**A lock on what changed, chosen by config.** `[claim] overlap = "scope"` (today's rule, the default) or
`"changed"`. With `"changed"`, a ticket rests only while its `scope_paths` overlap files an open ticket has
already changed (`Project.changed_files` in `engine/rail/project.py`, confirmed), not that ticket's whole
scope. A ticket can only change files in its own scope, so two tickets collide only when both change the same
file. That shows at the second one's rebase as a conflict, which already has its brief (`CONFLICT`).
So `"changed"` trades rests for an occasional conflict.

Rule for switching the default: when `rail stats` shows that accepted-to-claimed time behind an overlapping
ticket is over a quarter of request-to-merge time across 30 merged tickets, and conflicts at rebase stay under
one in ten tickets in a trial with `"changed"`. Both numbers are guesses for the owner to set (Decision 1).

**One rebase at a time.** When several shipped tickets are behind, the engine rebases only the one that will
merge next (lowest ID among the green ones, else the lowest ID), and leaves the rest behind until it merges.
CI then runs about once per ticket per merge instead of once per ticket per earlier merge (inferred). Rule for
building it: `rail stats` shows more than two rebases per merged ticket on average over 30 merged tickets
(`Rebases after the first ship`).

**A merge queue, not now.** GitHub's merge queue would batch merges, but the engine merges through REST, and
whether a REST merge enters a queue was not checked; GraphQL, which enqueues, is blocked in cloud sessions
(`engine/docs/cloud.md`, "What the cloud refuses", confirmed). It stays the project's choice, as today.

## Part 2: GitHub at scale

1. **Conditional reads.** The forge keeps each read's `etag` in the local cache (`.git/rail/cache/`) and sends
   `If-None-Match` on the next read of the same URL. A `304` costs no primary limit (confirmed) and the cached
   body is used. Whether `gh api` returns a `304` as a success or an error was not checked.
2. **Count the calls.** Each engine event a command writes carries `gh_calls`, the REST calls that command
   made. `rail stats` gives calls per merged ticket and `rail doctor` shows `x-ratelimit-remaining`. Rule: when
   calls per merged ticket times merged tickets per hour passes half of the token's limit, the machine
   identity (Part 6, item 1) is the fix, since an installation's budget is its own.

## Part 3: history that doesn't slow every command

A merged or dropped ticket's facts can't change. The engine keeps them in the local cache keyed by the base
branch's tip and the `rail/ids` counter's tip, and derives only open tickets on each command; a changed key
reads them again. Built only after a measurement: `rail next` on a fixture with 20 and with 2,000 merged
tickets. Rule: build it when the 2,000 case takes over 5 seconds, or over twice the 20 case.

## Part 4: one person, many repositories

A person may own the waits of many repositories. `rail docs cloud`, "Where your acts go", gives the inbox for
one repository as the search `is:open label:rail:needs-you`. Across repositories it is one saved search on
GitHub: the same with `user:OWNER`, or `author:@me` when the work carries the person's login, or
`author:app/NAME` with a machine identity (search qualifiers from my knowledge, not checked). `rail doctor`
prints the search for this repository's owner. A paragraph in `engine/docs/cloud.md`; no code beyond the doctor
line.

## Part 5: tools, what is left

A `[tools.NAME]` declaration is built (`rail docs tools`). Three things around it are not.

1. **The engine's agents get read-only tools.** The engine writes an MCP config holding only the
   `review = true` servers from `.mcp.json` to the cache and sets `RAIL_MCP_CONFIG`. The seed's review,
   refuter and consult commands change from `--safe-mode` to `--setting-sources "" --disable-slash-commands
   --strict-mcp-config --mcp-config "$RAIL_MCP_CONFIG"`, keeping the other flags they have (the review command
   already takes `RAIL_REVIEW_PROMPT` and `RAIL_REVIEW_SCHEMA`). In local tests with canaries on 2026-11-24
   (Claude Code 2.1.292) these flags loaded no CLAUDE.md, project skill, plugin or project hook, as
   `--safe-mode` does, and did load the server; that is a tested result, not documented behaviour, so the
   pilot (test 3) checks it again on the version in use. The command stays agent-neutral: the engine sets a
   variable, the command chooses its flags. The engine sets `RAIL_MCP_CONFIG` before every review, refuter and
   consult run, and it points to an empty server list when no tool has `review = true`.
2. **A `rail-tool` skill** adds a tool: the declaration, the probe, the name in each place, and the line in
   `rail.yml` for a `ci = true` key. `rail-grill` points to it when a request needs a new service.
3. **Each run records the tools it used,** in the worker's `worked` event, so `rail stats` shows which tools
   tickets use and which probes fail.

Adding or changing a tool edits `.rail/config.toml`, so it is a PERSON ticket. Granting the machine a key is a
person's act (`engine/docs/environments.md`).

## Part 6: grants

A grant is a person's one-time act that lets the machine do something. Each wait the machine can't get past
names the grant it needs (`grant` kind, built), and `rail doctor` lists grants held and lacking (not built).

1. **A machine identity:** a GitHub App or a machine account, set up once. Its pull requests can be approved by
   any person (`proposals/team.md` section 3), and an installation's rate limit is its own (Part 2). Not
   verified: how a cloud session picks its GitHub identity (`team.md` section 3).
2. **Sources declare their schedule.** A source's front matter gains `every = "1d"`. One runner then runs every
   source, instead of one scheduled task per source (`engine/docs/sources.md`, "Running a source", confirmed).
   Where `rail next` answers matters: today it returns `WAITING_PERSON` whenever any ticket waits for a person,
   before it reaches the sweep (`engine/rail/cli.py`, confirmed), so one open wait stops the sweep, and a due
   source placed the same way would starve. A due source, and a due sweep with it, is answered before the
   `WAITING_PERSON` return: after every ticket the agent can act on, after a CI watch, and before reporting
   waits. The waits still go into the answer's `waits` list and their labels are set earlier in the same
   command, so the person's inbox is unchanged; the runner, which stops only when `rail next` says nothing is
   left for an agent, keeps going until the source has run. A source's last run is kept the way the sweep's is:
   the sweep finds its last run from the `Sweep:` trailer on the base branch (`engine/rail/sweep.py`,
   confirmed). A source files tickets and merges nothing, so it has no commit of its own on the base; its run
   time goes into the `requested` event of each ticket it files, and a run that files nothing writes a
   one-line mark in the local cache (inferred design: a fresh cloud clone then runs a source that filed
   nothing once more, which costs one `fetch` and files nothing new, since `external_id`s are unique,
   `engine/docs/sources.md`). The counter branch is not used: it holds ids and drop marks
   (`engine/rail/project.py`, confirmed).
3. **An admin grant** lets the engine apply and repair the repository's settings: the ruleset, squash
   settings, branch deletion, labels. A cloud session can't write settings (`cloud.md`, confirmed), so this
   needs the machine identity with admin rights. It weakens the guard "a cloud session can't change settings"
   that `cloud.md` names as the one an agent can't get around (Decision 3).
4. **A local grant for provision.** On a person's own machine Rail installs nothing (`cloud.md`, table,
   confirmed). A one-time sudoers rule lets `rail provision` run the `provision` command as it stands on the
   base branch, never a worktree's copy, so an unmerged change can't run as root (inferred design; Decision 5).

## Left out

- **How many sessions run, and when.** That is the host's (framework lens: orchestration belongs to hosts).
  Rail answers one ticket per `rail next` and lists agent-owned tickets in `rail status --json`.
- **A webhook server.** GitHub's docs prefer webhooks to polling (confirmed); Rail has no server, and the
  scheduled task's GitHub triggers are its events.
- **Per-person statistics** (`team.md`).
- **Best-of-N runs** to use spare capacity: one attempt per ticket (owner, 2026-11-25).

## Docs and files that change

- `engine/rail/stats.py`, `engine/docs/stats.md`: calls per merged ticket.
- `engine/rail/state.py` (`derive`), `engine/rail/config.py`, `seed/config.toml`, `engine/docs/tickets.md`:
  `[claim] overlap`.
- `engine/rail/cli.py`, `engine/rail/table.py`, `engine/docs/github.md`: one rebase at a time; due sources.
- `engine/rail/forge.py`: `etag`s, call count.
- `engine/rail/project.py`: the cache of settled tickets.
- `engine/rail/config.py`, `seed/config.toml`: the review, refuter and consult commands.
- `engine/rail/review.py`, `engine/rail/consult.py`: `RAIL_MCP_CONFIG`.
- `engine/rail/doctor.py`: grants, the inbox search, `x-ratelimit-remaining`.
- `engine/docs/sources.md`, `engine/rail/sources.py`: `every`.
- `engine/docs/tools.md`: the read-only tools and the tools a run used. `engine/docs/cloud.md`: the inbox across
  repositories, the machine identity, sources without their own tasks.
- New: `seed/skills/rail-tool/SKILL.md`; `seed/skills/rail-grill/SKILL.md` points to it.

## Tests, each before its part is kept

1. **Gate cases, no model** (fixture projects and `tests/fake_gh.py`):
   - `overlap = "changed"`: two tickets with overlapping scopes and different changed files both claim; the
     same file changed by both gives a conflict at the second rebase; `"scope"` keeps today's rest.
   - One rebase at a time: three shipped tickets behind; after one merge only the next to merge is rebased.
   - The fake answers `304` to a repeated read: the cached body is used.
   - `gh_calls` on events matches the fake's request log.
   - Settled-ticket cache: on a fixture with 2,000 merged tickets, facts from the cache equal facts from a full
     derive, for every ticket, before and after a merge and a drop. The timing measurement runs first.
   - The review, refuter and consult commands get `RAIL_MCP_CONFIG` (with the review command's other
     variables), with an empty server list when no tool is `review = true`; the file holds only
     `review = true` servers.
   - A tool a run used is on its `worked` event, and `rail stats` counts it.
   - A due source is answered by `rail next` when no ticket work is left, and not before; with a ticket waiting
     for a person, the due source and a due sweep are still answered, the waiting ticket keeps its label, and
     the next `rail next` after the source ran returns `WAITING_PERSON`.
   Kept when every case behaves as written.
2. **Load, no model, real GitHub.** In a throwaway repository, 20 small tickets with overlapping and separate
   scopes, three sessions in parallel, the worker replaced by a fake command that writes a fixed change (it
   needs `rail work`, which is built). Recorded: REST calls per merged ticket, CI runs per merged ticket,
   rebases, time per state, any rate-limit answer. Run before and after Parts 1 and 2; kept when CI runs and
   calls per merged ticket fall and nothing else changes.
3. **Cloud pilot, with a model.** One tool reached through a network secret with a probe, one `review = true`
   MCP server: the worker uses the tool; the reviewer sees the server and no project hook (a canary, as on
   2026-11-24); breaking the secret gives a failing probe and a grant wait, with no attempt spent. This uses
   a model, so its wording stays untested until the owner restarts the paused model tests.

Not covered: GitHub Enterprise limits; forges other than GitHub; how many sessions a host should start.

## Assumed, not verified

- That `gh api` passes `If-None-Match` and reports a `304` in a form the forge can read.
- That a REST merge does not enter a merge queue.
- That the search qualifiers in Part 4 work across repositories as written.
- That a sudoers rule can be limited to `rail provision` running the base branch's command, with nothing a
  worktree can change on that path.
- How a cloud session picks its GitHub identity, so whether a machine identity works in the cloud at all.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. Part 6 item 1, the machine identity: first check how a cloud session picks its GitHub identity, then build
   after Decision 4. Part 2 item 2's fix for the rate limit also needs it.
2. Part 5 items 2 and 3: the `rail-tool` skill; tools on runs.
3. Part 5 item 1: read-only tools for the engine's agents (after the cloud pilot).
4. Part 6 item 2: due sources.
5. Part 2: `etag`s and the call count.
6. After the numbers from `rail stats`: Part 1 (overlap mode, one rebase at a time), Part 3 (the cache), with
   the load test.
7. Part 4: the inbox search in `rail doctor` and its paragraph in `cloud.md`.
8. After their decisions: Part 6 items 3 and 4.

## Decisions

**Made by the owner:**

- 2026-11-25: build for ever more work and tools until a supercoder is public; not beyond.
- 2026-11-24: the tools-and-keys design and the seven grants; the reviewer stays a swappable `claude -p`
  command.
- 2026-11-26: secrets reach pull request CI only as `ci = true` keys (built). A rotation reminder for those
  keys (`rotate_days`) was judged not worth building: rotation stays the person's own practice.

**Open:**

1. The numbers for switching `[claim] overlap` to `"changed"`: a quarter of request-to-merge time resting,
   conflicts under one in ten (proposed).
2. One rebase at a time (proposed), or ask projects to turn on GitHub's merge queue once it is shown to work
   with REST merges.
3. The admin grant (Part 6 item 3). Proposed: not by default; a project that wants it grants it, and
   `rail doctor` says which guard that removes.
4. Machine identity as a GitHub App (proposed: its own rate limit and scoped permissions) or a machine account.
5. The local sudo grant's shape (Part 6 item 4). Proposed: build only after the assumption above is checked.

## Sources

Rail, confirmed: `engine/rail/cli.py`, `state.py`, `table.py`, `project.py`, `forge.py`, `util.py`, `stats.py`,
`sweep.py`; `engine/docs/cloud.md`, `github.md`, `sources.md`, `tickets.md`, `tools.md`, `environments.md`;
`seed/config.toml`; `proposals/team.md`.

GitHub's docs, confirmed 2026-11-25: "Rate limits for the REST API"; "Best practices for using the REST API".

The tests of 2026-11-24 that `--safe-mode` ignores `--mcp-config`, and that the replacement flags load only the
server: run on that date, not repeated here.
