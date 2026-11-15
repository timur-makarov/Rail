# Review

Every ticket gets a review after ship. The engine launches it, so it can't be skipped or written by hand:
`advance` runs `[review] command` in the ticket's worktree with a brief on stdin, reads the `review/v1`
output, binds the run to the patch, and resets the worktree afterwards. The reviewer may run commands and
write scratch files to test an idea; all of it is thrown away.

**Which changes skip it.** `[review] skip_paths` lists paths whose changes need no reviewer, such as docs. An
AUTO ticket merges without a review when every product file it changes matches that list. The paths decide,
not the author: one changed file outside the list, and the reviewer reads the whole change. A PERSON ticket
is always reviewed. The squash commit says which happened in its `Review:` trailer (`reviewer`,
`reviewer, security seat` or `none`), and [the sweep](sweep.md) reads afterwards what merged with `none`.

**The reviewer's model** is `[review] model` in `.rail/config.toml`, such as `model = "claude-opus-5-5"`.
The engine passes it to the command as `ANTHROPIC_MODEL`, which the `claude` CLI reads, and as `RAIL_MODEL`
for any other command. Empty leaves the command's own default. The model that answered is stored with each
run and shown in the pull request's Evidence table. `[consult] model` does the same for consult.

The brief holds the ticket, the diff, the matching `## Areas` rows, the project's own part of `AGENTS.md`
(never the `## Rail` section), what to look for, and the do-not-report list. On an AUTO ticket, what to
look for includes a security checklist. On a re-review the brief also holds the earlier findings and your
answers.

## Findings

Each finding has an id (`F1`, `F2`, ...), a severity, a location and a claim, and sometimes `evidence`: a
command the reviewer ran and its output.

- `blocking`: the change must not merge as it is.
- `advisory`: worth fixing, safe to merge.
- `parked`: a real problem this change didn't cause.

Answer every finding:

```text
rail answer NN F1 fixed "what you changed"
rail answer NN F2 declined "why it is not a problem"
rail answer NN F3 parked "a real problem this change didn't cause"
```

You can't decline or park a blocking finding: either answer disputes it, and a fresh refuter decides at the
next `advance`. The refuter sees the location, the claim and the evidence, not your argument. It dismisses
the finding, parks it (the problem is real, but this change didn't cause it), or upholds it. If it upholds
the finding and you still can't fix it, a person decides, with `rail answer NN F1 declined "why" --owner`
or `rail answer NN F1 parked "why" --owner`.

When you fix a finding, `advance` ships the fix and reviews the whole change again. A finding marked fixed
counts only once a later run doesn't repeat it.

## PERSON tickets

A PERSON ticket adds a security seat: a second run whose brief asks only about security. Each blocking
finding it reports goes to a refuter at once. A person merges a PERSON ticket.

## What the reviewer costs and finds

`rail stats` counts, over the merged tickets, the review runs, their cost and time by role and by model, how
each finding ended, and the share of decided blocking findings that ended in a fix. See [stats](stats.md).
