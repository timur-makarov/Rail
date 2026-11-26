# What projects learn reaches Rail, and back: what is left to build

This page is a proposal: what remains of a larger one, "Rail improves Rail". Its built parts are in the engine and
its docs, and are no longer described here: the OUTCOMES block that `rail stats` leads with (merged, reverted
afterwards, caused a fix ticket, held after `[stats] held_days`, cost per merged ticket, a person's acts) with
its splits by worker model and by language profile, and the line for how many merged tickets name their cause
(`rail docs stats`); the `worked` event that records the model (`rail docs journal`); the kinds of change,
`external-effect` among them (`rail docs kinds`). `rail init` also writes the framework's URL and commit into
`.rail/SOURCE`, which no doc page describes. Nothing below is implemented, and nothing below was
run.

Decided by the owner (2026-11-26): Rail is developed without Rail, not run on its own repository, because Rail
changes too fast for that. So the parts of the larger proposal that gave the Rail repository its own `.rail/`,
CI, `REVIEW.md` and `EVIDENCE.md`, and the weekly watch of the platforms there, are removed. The benchmark and
`rail replay` are set aside for now. Steps that need model runs build their deterministic part, and their
wording is marked untested.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

The owner's position (2026-11-25): Rail should improve Rail, with a person approving each change to it. A second
position: one attempt per ticket for now.

A project owns its copy of the engine after `rail init`: `.rail/SOURCE` records the framework's URL and commit,
and `.rail/engine/**` is in `person_paths` (`engine/rail/init.py`, `seed/config.toml`, confirmed). Nothing carries
a project's fix to its engine back to Rail, and nothing tells a project what changed in Rail since its copy.
Today a person asks an agent to "clone the repo and see what we can integrate" (owner, 2026-11-09).

## Part 1: what projects learn reaches Rail, and back

**Upstream: a project's fix to its engine.**

- A seed source, `.rail/sources/rail-upstream.md`, that `rail init` copies and nothing schedules until a person
  does. Its `fetch` lists the merged commits since its last run that changed the files `rail init` copied from
  the framework (`engine/rail/init.py`, confirmed): `.rail/engine/**`, `.rail/bin/**`, `.rail/packs/**`,
  `.rail/ruleset.json`, `.rail/tickets/TEMPLATE.md`, `.rail/sources/weekly-review.md` and the two sources below,
  `.claude/skills/rail-*/**` and `.github/workflows/rail.yml`; each with its `Ticket:` trailer, its ticket's
  `## Why`, and the diff of those files only; and the counts from `rail stats --json`.
- Its prompt: a change that would help any project running Rail (a bug in the engine, a brief that misled, a
  missing guard) is drafted as an issue for the framework repository named in `.rail/SOURCE`; a change that is
  this project's own setting is not. The draft holds the diff of Rail's files, the reason, and the stats lines that
  show its effect; never code outside Rail's files, and never a value from an environment variable.
- **A person sends it.** An issue on another repository is text published outside the repository, the
  `external-effect` kind, which can't be undone (`rail docs kinds`). The source opens the draft as an issue in the
  project's own repository with the label `rail:upstream`, which intake doesn't read (intake reads `rail`,
  `engine/rail/forge.py`, confirmed). A person who adds `rail:go` to it approves the text; the next run of the
  source opens it on the framework's repository with a grant for that, links it, and closes the draft.
- On the framework's side the issue is labelled `rail` and becomes a request: its author can't push there, so it
  is never taken as a whole ticket (`engine/rail/cli.py`, confirmed).

**Downstream: what changed in Rail since a project's copy.**

- A seed source, `.rail/sources/rail-framework.md`, copied by `rail init` and scheduled by a person. Its `fetch`
  fetches the framework at the URL in `.rail/SOURCE` into a temporary folder and prints the `CHANGELOG.md` lines
  added since the commit in `.rail/SOURCE`, each with its commit.
- Its prompt files one ticket per change worth taking, `external_id = "rail-framework#SHA"`, with
  `tier = "PERSON"`: every such ticket changes Rail's own gates. The default `person_paths` covers only part of
  what init copies (`.rail/bin/**`, `.rail/engine/**`, `.rail/config.toml` and `.rail/sensors/**`; `.claude/**`
  and `.github/workflows/**` are PERSON under the kind `runs-with-secrets`; `seed/config.toml`, confirmed), so the
  seed's `person_paths` gain `.rail/packs/**` (a
  pack runs code, as consult runs a model), `.rail/sources/**` (a source's prompt files tickets),
  `.rail/ruleset.json` (the branch protection a person imports) and `.rail/tickets/TEMPLATE.md`; then the paths
  make the tier PERSON too, and the front matter is a second hold. Its work copies the changed files from that
  commit, keeps the project's own changes to them, and updates the commit in `.rail/SOURCE`.
- This replaces the person's prompt with a source and adds no verb; the owner's 2026-11-09 decision of no
  `upgrade` command holds.

## Part 2: more tickets name their cause, and a split by surface

1. **The contract brief gains one line.** `caused_by` is set today by intake for a deploy issue that starts with
   `Commit:` (`engine/rail/cli.py`, confirmed), by a revert ticket, and otherwise only when an agent writes it
   (the sweep's brief says to). The brief for a ticket's contract (`TICKET_LINT`, `engine/rail/table.py`) says
   nothing of it. It gains: when the request is a bug in code a merged ticket wrote, find that ticket (the squash
   commit of the failing lines, `git log -L` or `git blame`, and its `Ticket:` trailer) and set `caused_by`. The
   coverage line in `rail stats` already shows whether it works.
2. **A split by surface**, from the paths a ticket changed, beside `BY WORKER` and `BY LANGUAGE` in `rail stats`
   (same rule: a group under five tickets is summed into `other`). What a surface is, and the paths that mark
   one, are defined by `[[surfaces]]` in `proposals/product.md` Part 1, which is not built: this waits for it. Not verified: whether such a split
   shows anything the language split does not.

## Part 3: one line of work per ticket

Owner's position (2026-11-25): one attempt for now. **Defined here:** a ticket has one line of work at a time,
one worker carrying it from claim to merge; no parallel lines of work on the same ticket, and no best-of-N. This is
not the retry budget's "attempt", which is one ship counted toward `[retry] budget` and `cap`
(`rail docs journal`, "The retry budget"; `rail docs retries`); those are unchanged. The definition goes into
`engine/docs/retries.md`, which uses "attempt" for the retry budget only.

Several lines of work with the best one kept pays only when something can rank them. For most web, API and
command-line work every line of work that passes the checks looks the same to them; the differences are design and
readability, which only a reviewer judges, at the cost of a review per attempt and with its own false alarms
(inferred; reviewers' false alarms on correct changes ran 21-48% in one benchmark, reported).

**Left out:** best-of-N in the loop. The narrow cases where it might pay, named so they are recognised: a bug
that lines of work fail in different ways; performance work with a benchmark that ranks them; a rewrite with an
old-against-new check that ranks them. Running a ticket again to see whether passing lines of work differ in
whether they hold is `rail replay`, which is set aside for now.

## Docs and files that change

- `seed/sources/rail-upstream.md` and `seed/sources/rail-framework.md` (new); `engine/rail/init.py` copies them;
  `engine/docs/sources.md`: the two sources, and that `rail-upstream` opens an issue elsewhere after a person's
  `rail:go`; `engine/rail/forge.py` `LABELS`: `rail:upstream`.
- `seed/config.toml`: `person_paths` gains `.rail/packs/**`, `.rail/sources/**`, `.rail/ruleset.json` and
  `.rail/tickets/TEMPLATE.md`.
- `engine/rail/table.py`: the `caused_by` line in the `TICKET_LINT` brief.
- `engine/rail/stats.py`, `engine/docs/stats.md`: the split by surface, when surfaces are defined.
- `engine/docs/retries.md`: the definition of a line of work.
- `README.md`: how a project takes Rail's changes (the source) instead of the prompt.

## Tests, each before its part is kept

1. **Gate cases, no model.**
   - `rail-upstream`'s `fetch` on a fixture history lists the commit that changed `.rail/engine/` and not one that
     changed only product code; its diff holds no file outside Rail's paths.
   - `rail-upstream`'s `fetch` lists a commit that changed only `.rail/packs/` or `.rail/ruleset.json`.
   - `rail-framework`'s `fetch` against a fixture framework repository prints the CHANGELOG lines after the
     recorded commit and none before it.
   - With the seed's `person_paths`, a ticket that changes only `.rail/packs/consult/` or `.rail/sources/` is
     PERSON at add.
   - A `rail:upstream` issue is not taken by intake; `rail:go` on it lets the next run of the source open it.
   Kept when every case behaves as written.
2. **Model tests, four runs each.** Built and run once model runs are available; until then the wording of the
   prompts is untested.
   - `rail-upstream` on two fixture histories, one with an engine fix and one with only a project setting changed
     in `.rail/config.toml`: kept when it drafts an issue for the first and none for the second in at least 3 of 4
     runs, and no draft holds a line from outside Rail's files.
   - `rail-framework` on a fixture changelog of three changes, one of which the project already has: kept when it
     files two tickets in at least 3 of 4 runs.
   - The `caused_by` line: on fixture bug requests where blame leads to a merged ticket, and controls where the
     bug predates Rail, kept when `caused_by` is right in at least 3 of 4 runs per case and empty on the controls.

Not covered: whether an upstream issue's text leaks something of the project that Rail's paths don't show (the
person's approval of the text is the check); how many projects will send anything.

## Assumed, not verified

- That a cloud session's GitHub access can open an issue on another repository. If not, it is a grant: an identity
  for the machine with access to the framework's repository (`proposals/scale.md` Part 6, not built).

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. The `caused_by` line in the `TICKET_LINT` brief, and the definition of a line of work in `retries.md`.
2. The seed's added `person_paths`, then `rail-framework`, then `rail-upstream`, each source after its model
   test. `rail-upstream` needs a grant to open an issue on the framework's repository.
3. The split by surface, once `proposals/product.md` Part 1 is built.

## Decisions

**Made by the owner:** Rail improves Rail with a person approving each change, and one attempt per ticket for now
(2026-11-25); Rail is not run on its own repository (2026-11-26).

**Open:**

1. `rail-upstream` as a source that opens an issue elsewhere after `rail:go` (proposed), or a verb. A source keeps
   the prompt editable, and it is the first source that acts outside `rail add`.

## Sources

Rail, confirmed: `engine/rail/stats.py`, `init.py`, `cli.py`, `forge.py`, `table.py`; `engine/docs/stats.md`,
`sources.md`, `journal.md`, `retries.md`, `kinds.md`; `seed/config.toml`; `seed/sources/weekly-review.md`;
`CHANGELOG.md`.

Reported: the reviewers' false-alarm range of 21-48% in one benchmark.
