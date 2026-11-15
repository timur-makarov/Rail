# The sweep

Some changes merge with no reviewer: a ticket whose every changed file is in `[review] skip_paths`, and a
commit a person made with no ticket. The sweep reviews them afterwards. It counts the commits on the base
branch since the last sweep that have no `Ticket:` trailer, or whose `Review:` trailer says `none`. Once
there are `[sweep] after` of them (20 by default), `rail next` offers `rail sweep` when no ticket work is
waiting. A person can run `rail sweep` at any time. A merge commit counts once, however many commits it
holds.

A sweep is itself an AUTO ticket that changes only its journal summary. It changes no product file, so it
needs no review and merges on its own. Its squash commit carries a `Sweep:` trailer, which marks where the
next sweep starts. The first sweep starts where Rail was set up.

- **Free part:** doc-lint on the base branch, and each structure rule counted over the whole tree.
- **Review part:** one pass of the reviewer over the combined changes, looking for duplication across
  tickets, logic in the wrong area, weak checks, security and stale docs. It also reads the findings parked
  in those tickets and the checks reviewers proposed for fixed findings.
- **Output:** tickets, never edits, and a one-page summary in `.rail/journal/NN-summary.md`. The agent opens
  a ticket for each finding worth one, and one ticket "make it a check: ..." for each kind of proposed check,
  so a mistake that could happen again ends as a test, a rule or a lint.

A sweep never blocks a merge.
