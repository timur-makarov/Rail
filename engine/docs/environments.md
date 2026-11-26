# Environments

Environments belong to the project. Rail touches each at one named point.

| Environment | What Rail does |
|---|---|
| The machine | In a cloud session and on a CI runner, `provision` installs what the checks need, once per machine, as root. On your own computer Rail installs nothing: `rail provision` shows the command |
| Local | `setup` runs in each ticket's worktree with `RAIL_TICKET` set, so parallel tickets can name their own databases and ports. `verify` and the checks run at ship |
| Dev | Nothing at runtime: a ticket ends at its merge, and the project's CD deploys the base branch. Add one step to that CD: after a deploy, run the smoke check, and when it fails, open an issue labelled `rail` whose body starts with `Commit: <sha>`. `rail intake github` turns it into a fix ticket whose `caused_by` is the ticket that commit merged |
| Prod | Nothing. A release goes through the project's CD gate; Rail has no part in it |

- The machine the agent runs on holds local and dev secrets only.
- A change to `person_paths` or `migration_paths`, or a change of a kind in `rail docs kinds`, is a PERSON
  ticket, so a person sees it before it reaches dev.
- A person is asked only about what a revert doesn't undo (`rail docs kinds`): a PERSON ticket's contract
  and its merge. Credentials stay with people: the machine never holds a prod secret.
