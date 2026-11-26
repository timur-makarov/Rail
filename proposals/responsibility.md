# A person for what can't be undone: what is left to build

This page is a proposal: what remains of a larger one. The larger one made one rule decide when a person is in
Rail's path: a person bears responsibility for what can't be undone, and for nothing else. Its built parts are in
the engine and its docs, and are no longer described here: the list of kinds a revert doesn't undo, `[kinds]`,
`person_reason` and its lint, and the kinds recorded on `accepted` and `tier_raised` (`rail docs kinds`); size
raising no tier, with only a split offered (`rail docs loop`); the reviewer's `kinds` field in place of
`needs_person` (`rail docs review`); an AUTO ticket at the retry cap dropped with a record (`STUCK`), the drop
mark written before anything is removed (`DROP_PENDING`), the refuter's verdict standing on AUTO, and
`AFTER_DROPPED` decided by the agent on AUTO (`rail docs retries`); the waits' kinds `approval`, `grant` and
`hold` (`rail docs retries`); a chain of failed dev deploys ending with a comment and no second fix
(`rail docs environments`); and the lines in `rail stats` for AUTO tickets that held a kind, AUTO tickets over the
cap, dropped tickets, and the reasons by kind (`rail docs stats`). Nothing below is implemented, and nothing
below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

The owner's position (2026-11-25): "a person still bears the responsibility. Anything that can be undone does
not provoke any consideration about whether the change should be approved, reviewed or learnt about. Anything
that is not *is* the responsibility a person bears." The built parts make a person's approval depend on a kind.
Two things still ask a person to learn about a change that can be undone, and one thing the rule needs is
untested.

Today (confirmed, `engine/docs/github.md`): every pull request opens with `## Read these`, built from facts,
and an AUTO ticket whose list is not empty gets the label `rail:look` as it merges, so that
`is:pr is:merged label:rail:look` is what to read afterwards. Its rows include a declined finding, an amended
contract, markers and changed manifests, each of which can be undone. `proposals/oversight.md` Part 1 would add
a reviewer's `attention` field that feeds the same list.

## Part 1: no one is asked to learn about a change that can be undone

The rule says "no consideration" for an AUTO change: no approval, no review by a person, and no being told about
it. The built `rail:look` label and the AUTO rows of `## Read these` are the last places that ask for it. The
proposed change:

- **`rail:look` goes,** and with it the saved search for merged AUTO pull requests. An AUTO ticket holds nothing
  that can't be undone, so no person is asked to learn about it.
- **"Read these" serves PERSON tickets only, and lists only what can't be undone:** the hunks in files that
  matched a kind's paths, the reviewer's `kinds` items, the `person_reason`, and changed manifests when they add a
  dependency. Rows for declined findings, an amended contract, markers, other manifests and `.gitattributes` go:
  each can be undone. Flag rules stay only with a `kind` (`flag = "access"`). Changes to tests and `REVIEW.md`
  get no row.
- **The reviewer's `attention` field is not built** (`oversight.md` Part 1): the reviewer's `kinds` is its one
  route to a person, and `attention` would be a second one for a change that merges either way.
- **`rail stats --forge`** (`oversight.md` Part 2) keeps the PERSON-ticket lines and has no `rail:look` lines.

A person who wants to look at an AUTO change keeps `rail:hold`, the brake `rail:stop` and `rail:revert`: those
are the person's choice, never a step Rail asks for. This part is open (Decision 1), because the built list was
made for the opposite purpose: so that a person could look after an AUTO ticket merged.

## Part 2: the contract writer's tier and `person_reason`

Built: ticket lint fails a PERSON ticket whose `person_reason` has no known kind, and the `rail-blast-radius`
guide names the kinds. Not tested: whether the contract writer, given a request, picks the tier and kind the
rule needs. Wording is in the guide and the brief; no model run has checked it.

## Tests, each before its part is kept

1. **Gate cases, no model** (Part 1, once decided). A pull request of an AUTO ticket gets no `rail:look` label
   and its `## Read these` has no row for a declined finding, an amended contract, a marker or a manifest; a
   PERSON ticket's list has only the kind rows, its `person_reason`, and manifests that add a dependency; a
   flag rule without a `kind` raises no row. Kept when every case behaves as written.
2. **The contract writer, with a model.** Intake cases with and without a kind; four runs each at
   `[worker] contract`. Kept when the tier and `person_reason` match the case in at least 3 of 4 runs. This uses
   models, so it waits for the owner to restart the paused model tests.
3. **In use, from the journals.** Over 50 AUTO tickets merged: if any is counted under "AUTO tickets that held a
   kind" in `rail stats`, the kind's detection (paths, the reviewer's text, or the contract writer's guide) is
   revisited before anything else.

Not covered: whether the list of kinds is complete for every project (`rail init` asks per project); harm from a
change that can be undone but costs users while it is live (the dev smoke check and the revert are the defence);
secrets a ticket branch reaches, which `ci = true` keys bound and no tier can.

## Assumed, not verified

- That no person needs to learn about an AUTO change after it merges. The brake, the revert label and the
  stats lines are what is left to notice a mistake, and test 3 is where it would show.
- That dropping at the cap loses no work a person would want: the branch is deleted, and the closed pull
  request's commits and the drop mark remain. Whether a relabelled issue's new ticket should start from those
  commits is not designed here.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. The contract writer's test (test 2), when the owner restarts the model tests; fix the guide's wording by it.
2. After Decision 1: no `rail:look`, "Read these" for PERSON tickets and kinds only, `rail stats --forge` as
   `oversight.md` says with no `rail:look` lines, and `oversight.md` edited to match.

## Decisions

**Made by the owner (2026-11-25):**

- A person bears responsibility for what can't be undone, and only for that.
- Review before merge stays: the machine's review runs on every AUTO change.

**Open:**

1. Whether `rail:look` and the AUTO rows of "Read these" go (proposed), or stay as an optional aid for a person
   who chooses to look. If they go, `oversight.md`'s `attention` field and its Decision 2 go with them.

## Sources

Rail, confirmed: `engine/docs/github.md`, `kinds.md`, `review.md`, `retries.md`, `stats.md`,
`environments.md`; `engine/rail/table.py`, `cli.py`, `stats.py`; `seed/skills/rail-blast-radius/SKILL.md`;
`proposals/oversight.md`.
