# Running the real product on every ticket: what is left to build

This page is a proposal: what remains of a larger one. Parts of what it relies on are built and are no longer
described here: tool declarations `[tools.NAME]` with `env`, `probe` and `ci = true`, the `TOOL_MISSING` wait and
the probes that run after a failure (`rail docs tools`); the waits and their kinds (`rail docs retries`); the
kinds of change a revert doesn't undo, `data-exposure` among them (`rail docs kinds`); and the label
`rail:revert` (`rail docs tickets`). Nothing below is implemented, and nothing below was run. The page says how
Rail could make every ticket that changes behaviour run the product the way its users reach it, keep what that
run showed, and say which pieces a project lacks before the machine can do this on its own. Status: written
2026-11-25 from Rail's engine code and docs, published research (sources at the end), and the owner's positions
of 2026-11-25; checked against the code on 2026-11-26.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

Terms on this page, used the same way on the other proposals:

- **Surface:** one way users or other programs reach the product: a web page, an HTTP or RPC API, a command
  line, an agent-facing surface (MCP server, tools, markdown docs for agents), a data job, an integration with
  a third party, a mobile app.
- **Driving check:** a command that starts from the running product and uses one surface the way a user does,
  with deterministic assertions, and writes what it saw as evidence.
- **Machine-operable:** a project where the machine can start, seed, drive and probe the product with no person.

## Why

**Passing tests is a weak signal of working software.** About one in five benchmark patches counted as solved
fails stronger tests; agent-written suites kill 38-57% of planted bugs (reported, TestSuiteBench). Running the
product finds what reading code and unit tests miss: told to test as a user with browser automation, Claude
found end-to-end failures it had missed with unit tests and `curl` (reported, Anthropic, qualitative); across
16 models, browser calls per app correlate with accuracy at r = 0.72 (reported, Vibe Code Bench, correlational).
Data jobs that pass one run hide time-dependent faults: replaying with late, duplicate and out-of-order records
found 7.0-79.2% of snapshot-certified pipelines silently wrong (reported, ArrivalBench, arXiv 2610.02363).

**Rail runs the product once, at setup, and never requires it again.** `rail-verify` asks for "one check that
drives it the way a user would" when the project is set up (`seed/skills/rail-verify/SKILL.md`, confirmed).
After that a ticket's `Check:` lines may drive the product, but nothing requires it: ship runs ticket lint,
assumptions, scope, rules, sensors, migration, size, doc-lint, `verify` and the `Check:` lines
(`engine/rail/steps.py`, confirmed).

**What a run showed is not kept.** A step event keeps the step, status, result, patch id, detail, duration and,
when it failed, a signature: a hash of its output (`engine/rail/steps.py`, `engine/docs/journal.md`, confirmed).
The output itself goes into the failure brief, cut to 60 lines, and the pull request's Evidence table says only
"ran, pass" per step (`engine/rail/steps.py`, confirmed). Neither the reviewer nor a later reader can see what
the product did.

**Nothing tells a project what it lacks.** `rail doctor` checks Python, git, the claude CLI, hooks, guard
rules, AGENTS.md, the config, guides, sources, sensors' tools, declared tools and their probes, the cloud
machine and GitHub (`engine/rail/doctor.py`, confirmed). It says nothing about whether the product can be
started, seeded or driven. The owner's basis (2026-11-24) is that a person's one-time act grants the machine a
capability: a missing piece should be named as a grant for a person or a ticket for the machine.

**Rail is for software (decided by the owner, 2026-11-25).** `rail-verify` today gives a Blender add-on and a
video pipeline as examples (`seed/skills/rail-verify/SKILL.md`, confirmed). Those go: automating non-code work
is for the people who do it.

## Part 1: the product in config

Three new parts of `.rail/config.toml`. Each key names its reader, as the seed config does today
(`seed/config.toml`, confirmed). None exists: `engine/rail/config.py` has no `product`, `surfaces` or `preview`
key (confirmed).

