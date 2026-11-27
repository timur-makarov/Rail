# The contract

The contract is a ticket's Done Contract, `scope_paths` and tier. It freezes at acceptance: from then on,
ship and CI fail when the ticket's contract differs from the accepted one, or its tier is lower.

To change it, edit the ticket in its worktree and run:

```text
rail amend NN "why the contract changes"
```

The reason is optional. It is kept in the `amended` event, and the person who merges the change reads it.

- A wider or narrower scope, or a change from AUTO to PERSON, is accepted again at once. The added paths are recorded.
- A changed Done Contract is accepted at once, and the reviewer is shown the contract as first
  accepted next to it (`rail docs review`). On a PERSON ticket the pull request's "Read these" names the amend
  and its reason, for the person who merges. Only a PERSON ticket whose kind the project names in
  `approve_contract` waits until a person runs `rail accept NN` (`rail docs kinds`).
- A tier never goes down: a PERSON ticket stays PERSON.
