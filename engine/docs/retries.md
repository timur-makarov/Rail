# Retries, consult and waits

## The retry budget

A failure counts as stuck only when it repeats. Each failed step event carries a `signature`: the step's name
and a hash of the tail of its output, normalised so that the same failure gives the same signature on every
run. The engine lower-cases the output and replaces numbers, hex strings, absolute paths and temp-folder
names with placeholders, then collapses whitespace, so a new line number, commit or temp path doesn't make
the same failure look new.

`[retry] budget` (2 by default) counts the failures in a row at one step with the same signature. When a
step fails the same way twice, the consult pack advises once, and you get one more attempt. If that fails
too, whatever its output, the ticket is stuck. When there is no pack, it is stuck at the budget. A failure whose signature differs from the last failure at that step is progress: the count of
same failures starts again at 1.

`[retry] cap` (5 by default) bounds the rest: after that many failed attempts at one step, whatever their
signatures, the ticket is stuck. This is what stops an agent that keeps producing new errors.
An agent could also make a failure look new by changing the text it prints; the cap bounds that too.

**A stuck ticket.** An AUTO ticket that is stuck is dropped by the engine with a record (`STUCK`): nothing
merged, so nothing needs undoing, and a wait would only spend a person's attention on doubt. `rail next` writes a
`dropped` event with `by: "engine"`, the step and its last failure's signature; writes the drop's mark on the
counter branch; closes the pull request; takes the `rail` label off the issue with a comment that says what was
tried and why it stopped; and removes the worktree and branches. The closed pull request keeps the commits on
GitHub. To try again, label the issue `rail` again. A PERSON ticket that is stuck waits for a person
(`RETRY_CAP`): a person is there anyway.

**The mark comes first.** When the counter branch can't be pushed (offline, or a push refused other than by
another clone's push), nothing is removed or closed: the ticket rests as `DROP_PENDING` until a later
`rail next` writes the mark and finishes the drop. `rail drop` works the same way.

Both count since the step last passed or since a person last continued the ticket. A review run counts when
it leaves a blocking finding open, and all such runs at a review step count as the same failure, so the
budget there is a plain count of failed runs. A review run that timed out, or whose output is invalid (not
JSON, not `review/v1`, a finding on a file or line that doesn't exist, or a non-zero exit), is the reviewer's
fault, not the change's: it doesn't count and doesn't move the worker ladder. It is started once more, and
two such runs in a row wait for a person. A command that
times out at ship, such as `verify` or a check, counts like any other failure. A failed step event with no
`signature`, written by an older engine, counts as the same failure as its neighbour.

A command the shell couldn't start (exit 127: not found; 126: found but not executable) is recorded as
`could_not_run`, not as a failure of the change: nothing was checked. It still counts as an attempt, so a
missing tool can't loop for ever, and a verify that couldn't run is never taken for a red base. Install the
tool to go on, and open a ticket so that `[commands] provision` (or `setup`) installs it on every machine.

## Consult

Consult asks a different model for advice when you are stuck. Its brief is the ticket, the diff and the
failing step's raw output, plus one question; your own story is left out. It answers `proceed`, `change`
or `stop` (a product decision the ticket leaves open; a plainly wrong check is one you amend), and the engine keeps the advice in `.rail/journal/NN-advice.md`. It is read-only and never
checks the change, and at most three run per ticket. Every verdict is advice, `stop` too: you still get the one attempt after
it. The advice given at the budget is in the answer of
`rail advance` and, until the next attempt, in the brief of `rail next`, so a fresh worker gets it too. Ask it yourself with `rail consult NN "question"`.

## Waits

A ticket waits for a person (`owner: human`) for an approval, a person's merge, a review that timed out or gave
invalid output twice in a row, or an amended Done Contract; and a PERSON ticket also for the retry budget or cap,
a finding the refuter upheld, and a ticket it comes after that was dropped. On an AUTO ticket those three are no
wait: at the cap the ticket is dropped (above); a finding the refuter upheld stands, and disputing it again comes
back as a failed review that counts toward the cap; and when a ticket it comes after was dropped, the agent
decides, with the contract writer's model (`[worker] contract`), whether to remove that ticket from `after`
(`rail amend NN "why" --file FILE`) or to drop this one (`rail drop NN --reason "why"`). Both are recorded. The brief says what is
needed. One act continues any wait:

```text
rail accept NN "what to do differently"
```

The note goes into your next brief, with a fresh retry budget and a fresh cap. If it holds beyond this ticket, open a
ticket that writes it into the project's part of `AGENTS.md`, or into a rule.