```toml
[product]                                 # reader: ship and CI (the product step), rail doctor
start = ""                                # starts the product in the ticket's worktree and returns; RAIL_TICKET is
                                          # set, so parallel tickets pick their own ports and databases
ready = ""                                # exits 0 once the product answers; changes nothing
seed = ""                                 # loads test data and the test identity from files in the repository
stop = ""                                 # stops what start started
ready_secs = 120                          # how long ready may take before the product counts as not started

[[surfaces]]                              # reader: ship and CI; one table per surface
name = "web"
kind = "web"                              # web, api, cli, agent, data, integration, mobile
paths = ["app/**", "components/**"]       # a ticket that changes one of these runs this surface's check
check = ".rail/checks/web.sh"             # the driving check; writes evidence into $RAIL_EVIDENCE
preview = false                           # true: the check runs against a hosted preview (Part 6)
```

- `kind` decides which recipe `rail-verify` uses (Part 4) and which `rail doctor` checks apply (Part 2). The
  engine reads no other meaning into it.
- A project with no `[product] start` and no surfaces works as today. A `cli` or `data` surface often needs no
  `start`: its check runs the built program itself.
- The config check refuses an unknown key or kind, as it refuses unknown keys today (`engine/rail/config.py`,
  confirmed). `[[surfaces]]` is checked like `[[rules]]` and `[[sensors]]`.
- The driving check scripts live in the repository and count as tests: `rail init` adds each surface's `check`
  path to `[tests] paths` (`rail docs languages` describes the key), so that a ticket that edits a check script
  is held against the base's version of it once that rule exists: `proposals/checks.md` Part 1 proposes it, and
  nothing reads `[tests] paths` yet.

## Part 2: the machine-operable bar

A project is machine-operable when it has each of these. `rail doctor` reports each one, and the init task asks
for them.

| Piece | What `rail doctor` checks | Missing: whose act |
|---|---|---|
| One command starts the product | `[product] start` and `ready` are set, or every surface is `cli` or `data` | A ticket: the machine writes the script |
| A seeded test identity | `[product] seed` is set when a `web`, `api`, `agent` or `mobile` surface exists | A ticket for the seed files. A third party's test account is a grant |
| A driving check per surface | each `[[surfaces]]` has a `check` that exists at its path; at least one surface | A ticket |
| A place to run it | local always; for a surface with `preview = true`, the `[preview]` commands (Part 6) are set and their tool's names are present | The preview host's token is a grant (`[tools.NAME]`, `rail docs tools`) |
| Probes that tell a broken machine from broken code | `[product] ready`; each tool's `probe` (`rail docs tools`) | A ticket for `ready`; a failing tool probe is a grant |
| A way back | the `rail:revert` label (`rail docs tickets`) | Rail sets the label up. Prod is the project's own CD gate: Rail has no part in it (`rail docs environments`) |
| A machine that can run the surface | `mobile` with Android: `/dev/kvm` exists; with iOS: the machine is macOS | A grant: a runner with hardware acceleration, or a Mac |

**`rail doctor --product`** goes further: it runs `start`, `ready`, `seed`, each surface's check and `stop`
once on the base branch in a temporary worktree, and reports each as passed or failed. Plain `rail doctor`
stays fast and runs none of the project's commands, as today: it runs version commands and, with a remote,
GitHub calls through `gh` (`engine/rail/doctor.py`, confirmed).

**Each line names its kind.** Today a doctor line is a name, a pass or fail, and a detail (`engine/rail/doctor.py`,
confirmed). A failed bar line adds `kind`: `grant` (a person's one-time act, named exactly: which token, which
account, which machine) or `ticket` (the machine can build it). `grant` is the same kind as the wait kind of
that name (`rail docs states`). The init task asks the agent to file one ticket per `ticket` line with
`rail add`, and to list the `grant` lines in its pull request for the person, as it lists the repository
settings only a person can change today (`engine/rail/init.py`, confirmed). After setup, the sweep runs plain
`rail doctor` and files a ticket for a `ticket` line that is new since the last sweep.

## Part 3: a product step at ship, and its evidence

