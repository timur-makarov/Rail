# People after the fact: what is left to build

This page is a proposal: what remains of a larger one. Its built parts are in the engine and its docs, and
are no longer described here: the kinds of change a revert doesn't undo (`rail docs kinds`), the brake
`rail:stop` and the label `rail:revert` (`rail docs cloud`, `rail docs tickets`), `## Read these` with its
review comments, flag rules and the label `rail:look` (`rail docs github`), and the count of a person's acts
in `rail stats`. Nothing below is implemented, and nothing below was run.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Part 1: the agents stop themselves

1. **A failed dev deploy reverts first.** Today a failed smoke check opens an issue with `Commit: <sha>`, and
   `rail intake github` turns it into a fix ticket whose `caused_by` is the ticket that commit merged
   (`engine/docs/environments.md`, confirmed). Proposed: the intake files two tickets from the issue, each
   with its own `external_id` (`github#N:revert` and `github#N`, since intake skips a second ticket with the
   same one, `engine/rail/cli.py`, confirmed):
   - a revert ticket for the ticket that commit merged (`rail docs tickets`), and a `rail:stop` issue with `paths:` set to
     that ticket's scope; the engine closes the stop when the revert merges, and the revert goes on under it
     (`rail docs cloud`);
   - the fix ticket, `after` the revert, which redoes the work with the fix and closes the issue. The revert's
     pull request says `Part of #N`, so it doesn't close the issue.
   The owner decided for the revert first (2026-11-26).
   `rail stats` adds the time from the smoke issue's opening to the revert's merge: how long dev stayed broken.
   The `requested` event's `at` is the intake's time, not the issue's (`engine/docs/journal.md`,
   confirmed), so intake records the issue's `created_at` as `opened` on both tickets.
2. **Fix chains end.** A smoke fix ticket is one filed from an issue that starts with `Commit:`; its
   `requested` event says so (`smoke: true`). A smoke fix ticket whose `caused_by` ticket was itself a smoke
   fix ticket is not worked: the engine drops it with a record, as it drops a stuck AUTO ticket (`rail docs retries`),
   and the issue stays open for a person, with the chain in its comment. Today nothing
   limits the chain: `caused_by` is only counted (`engine/rail/stats.py`, confirmed).

## Part 2: the reviewer names lines worth a person's eye

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

## Part 3: measure the list

`rail stats --forge`. `rail stats` reads only the journals and the base branch's history, and line comments
live on GitHub; `--forge` also reads each merged ticket's pull request comments, and without it these lines
are left out. On PERSON tickets: the person's line comments per ticket (unmarked ones), and the share that
fall on an item. On tickets reverted afterwards: whether the reverted lines held an item. On AUTO tickets:
how many `rail:look` pull requests led to a revert or to a ticket that names them in `caused_by`.

## Tests, each before its part is kept

1. **Gate cases, no model.**
   - The smoke issue: two tickets with their own ids, a scoped stop closed when the revert merges, the issue
     closed by the fix; a smoke fix two deep is dropped with a record.
   - `rail stats` gives the time from a smoke issue's `opened` to its revert's merge.
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

1. The smoke-check revert and the fix-chain limit (Part 1).
2. `rail stats --forge` (Part 3).
3. The reviewer's `attention` field, after its test (Part 2).

## Decisions

**Made by the owner:** on a failed dev deploy, revert first (2026-11-26).

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
