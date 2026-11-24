# People after the fact: what could be built

This page is a proposal. None of it is implemented. It treats Rail as two systems: agents that carry
tickets to a merge and a dev deploy on their own (System 1), and people, with their own agents reading for
them, who check the work afterwards and stop it when needed (System 2). It says what would move Rail
further that way, and how a person's review could be pointed at the few lines that need a person. Status:
written 2026-11-25 from Rail's engine code and docs and GitHub's docs. Nothing here was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Where Rail stands

Rail is mostly System 1 already. An AUTO ticket is accepted, built, reviewed and merged with no person; the
project's CD deploys the base branch to dev; a dev smoke check that fails opens an issue that becomes a fix
ticket; releasing to prod is a person's act (`engine/docs/environments.md`, confirmed).

A person acts **before** the fact in two places:

- **PERSON tickets.** A person approves the contract and merges. A ticket is PERSON when its author says so,
  when its scope or changed files match `person_paths` or `migration_paths`, when it stays over `[size] cap`
  after a split offer, or when the reviewer asks for a person (`engine/rail/state.py:22-38`,
  `engine/rail/steps.py:238, 261`, `engine/rail/review.py:455`, confirmed).
- **Waits.** The retry budget or cap, an upheld finding, a stuck review, an amend that needs approval
  (`engine/docs/retries.md`, confirmed).

A person acts **after** the fact only through what GitHub offers: reading merged pull requests, reverting by
hand. `rail stats` counts reverts afterwards (`engine/docs/stats.md:62`, confirmed). Nothing points the
person at what to read, there is no way to stop all work at once (`rail:hold` stops one ticket,
`engine/rail/table.py:321`, confirmed), and a revert is not a Rail act.

The goal is the owner's: a person only on critical tickets; a needless PERSON ticket costs attention, and so
does a needless wait. Moving checks after the fact is how a person stays informed without being in the path.

## Part 1: a person before the fact only for what can't be undone

A merged change can be reverted, so most changes can be checked after they merge. A few acts can't be taken
back by a revert, and those stay before the fact:

| Kind | Why a revert doesn't undo it |
|---|---|
| Moving money, charging, refunding | The money has moved |
| Deleting data, and migrations | The data may be gone. A migration's `rollback` field is a claim nobody has run, so `migration_paths` stays PERSON |
| Credentials, secrets, authentication and permissions | Access granted meanwhile was usable; a leaked secret stays leaked |
| Messages to real people (email, notifications) | They were sent |
| Infrastructure that a change can delete or replace | The resource and its data are gone |
| Rail's own controls: `.rail/config.toml`, `.rail/engine/**`, `.claude/**`, CI workflows | A weakened gate lets other changes through before anyone looks |
| Releasing to prod | Already a person's act, outside Rail |

Changes:

1. **`rail init` asks about these kinds.** Today its brief asks for "the paths a person should see changed
   (auth, payments, infrastructure)" (`engine/rail/init.py:43` and `:74`, confirmed). It would name the kinds
   above, and only those, so `person_paths` holds what can't be undone. The seed's defaults are already the
   controls row.
2. **The other reasons are reviewed by their own numbers.** `rail stats` already reports, per reason a ticket
   was PERSON, how often the person changed nothing, and says a reason may stop making tickets PERSON at 95%
   or more over 20 tickets with no revert and no later `caused_by` (`engine/docs/stats.md:80, 91`,
   confirmed). Size and the reviewer's request are the two reasons that aren't about what can be undone; with
   Part 3 and Part 5 a person can see those changes after the merge. Whether either stops making a ticket
   PERSON stays the owner's decision on those numbers (Decision 1).

## Part 2: one brake for the repository

An open issue labelled `rail:stop` stops System 1. The engine reads it with its own REST call each
`rail next`, `rail advance` and `rail work`: open issues with that label. (The intake's call can't serve: it
lists open issues labelled `rail` and drops pull requests, `engine/rail/forge.py:324-326`, confirmed.)