**The step.** A new ship step, `product`, runs after the `Check:` lines, in the same `check()` that ship and CI
share (`engine/rail/steps.py`, `engine/rail/cli.py`, confirmed). It runs when the change touches the `paths` of
at least one surface:

1. `start`, then `ready` until it exits 0 or `ready_secs` pass, then `seed`. When the ticket's surfaces include
   one with `preview = true`, Part 6 runs first and the check gets its URL.
2. For each touched surface, its `check`, with `RAIL_EVIDENCE` set to an empty folder for that surface and
   `RAIL_URL` set to the local or preview address. Each is recorded as a `step` event, `product: NAME`, with
   its duration, as `Check:` lines are recorded today (`engine/rail/steps.py`, confirmed).
3. `stop`, always.

A failed driving check counts like a failed `Check:` line: it moves the retry budget and cap as any step does.

**When the product doesn't start.** When `start` or `ready` fails, the engine runs them once on the base branch,
as it does for a `verify` that fails (`engine/rail/steps.py`, confirmed). If the base fails as well, the attempt
doesn't count and a fix ticket for the base comes first, with the same wording as the red-base `verify` case.
If only the ticket's branch fails, the failure is the ticket's. A command the shell can't find (exit 127) is
`could_not_run`, as today; a missing tool is a `TOOL_MISSING` wait that costs no attempt, and a failed probe
afterwards is `TOOL_DOWN` (`rail docs tools`, built).

**The evidence.** Each driving check writes what it saw into `$RAIL_EVIDENCE`: the steps it took, the requests
and responses, the command, output and exit code, and for a web page screenshots or a trace.

- **Text** (files under 64 KB each, 256 KB per surface in all) is committed with the step events in a new
  journal file, `NN-evidence.json`: per surface, per file, its name and contents, keyed by `patch_id`. Only the
  engine writes the journal (`rail docs journal`), so the worker can't rewrite it.
- **Values of declared secrets are replaced** before anything is committed: for each environment name a
  `[tools.NAME]` declares (`env`), and each `.env` value the worktree holds, its value becomes `[NAME]`.
  Evidence holds test identities and test-mode responses; a committed secret can't be taken out of history.
- **Binary files** (screenshots, traces, recordings) are not committed. On a session's machine they stay in the
  local cache beside the engine's other notes (`.git/rail/cache/`, `engine/rail/project.py`). In CI the rail
  workflow uploads `$RAIL_EVIDENCE` as a workflow artifact, so every pull request has them.
