# People after the fact: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and
are no longer described here: the kinds of change a revert doesn't undo (`rail docs kinds`), the brake
`rail:stop` and the label `rail:revert` (`rail docs cloud`, `rail docs tickets`), `## Read these` with its
review comments, flag rules and the label `rail:look` (`rail docs github`), the revert that goes first after a
failed deploy to dev (`rail docs environments`), and the count of a person's acts in `rail stats`. Nothing below is implemented, and nothing below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Part 1: the reviewer names lines worth a person's eye

`## Read these` is built from facts: the tier's reason, findings the machines decided against, an amended
contract, markers, flag rules, manifests. One source is missing, the reviewer's judgment about lines on a
change that merges either way.

A new optional field in `review/v1`, `attention`: up to three `{file, line, end_line, why}`. It is for lines a
person reading afterwards should not miss: a value chosen by judgment (a limit, a timeout, a threshold),
behaviour the tests can't show (timing, concurrency, an external service), a name others will depend on. Each
becomes a "Read these" item with the source "the reviewer".

**`attention` and the reviewer's kinds stay apart.** A kind the reviewer names says a person must see the
change before it merges, and on an AUTO ticket it raises the tier. `attention` raises nothing. If the owner
ends the reviewer's tier raise (Decision 1), its cases move to `attention`.

`engine/review-v1.json` refuses unknown keys at its top level today, so the field is a schema change, with
`engine/reviewer.md` and `engine/docs/review.md`.

## Part 2: measure the list

`rail stats --forge`. `rail stats` reads only the journals and the base branch's history, and line comments
live on GitHub; `--forge` also reads each merged ticket's pull request comments, and without it these lines
are left out. On PERSON tickets: the person's line comments per ticket (unmarked ones), and the share that
fall on an item. On tickets reverted afterwards: whether the reverted lines held an item. On AUTO tickets:
how many `rail:look` pull requests led to a revert or to a ticket that names them in `caused_by`.

## Tests, each before its part is kept

1. **Gate cases, no model.**
   - `rail stats --forge` reads line comments from a test repository; without `--forge` those lines are
     left out.
   Kept when every case behaves as written.
2. **The reviewer's `attention` field, with a model.** On changes with a planted line of the `attention`
   kinds (a limit chosen by judgment, a timeout, a retry count) that is no case for a person before the
   merge, and on plain controls, four runs each: kept when the planted line is among the items in at least 3
   of 4 runs per case, the controls get no item in at least 3 of 4, and no kind is named on the planted cases
   in at least 3 of 4. This uses models, so it waits for the owner to restart the paused model tests.
3. **In use, from the journals.** Over 20 PERSON tickets: when fewer than half the person's line comments fall
   on items, the sources are revisited. Over 20 `rail:look` pull requests: a source whose items never led to
   a revert, a ticket or a comment is removed from the list.

Not covered: how long a person takes per pull request (GitHub doesn't report reading time); whether a person
reads the items or the whole diff; forges other than GitHub.

## Built, and not yet tried on GitHub itself

These are in the engine and pass against the suite's stand-in for GitHub. Each rests on GitHub behaving as its
docs say, which nothing here checked:

- A review comment placed by file and line number (`line`, with `commit_id`), and a `COMMENT` review on a pull
  request the same account opened.
- A Claude Code cloud session being allowed the reviews endpoint, and opening and closing issues.
- The issues endpoint returning merged pull requests with a label when asked for closed items.
- GitHub folding a file marked `linguist-generated` in a pull request's diff.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. `rail stats --forge` (Part 2).
2. The reviewer's `attention` field, after its test (Part 1).

## Decisions

**Open:**

1. Whether the reviewer's request keeps making a ticket PERSON, once `rail stats` has 20 such tickets with
   "Read these" in place. Proposed: decide on those numbers. (Size raises no tier any more.)
2. The cap on the reviewer's `attention` items: three (proposed).

## Sources

Rail, confirmed: `engine/rail/state.py`, `steps.py`, `review.py`, `table.py`, `cli.py`, `stats.py`, `forge.py`,
`readthese.py`; `engine/reviewer.md`; `engine/review-v1.json`; `engine/docs/`.

GitHub's docs, confirmed: "REST API endpoints for pull request reviews"; "Customizing how changed files appear
on GitHub".

Reported: review framing, Mitropoulos et al., arXiv 2603.18740; "How to Build an AI Software Factory That
Ships Faster", Boundary's AI That Works, with Warp's founder, https://www.youtube.com/watch?v=XUEfIxkdT2Q
(transcript read 2026-11-25).