A stopped ticket matches a new first-match row, `STOPPED`, above every agent row: owner `human`, action
`human_wait`, the issue's link and title as the reason. The engine doesn't label the pull request
`rail:needs-you`: the person set the brake and knows. While the brake is open:

- `rail next` answers `STOPPED` for every ticket, `--ticket NN` included, and claims nothing.
- `rail advance` and `rail work` answer `STOPPED` and do nothing, so a runner that loops on one ticket stops
  at its next call. A worker run already going finishes; its changes are saved and wait.
- `rail status` shows an open brake first.

An issue whose body has a `paths:` line (globs, as in `person_paths`) stops only tickets whose scope overlaps
those paths. Closing the issue, or removing the label, lifts the brake; the next run, at the latest the
runner's schedule, carries on (closing an issue starts no runner run, `engine/docs/cloud.md` triggers,
confirmed). A merge GitHub already accepted before the brake was set may still land (inferred: the engine
merges through GitHub's async merge, `engine/docs/github.md`). With no remote there is no brake: the person
is at the terminal.

Two things go on under any brake, so that a brake can't block its own way out: intake of an issue that
starts with `Commit: <sha>` (a failed dev deploy, Part 4), and revert tickets (Part 3).

## Part 3: acts after the fact

### A revert is a Rail act

The label `rail:revert` on a merged pull request makes the next `rail next` file a revert ticket. The engine
finds such pull requests with a REST call for closed issues and pull requests with that label (inferred: the
issues endpoint lists pull requests when they aren't filtered out).

- **Its change** is the reverse of the reverted ticket's squash commit on product paths only, leaving
  `.rail/tickets` and `.rail/journal` alone (`PRODUCT_SPEC`, `engine/rail/project.py:15-16`, confirmed). A
  whole `git revert` would delete another ticket's file and journal, which the scope step and the guard both
  refuse (`project.py:218-222`, `engine/docs/guards.md`, confirmed).
- **Its contract** is built in: `kind = "revert"`, `reverts = "NN"`, `caused_by = "NN"`, scope the reverted
  ticket's changed product files. Instead of `Check:` lines, ship checks that the change is the reverse of
  NN's product diff (`git apply -R --check` of that diff on the base, then a compare), and `verify` runs as
  always. `base_checks` is skipped. Ticket lint accepts a revert ticket with no `Check:` line.
- **When the reverse doesn't apply** (later tickets changed the same lines), the engine files it with a
  `REVERT` brief instead: undo ticket NN's change by hand, keep later work, and ship. The built-in check is
  then skipped, and the reviewer reads the change as usual.
- **Its `## Why`** holds the comments of people who can push on the reverted pull request, with the same
  filter the briefs use (`person_comments`, `engine/rail/cli.py:262-277`, confirmed).
- **Its tier** follows its paths like any ticket, so reverting a change on `person_paths` waits for the
  person's merge. The label counts as the person's approval of the contract.
- **Its squash commit** carries a `Reverts: <sha>` trailer, and `rail stats` reads that trailer as a revert
  beside git's and GitHub's wordings, which a Rail squash message has neither of (`engine/rail/stats.py:42-60`,
  confirmed).
- The engine removes the label once the ticket is filed, so one label files one ticket.

### A list of what to look at

An AUTO ticket whose "Read these" list (Part 5) is not empty gets the label `rail:look` in the same call that
asks GitHub to merge it, so the label is set once and nothing needs to be recorded after the merge (the
journal can't be written then, `engine/docs/journal.md`, confirmed). A person, or the person's own agent
reading on their behalf, works the saved search `is:pr is:merged label:rail:look` and removes the label when
done, as the inbox `label:rail:needs-you` works for waits (`engine/docs/cloud.md`, confirmed). A PERSON
ticket gets no such label: its person reads the list before the merge. A person who finds a problem uses
`rail:revert`, or files a ticket.

`rail init` creates the three labels `rail:stop`, `rail:revert` and `rail:look` beside the four it makes
today (`engine/docs/github.md`, `engine/rail/forge.py` `LABELS`, confirmed), and `rail doctor` checks them.

## Part 4: the agents stop themselves

1. **A failed dev deploy reverts first.** Today a failed smoke check opens an issue with `Commit: <sha>`, and
   `rail intake github` turns it into a fix ticket whose `caused_by` is the ticket that commit merged
   (`engine/docs/environments.md:9`, confirmed). Proposed: the intake files two tickets from the issue, each
   with its own `external_id` (`github#N:revert` and `github#N`, since intake skips a second ticket with the
   same one, `engine/rail/cli.py:596-598`, confirmed):
   - a revert ticket for the ticket that commit merged (Part 3), and a `rail:stop` issue with `paths:` set to
     that ticket's scope; the engine closes the stop when the revert merges, and the revert goes on under it
     (Part 2);
   - the fix ticket, `after` the revert, which redoes the work with the fix and closes the issue. The revert's
     pull request says `Part of #N`, so it doesn't close the issue.
   Decision 2 is whether to revert first or fix forward as today.
2. **Fix chains end.** A smoke fix ticket is one filed from an issue that starts with `Commit:`; its
   `requested` event says so (`smoke: true`). A smoke fix ticket whose `caused_by` ticket was itself a smoke
   fix ticket waits for a person before its contract is accepted, with the chain in the brief. Today nothing
   limits the chain: `caused_by` is only counted (`engine/rail/stats.py:143`, confirmed).
3. **Spending stops work.** With the worker proposal, `[worker] daily_usd` rests `rail next` and `ticket_usd`
   makes a ticket wait (`proposals/worker.md`). Both are stops for a runaway, not reviews.

## Part 5: point the person at the lines that need a person

Today the pull request opens with `## Why`, from the ticket, then `## Look at`, written by the worker before
it ships (`engine/rail/table.py:108`, `engine/rail/steps.py:407-411`, confirmed). `## Look at` is the author's
framing: research on review found an author's framing lowers a reviewer's detection by 16 to 93 points
(reported, arXiv 2603.18740). It stays, below a new list the engine builds from facts.

**"Read these" lists, for each item, the lines and why:**

| Source | Lines | Why a person |
|---|---|---|
| The tier's reason | The hunks in files that matched `person_paths` or `migration_paths`; for `size`, the whole change; for the author's tier, the ticket's `## Why` | This is why the person is there |
| The reviewer | A new optional field in `review/v1`, `attention`: up to three `{file, line, end_line, why}` | The reviewer's judgment, kept apart from findings |
| Findings a person may disagree with | Each declined advisory finding, and each blocking finding the refuter dismissed, at its location | The machine decided against a finding |
| A contract changed with no person | The Done Contract as first accepted, against the one merged, when an AUTO amend changed it (`engine/docs/review.md`, confirmed) | The bar moved |
| Markers | Each added `SHORTCUT(NN)`; with the entropy proposal, `SENSOR(NN)` and `TODO(NN)` | A corner cut on purpose |
| What the change can now do | Changed manifests and lockfiles (the Risk section lists lockfiles today, `steps.py:400-404`, confirmed), a changed `.gitattributes`, and added lines that match a flag rule (below) | New reach, or a file hidden from the diff |

**`attention` and `needs_person` stay apart.** The reviewer sets `needs_person` when a person must see the
change before it merges: the first of something other code will copy, a new dependency, a change users get
beyond the ticket (`engine/reviewer.md:31-38`, confirmed); on an AUTO ticket it raises the tier
(`review.py:450-456`, confirmed), and its sentence is the first item of the list. `attention` is for lines on
a change that merges either way, which a person reading afterwards should not miss: a value chosen by
judgment (a limit, a timeout, a threshold), behaviour the tests can't show (timing, concurrency, an external
service), a name or format others will depend on. If Decision 1 ends the reviewer's tier raise, its cases move
to `attention`.

**Flag rules.** A `[[rules]]` entry gains `flag = true`: it matches text on added lines as any structure rule
does (`engine/docs/rules.md`, confirmed), but adds a "Read these" item instead of failing the ship. A project
writes them for its own kinds of reach, such as reading an environment variable, an outbound URL, or a new
route. The seed ships none: what marks new reach is language- and project-specific.

**Line numbers.** Every item except a missing thing needs the added lines' numbers. `rules.added` returns
their text only (`engine/rail/rules.py:22-36`, confirmed). The entropy proposal builds hunk-line parsing for
its sensors (`proposals/entropy.md`, Part 1 item 2); "Read these" uses the same parser, and whichever lands
first builds it.

**When the list is built.** The reviewer's items and the answered findings exist only after review, so the
list is built when the ticket reaches `merge-ready`, or a person's merge wait, and again if a later patch
brings it back there. It is keyed by `patch_id`, so a clean rebase, which keeps the patch id
(`engine/docs/journal.md`, confirmed), doesn't rebuild it.

**How it reaches the person:**

1. **The pull request opens with `## Read these`**, before `## Why`: one line per item, `path:lines`, the
   reason, and the source. Its last line counts the rest: "N other changed lines: checked by verify, M
   checks and the reviewer." When the list is empty, the section says "Nothing needs a person's eye"; on a
   PERSON ticket the tier's reason is always on it.
2. **The same items as review comments on their lines.** The engine posts one review with the event
   `COMMENT`, one comment per item that sits on a changed line, through
   `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` (confirmed on GitHub's docs). Each comment
   carries the engine's mark, as its other comments do (`ENGINE_MARK`, `engine/rail/forge.py:23`, confirmed), so the
   engine skips an item it already posted at the same path and line, and nothing reads its own comments as a
   person's. Items about something missing stay in the body only.
3. **A person's line comments reach the agent.** Today a person's note during a wait comes from the pull
   request's conversation comments only (`person_comments`, confirmed). It would also read line comments
   (`pulls/N/comments`), with the same filter, so a person who answers an item on its line is heard.
4. **Generated files collapse.** `rail init` writes the `[size] exclude` globs into `.gitattributes` with
   `linguist-generated`, which GitHub hides by default in diffs (confirmed on GitHub's docs). Lockfiles stay
   visible, since they are on the list. The size check already skips `linguist-generated` files
   (`engine/rail/rules.py`, confirmed), which is why a changed `.gitattributes` is an item: a ticket that marks
   its own files generated hides them from the diff and from the cap.

**`rail stats` measures it.** On PERSON tickets: of the person's line comments (the unmarked ones), the share
that fall on an item. On tickets reverted afterwards: whether the reverted lines held an item. On AUTO
tickets: how many `rail:look` pull requests led to a revert or to a ticket that names them in `caused_by`.

## Docs and files that change

- `engine/docs/github.md`, `engine/rail/forge.py` `LABELS`, and `rail doctor`: the three labels.
- `engine/docs/loop.md` (reason codes), `engine/docs/states.md`, `engine/docs/retries.md`: `STOPPED`,
  `REVERT`, and the smoke chain's wait.
- `engine/docs/environments.md`: a failed smoke check reverts first. `engine/docs/cloud.md`: where a person's
  acts go (`rail:stop`, `rail:revert`, the `rail:look` search), and that closing a stop issue starts no run.
- `engine/docs/tickets.md` and ticket lint: the revert ticket's fields. `engine/docs/journal.md`: the
  `requested` event's `smoke`, and the `Reverts:` trailer. `engine/docs/stats.md`: the new lines.
- `engine/review-v1.json` (its top level refuses unknown keys today), `engine/reviewer.md`,
  `engine/docs/review.md`: the `attention` field.
- `engine/rail/config.py` (`RULE_KEYS`) and `engine/docs/rules.md`: `flag = true`.
- `engine/rail/init.py` (both briefs): the kinds that can't be undone, and `.gitattributes`.

## Tests, each before its part is kept

1. **Gate cases, no model.**
   - The brake: an open `rail:stop` gives `STOPPED` from `next`, `next --ticket`, `advance` and `work`; a
     runner looping on one ticket stops at its next call; a `paths:` stop leaves other tickets alone; closing
     lifts it; a `Commit:` issue and a revert ticket go on under it.
   - The revert: `rail:revert` files one ticket, removes the label, leaves `.rail/` alone, passes scope and
     lint at its first ship, follows its paths' tier, and its squash carries `Reverts:`, which `rail stats`
     counts; a revert that doesn't apply gets the `REVERT` brief.
   - The smoke issue: two tickets with their own ids, a scoped stop closed when the revert merges, the issue
     closed by the fix; a smoke fix two deep waits.
   - "Read these": each source produces its item on a fixture ticket; the body section is written at
     `merge-ready` and not rebuilt on a clean rebase; the review is posted to a test repository with its
     comments on the right lines, and not posted twice; a flag rule adds an item and fails nothing; a changed
     `.gitattributes` is an item; a person's line comment reaches the next brief; `rail:look` is set on an
     AUTO merge with items and on no other.
   - `rail init`'s briefs name the kinds that can't be undone.
   Kept when every case behaves as written.
2. **The reviewer's `attention` field, with a model.** On changes with a planted line of the `attention`
   kinds (a limit chosen by judgment, a timeout, a format others will read) that is no `needs_person` case,
   and on plain controls, four runs each: kept when the planted line is among the items in at least 3 of 4
   runs per case, the controls get no item in at least 3 of 4, and `needs_person` is not set on the planted
   cases in at least 3 of 4. This uses models, so it waits for the owner to restart the paused model tests.
3. **In use, from the journals.** Over 20 PERSON tickets: when fewer than half the person's line comments fall
   on items, the sources are revisited. Over 20 `rail:look` pull requests: a source whose items never led to
   a revert, a ticket or a comment is removed from the list.

Not covered: how long a person takes per pull request (GitHub doesn't report reading time); whether a person
reads the items or the whole diff; forges other than GitHub.

## Assumed, not verified

- That a review comment can be placed by file and line number. GitHub's docs describe placing it by its
  `position` in the diff; the `line` and `side` parameters were not read (the page was cut). Counting
  `position` from the diff is the fallback.
- That GitHub accepts a `COMMENT` review on a pull request the same account opened (approving one's own is
  refused; commenting is assumed allowed).
- That a Claude Code cloud session allows the reviews endpoint and closing issues. Rail's list of what the
  cloud refuses (`engine/docs/cloud.md`) doesn't name them, and Rail uses REST for everything else there.
- That the issues endpoint returns merged pull requests with a label when asked for closed items.
- That the reviewer can keep `attention` to the few lines that matter: the cap of three is a guess the test
  checks.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. The hunk-line parser, if the entropy proposal's first step hasn't built it.
2. "Read these": the body section and the sources that need no model (tier reason, findings, amend,
   markers, manifests, `.gitattributes`), flag rules, the review comments, line comments into the note,
   `.gitattributes` from `rail init`.
3. The brake: `rail:stop`, with and without `paths:`.
4. `rail:revert` and `rail:look`.
5. The smoke-check revert and the fix-chain limit, after Decision 2.
6. The reviewer's `attention` field, after its test.
7. `rail init`'s question about the kinds that can't be undone.

## Decisions

**Open:**

1. Whether size and the reviewer's request keep making a ticket PERSON, once `rail stats` has 20 tickets of
   each with "Read these" in place. Proposed: decide on those numbers.
2. On a failed dev deploy: revert first (proposed), or fix forward as today.
3. The cap on the reviewer's `attention` items: three (proposed).