- **The pull request's Evidence table** gains one row per surface: `product: web | ran, pass | 6 steps, 2
  screenshots`, and the artifact's link when CI uploaded one. Today the rows come from step events
  (`engine/rail/steps.py`, confirmed).
- **The reviewer's brief** gets the text evidence of the patch it reviews, so a claim in the change can be held
  against what the product did. The reviewer can also run the check itself, as it can run any command now.

**What `rail stats` adds** (its own line only): driving-check failures per surface, and how many of them came
after `verify` and every `Check:` line had passed on the same patch. That second number is what the product
step catches that nothing else did.

## Part 4: one recipe per surface in `rail-verify`

`rail-verify` keeps its five sections (`seed/skills/rail-verify/SKILL.md`, confirmed). Section 3, "Drive the
real product", drops the Blender and video examples and gains one recipe per surface. Each recipe says what to
drive, what to keep as evidence, its negative control (break the behaviour on purpose, see the check fail,
restore it; section 2 already asks for this for `verify`), and what an agent most often fakes on that surface.
The tools named are those the research found documented; a profile in `rail docs languages` gives the variant
per language.

| Surface | Driving check | Evidence | What gets faked |
|---|---|---|---|
| Web | A Playwright script against the running app, as the seeded user, with deterministic assertions on what the page shows. An agent clicking through found the same bug in some runs and missed it in others for 22-28% of scenarios (reported, Waterloo seminar abstract), so an agent's exploratory pass is extra and repeated, never the check | Screenshots or a trace, the steps | Claiming done without opening the page; calling the API instead of clicking |
| HTTP or RPC API | Real requests with assertions (Hurl, curl, grpcurl); responses checked against the schema (Schemathesis, against a local or preview instance only, since it sends many invalid requests, reported). For a rewrite, the same requests to old and new, compared | Each request and response | Mocking the thing under test |
| Command line | The built binary on real files in a temporary folder, error cases and exit codes included. Snapshot tools that an agent can rewrite in one command (`TRYCMD=overwrite`, reported) count as changed tests | Command, output, exit code | Testing the library and never the binary; accepting new snapshots of broken output |
| Agent-facing | MCP Inspector's CLI, which does the handshake itself and then calls one method per run, `tools/list` or `tools/call`, with stable exit codes (reported; its docs page is a draft). A ticket that exposes something as a tool gets a contract test for it. A small eval of tasks a model should finish with the tools is recorded, not a gate (Decision 4) | The calls and results; the eval score | Testing the handler and never the tool as an agent sees it |
| Data job | The whole job on a real sample into a dev schema, with data-contract checks; then replayed with late, duplicate and out-of-order input, and run twice to show it is idempotent | Row counts, sample rows, contract results | One clean run taken as proof |
| Integration with a third party | The provider's test mode; a retry test and an idempotency test; secrets from the environment, tokens scoped | Requests, responses, the retry run | A mock of the provider standing in for its test mode |
| Mobile | A Maestro flow on an emulator or simulator. Android's emulator needs hardware acceleration, which a cloud machine may lack; iOS simulators need macOS (reported) | Screenshots or a recording | A test never seen to fail on a broken build |

**Mobile comes last** in the order of work: no study of agent-built mobile code was found, and Rail's first
target, a cloud session, runs Linux (reported).

**The project's own run skill.** When `rail-verify` finishes, it also writes a project skill that says how to
start, seed, stop and drive each surface, generated from `[product]` and `[[surfaces]]`, so a session with no
ticket uses the same procedure. Claude Code's built-in `run` skill says it "first looks for a project skill that
already covers launching the app" (confirmed: its description in a session's skill list, 2026-11-25). The
skill's file name is Decision 5. The config stays the source and the skill is generated from it: the engine
reads the config, not the skill, so the two can't disagree in what the engine does, and `rail-verify` writes
the skill again whenever it changes `[product]` or `[[surfaces]]`. A project skill named like a built-in one may
shadow it, and whether Claude Code has a built-in `/verify` skill was not checked, so the name waits on the
pilot.

## Part 5: an agent-facing surface

Agents are a growing share of the users of software: agents make about 70% of Stripe CLI requests and
Salesforce served 4.5 million MCP calls in six weeks (reported; both vendor numbers).

- **`rail init` asks** what the product's agent-facing surface is: a CLI, an API, an MCP server, markdown docs.
  When there is one, it is a surface of kind `agent` with its driving check.
- **The grill** (`engine/docs/grill.md`) gains one line in "Draft first": when the project has an `agent`
  surface and the request adds behaviour users get, the draft says whether the behaviour is exposed there, and
  if so a `Check:` line drives it. This changes the contract, so it passes the grill's own test for a question
  (`rail docs grill`, "Ask only what changes the contract", confirmed).
- **Rail asks; it doesn't build one.** Whether the product should have an agent-facing surface is the project's
  decision, made where its tickets come from (decided by the owner, 2026-11-25).

## Part 6: local first, a preview when needed

A cloud session already has `localhost`, and GitHub's cloud agent limits its browser to `localhost` by default
(reported). Most driving checks run there. A hosted preview is needed only for what `localhost` can't give:
OAuth redirects, webhooks from third parties, data shared with another service, a reviewer outside the session.

**A preview is commands the project names.** The platform stays the project's choice; Rail ships no adapter.

```toml
[preview]                                 # reader: ship (Part 3), cleanup after merge or drop, rail doctor
create = ""                               # prints {"id": ..., "url": ...} as JSON; RAIL_TICKET is set
wait = ""                                 # exits 0 once the preview answers; RAIL_PREVIEW_ID is set
seed = ""                                 # loads test data from files in the repository, never from production
destroy = ""                              # removes the preview; must succeed when it is already gone
list = ""                                 # optional: prints the open previews' ids as JSON
max_open = 5                              # previews open at once; a ticket over it rests until one is destroyed
tool = ""                                 # the [tools.NAME] whose token the commands use (rail docs tools)
```

The hosts the research compared document a command or action output that gives the URL as JSON or on stdout
(Netlify `deploy --json`, `vercel deploy`, the Fly action's outputs, Neon's action's `db_url`; reported, from
vendor docs). Cloudflare is left out of that list: the research cites `wrangler preview --json` for Wrangler
4.135.0 or later, but the current Wrangler gives preview URLs through `wrangler versions upload`, and which is
right was not checked.

**The engine creates it** at the first ship of a patch that needs it, records a `preview` event (`id`, `url`,
`created`) with the step events, and reuses it for later patches of the same ticket, running `seed` again.

**Where the commands run.** `create`, `wait` and `seed` run where the product step runs: in the worker's session
at ship, and in pull-request CI when Decision 1 keeps the step there (CI then reuses the ticket's preview by the
id in its journal, and creates one only when none is open). `destroy` and `list` run in the session that runs
`cleanup()` or `rail next`, never in pull-request CI. Each of these places runs the ticket branch's own code, so
nothing they hold may be a production secret or production data: the token follows the rule below, and `seed`
loads only files in the repository, with test identities and test values, never a dump or a copy of production.

**The engine owns teardown, because that is where hosts leak.** Neon branches made through its API and CLI and
Render previews never expire by default; Cloudflare leaves container apps behind; Supabase branches sit outside
its spend cap (reported, from vendor docs).

- At merge or drop: `cleanup()` already removes a merged or dropped ticket's worktree and branch
  (`engine/rail/cli.py`, `engine/rail/steps.py`, confirmed). It also runs `destroy` for the ticket's preview,
  whose id is in the ticket's journal, which merges with the code (`rail docs journal`). `rail drop` runs it
  directly, since a dropped ticket's journal goes with its branch.
- No journal event is written for a destroy. The engine commits the journal only on the ticket's branch; after a
  merge that branch is gone and the journal is on the base branch, where only a merge may write, since the guard
  denies a push to the base branch (`rail docs guards`). After a drop the branch is deleted. The local cache
  notes the destroy, and `destroy` must succeed on a preview already gone, so a second machine running it
  again does no harm.
- With `list`, `rail next` reconciles once per hour: any preview whose ticket is merged, dropped or unknown is
  destroyed. Without `list`, `rail doctor` lists the `preview` events of merged and dropped tickets the cache
  hasn't seen destroyed.

**Access is a grant.** The preview token is a `[tools.NAME]` declaration (`rail docs tools`) scoped to one
project: a person grants it once. The machine still holds no production deploy token (`rail docs
environments`). The token is reachable from a ticket branch: the worker's session holds it, and when the
product step runs in CI the tool is marked `ci = true` and reaches pull-request CI, which runs the branch's own
code. So it must be one whose exposure a rotation undoes and that costs nothing meanwhile, which is what
`ci = true` states: a token that can create and delete previews and nothing else. A host that offers only a
wider token (Fly needs an org-scoped token to create apps, reported) is a wider grant, and `rail doctor` says
so. The grant bounds the spend; `max_open` and teardown keep it bounded. Copying production data into a preview
is `data-exposure`, a kind that can't be undone (`rail docs kinds`), so a `seed` or `create` that branches
production data is a PERSON choice.

**`environments.md` gets a Preview row** between Local and Dev: "Per ticket, when a surface needs it: the
project's `create`, `wait` and `seed` at ship, `destroy` at merge or drop. The machine holds a token scoped to
previews." Today Rail does nothing at runtime outside Local and the machine (`rail docs environments`,
confirmed), so the page names this as the one exception.

## Docs and files that change

- `engine/rail/config.py` (`DEFAULTS`, a check for `[[surfaces]]`), `engine/rail/docs.py` (`rail docs config`),
  `seed/config.toml`: `[product]`, `[[surfaces]]`, `[preview]`.
- `engine/rail/steps.py`: the `product` step in `CHECKS` and `check()`, the red-base rule for `start`,
  `NN-evidence.json`, the Evidence rows. `engine/rail/cli.py`: teardown in `cleanup()` and `rail drop`, the
  hourly reconcile. `engine/rail/review.py`: the evidence in the reviewer's brief.
- `engine/rail/doctor.py`: the bar's lines with `kind`, `--product`. `engine/rail/init.py`: both init briefs
  ask for `[product]`, the surfaces, the agent-facing surface, and a ticket per missing piece.
  `engine/rail/sweep.py`: a ticket for a new `ticket` line.
- `engine/docs/journal.md` (`NN-evidence.json`, the `preview` event, the `product` step),
  `engine/docs/environments.md` (the Preview row), `engine/docs/grill.md` (the agent-facing line),
  `engine/docs/stats.md`, `engine/docs/loop.md` (the product step), a new `engine/docs/product.md`.
- `seed/rail.yml`: upload `$RAIL_EVIDENCE` as an artifact.
- `seed/skills/rail-verify/SKILL.md`: the recipes, the non-code examples removed, the project skill.

## Tests, each before its part is kept

1. **Gate cases, no model.** A fixture product in `tests/`: a small HTTP server and a CLI written with Python's
   standard library, each with a driving check script and a planted-fault switch.
   - Config: `[product]`, `[[surfaces]]` and `[preview]` load; an unknown kind or key is refused.
   - A ticket that changes a surface's paths runs `start`, `ready`, `seed`, that surface's check and `stop`;
     one that changes no surface path runs none; `stop` runs after a failed check.
   - With the planted fault on, the product step fails and counts against the retry budget; with it off, it
     passes. The same in `rail ci`.
   - `ready` that never exits 0 on the branch but does on the base fails the ticket; one that fails on both
     costs no attempt and gives the red-base answer.
   - Evidence: text lands in `NN-evidence.json`, cut at its caps; a value of a declared environment name and
     of a `.env` entry is replaced by its name; a binary file is never committed; the Evidence table has the
     surface's row; the reviewer's brief holds the text.
   - Preview, with fake commands that write to a log: `create` once per ticket, its URL in `RAIL_URL`, `seed` on
     each patch; `destroy` at merge, at `rail drop`, and for a pull request closed by hand; `destroy` twice
     passes; with `list`, an orphan is destroyed; over `max_open`, the ticket rests.
   - `rail doctor` names each missing bar piece with its kind; a `mobile` Android surface on a machine without
     `/dev/kvm` gives a `grant` line; `--product` runs each command once on the base.
   - The init briefs ask for the product, the surfaces and the agent-facing surface.
   Kept when every case behaves as written.
2. **`rail-verify`'s recipes, with a model.** For each of web, API, CLI, agent-facing and data job, a fixture
   project with no driving check, and a hidden fault the recipe's check should catch. Four runs per surface with
   the new skill and four with today's. Kept when the new skill's check catches the hidden fault in at least 3 of
   4 runs per surface, its negative control was run in at least 3 of 4 (seen in the transcript), and it does no
   worse than today's on any surface. This uses models: the recipes are built and their wording is marked
   untested until the owner restarts the paused model tests.
3. **In use, from the journals.** Over the first 50 tickets per surface: the count of driving-check failures on
   patches where `verify` and every `Check:` line passed. If a surface's step caught nothing in 50 tickets and
   its tickets show no revert or `caused_by` either, its recipe is revisited; the step is not removed on that
   alone, since a quiet surface may simply be healthy.

Not covered: iOS in a Linux cloud session; Kubernetes-based previews (the research sees them worth it only for
projects already on Kubernetes); performance and load; visual design judgment; whether the product step lowers
reverts, which needs outcome lines over months.

## Assumed, not verified

- That a GitHub Actions workflow artifact is reachable from the pull request for the length of a review
  (artifacts expire under the repository's retention setting).
- That a cloud session can start the product's dependencies (a database, a browser) with `provision`. The
  machine is the session's to change (`engine/rail/init.py`), but a service that needs Docker may not run there.
- That `/dev/kvm` is a fair test for Android emulator acceleration on Linux (inferred).
- The Inspector CLI's flags and exit codes: its docs page is under `/docs/draft/` (reported).
- That the built-in `run` skill finds a project skill by its description, not only by its name.
- That 64 KB per file and 256 KB per surface keep the journal small enough; the in-use numbers set them.
- That replacing declared values catches the secrets evidence can hold. A secret the project never declared is
  not caught; the project's secret scan in `verify` runs over the branch's commits, journal included (inferred:
  it scans `$RAIL_BASE..HEAD`, per `engine/rail/init.py`).

## Left out

- **A browser layer of Rail's own.** Playwright, Chrome DevTools MCP and Maestro exist, and measured token costs
  of the MCP and CLI forms differ by about 5% on current versions (reported); recipes name them.
- **Stacks, app templates or integrations for one platform.** The repository decides more than the model, and
  the shelf changes yearly (reported); `[product]` and `[preview]` are commands the project names.
- **Generative UI as a default.** No evidence in the research that it is near-term for the software Rail serves.
- **Payments between agents as a default.** The same; a project that takes payments uses an `integration`
  surface with the provider's test mode.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. `[product]`, `[[surfaces]]`, the `product` step with its red-base rule, `NN-evidence.json`, the Evidence rows,
   the reviewer's brief, the artifact upload; gate cases. The `[tools.NAME]` `env` names for the secret
   replacement in evidence exist already; the base-version rule for driving-check scripts is
   `proposals/checks.md` Part 1.
2. The bar in `rail doctor` with kinds, `--product`, the init briefs, the sweep's tickets.
3. `rail-verify`: recipes for web, API, CLI, data job and integration; the non-code examples out; the project
   skill. Its wording stays marked untested until test 2 runs.
4. `[preview]` with teardown and `list`; the Preview row in `environments.md`.
5. The agent-facing surface: the init question, the grill line, the recipe.
6. Mobile, last.

## Decisions

**Made by the owner (2026-11-25):** Rail is for software development; non-code work is for its own people.
Python, TypeScript, Rust and Go first, so the per-language recipes are `rail docs languages`'s. One attempt per
ticket. Review before merge stays. **Made by the owner (2026-11-26):** secrets reach pull request CI only as
`ci = true` keys (built); the benchmark and `rail replay` are set aside for now; a step that needs model runs
builds its deterministic part and marks its wording untested.

**Open:**

1. Whether the product step runs in CI as well as at ship. Proposed: yes; it is in `check()`, which both run,
   and `provision` installs what it needs on the runner.
2. Where binary evidence lives. Proposed: a workflow artifact in CI and the local cache on a session's
   machine; never the repository.
3. `[preview] list`: optional (proposed) or required.
4. The agent-facing eval: a recorded score (proposed) or a gate. It runs a model, so its result varies between
   runs.
5. The project skill's name: one that Claude Code's `run` skill finds, without shadowing a built-in skill.
   Proposed: `run-product`, checked in the pilot.
6. `max_open = 5` as the default.
7. **Short-lived apps** (Gartner's "disposable applications"): a ticket type with a retire-by date.
   Proposed: no. Rail is for code with a future, and a project that wants one can drop the app with a ticket.

## Sources

Rail, confirmed: `engine/rail/steps.py`, `cli.py`, `config.py`, `doctor.py`, `init.py`, `project.py`;
`engine/docs/journal.md`, `environments.md`, `guides.md`, `grill.md`, `tickets.md`, `tools.md`; `seed/config.toml`;
`seed/skills/rail-verify/SKILL.md`.

Research, reported: TestSuiteBench; the Waterloo seminar abstract on agent-driven testing; ArrivalBench, arXiv
2610.02363; agent-facing traffic figures (Stripe, Salesforce) and Gartner's "disposable applications"; vendor
documentation for preview hosts and teardown, database branching, seeding, driving tools per surface, mobile
limits; Anthropic, "Effective harnesses for long-running agents"; Vibe Code Bench (Tran et al., 2026).
