# Rail for a team: what could be built

This page is a proposal. None of it is implemented. It lists what a team of several people would need from
Rail, how each piece could be built, and what it would cost in complexity. Status: written 2026-11-17 from
the engine's docs and a reading of `forge.py` and `cli.py`, and brought up to date on 2026-11-27 with what was
built since; nothing here was tried on a real team. `proposals/features.md` holds the features that wait for
a second person under **More people**.

## What already works with several people

- **Sessions don't collide.** A claim is a push to the remote, so two sessions never work the same ticket.
  IDs come from one counter branch, `rail/ids`. Work with no journal event for `[claim] stale_minutes` is
  taken over.
- **Any session can continue any ticket.** State lives in git and the journal, not in a session.
- **Strangers can't steer the agent.** Only comments from collaborators reach a brief, and an issue becomes
  a contract as written only when its author can push.
- **Waits are visible.** Every wait carries the label `rail:needs-you`.
- **A PERSON ticket takes one act.** It is built before a person sees it, and its pull request opens with
  `## Read these`: why a person merges it, and the lines to read (`rail docs github`, `rail docs kinds`).
  Whoever on the team approves reads the same list.
- **One ticket can go first.** The label `rail:first` on a ticket's pull request or its issue, or the line
  `priority = "first"`, is read by `rail next` before the ticket's number (`rail docs tickets`). There is one
  level, and the mark holds the ticket for nobody (see 4).
- **Two tickets never work the same paths at once.** A ticket whose `scope_paths` overlap those of a ticket
  under way waits (`SCOPE_OVERLAP`) until that one merges or is dropped, and `rail stats` shows how long
  tickets waited so (see 5).
- **The numbers split by what a team asks about.** `rail stats` shows the cost of a merged ticket for each
  tier, a person's acts for each ticket, and the outcomes by worker, by language, by project and by source.

## What a team would miss

### 1. A wait names nobody

`rail:needs-you` says a person is needed, not which person. With one owner that is enough. With five people,
every wait is everyone's and so nobody's.

- **Build:** when a wait starts, the engine assigns the pull request to one login: the person who asked for
  the ticket (the `Person:` line of `## Grilling`, or the issue's author) for a contract approval or a retry
  wait; the owner of the touched area for a merge. Each person's inbox becomes the search
  `is:open label:rail:needs-you assignee:@me`.
- **Cost:** one REST call per wait and a rule for who the owner of an area is (see 2). Small.

### 2. Who may approve what

Today any collaborator can label `rail:go` or press merge on a PERSON ticket.

- **Build with GitHub, not in Rail:** a `CODEOWNERS` file for the paths that make a ticket PERSON
  (`person_paths`, `migration_paths` and each kind's paths in `[kinds]`, `rail docs kinds`), and "Require
  review from Code Owners" in the ruleset. Rail would only need to read `CODEOWNERS` to pick the assignee
  in 1, and `rail doctor` could check that every such glob has an owner.
- **A second approval for the riskiest paths:** a ruleset setting too (required approvals: 2 on those
  paths). Rail needs nothing new.
- **Cost:** almost none in the engine. The ruleset in `seed/ruleset.json` would get a team variant.

### 3. Whose name the unattended work carries

A scheduled cloud session runs with one person's GitHub login, so every pull request it opens is that
person's, and GitHub does not let an author approve their own pull request. With required approvals turned
on, that person could never approve the runner's work.

- **Build:** run unattended sessions under a machine account or a GitHub App, so every person can approve.
  The engine would record who asked for the ticket in the pull request's description, since the author
  field no longer says it. **A machine identity** in `proposals/features.md` has the design and its open
  decisions.
- **Not verified:** how a Claude Code cloud session chooses its GitHub identity, and whether a scheduled
  task can use a different one from the person who made it. Check this before building anything.

### 3a. Who owns the runner

Checked on 2026-11-19 against Claude Code's page on scheduled tasks, and seen in one cloud run:

- A scheduled task belongs to one claude.ai account. It is not shared with teammates, its runs count against
  that account, and its commits and pull requests carry that person's GitHub login.
- A GitHub trigger starts a new session for every matching event. Events over an hourly cap are dropped.
- Filters are documented for pull request triggers only: author, title, body, base branch, head branch,
  labels, draft, merged. None is documented for issue triggers.
- Not documented: whether the event (which issue, which label) reaches the session, and whether a task's
  own acts start it again. In the cloud run a "pull request edited" trigger did start runs from the
  engine's own edits.

So when two people each set the runner up, every event starts two sessions. Claims keep them off the same
ticket, but the cost doubles and the winner of each claim decides whose login the work carries.

- **One runner (works today):** one account owns the tasks, best a machine account (see 3). Everyone else
  files issues, labels `rail:go` and merges. Nothing to build. The cost: one account's limits carry the
  whole team's work.
- **A runner for each person:** each person's runner works only that person's tickets. Trigger filters
  can't do this alone, because new work arrives as issues and issue triggers have no documented filter.
  The engine has to share the work out: the journal already records who filed each ticket (`filed_by`), and
  `gh api user` says whose session this is, so `rail next` could take only the tickets its own login filed,
  plus tickets nobody's runner has taken after a while. A run started by someone else's event then finds no
  work and ends in one command. A pull request filter such as "Labels contains `owner:<login>`" would only
  save those empty runs.
- **Cost:** the second is one comparison in `next`'s ordering and a rule for orphaned tickets, and it is the
  same mechanism as 4. Start with one runner; build the second when one account's limits are reached.

### 4. A ticket a person keeps

An engineer who wants to drive a ticket in their own session has no way to tell the runner to leave it.
`rail next --ticket NN` claims it, but only once work starts.

- **Build:** a ticket assigned to a person on GitHub is skipped by every session that is not that person's.
  `rail next` already prefers the session's own tickets; this adds "and never takes one held by someone
  else". `rail status` shows the holder.
- **Cost:** one field read from the pull request or issue, and one branch in `next`'s ordering. Small. This
  is the first piece I would build.

### 5. Two tickets with wide scopes

Tickets whose `scope_paths` overlap already wait for each other. The comparison is glob against glob, so
with several people filing tickets, two that would never touch the same file can wait in a row because both
named a whole folder.

- **Build:** compare a new claim with the files the tickets in flight have changed so far, which is exact.
  **Claims by changed files** in `proposals/features.md` has the design.
- **Cost:** small. Build it when `rail stats` shows tickets resting behind an overlapping scope
  (`accepted to claimed, behind a ticket with an overlapping scope`).

### 6. How many sessions, and who pays

Each person's sessions run on their own account. A shared runner runs on one account.

- **Build:** nothing in the engine. A team decides how many scheduled runs it starts. `rail stats` shows
  what a merged ticket cost for each tier, worker and project. It counts each source's tickets and does not
  say what they cost; that split is one more column if a team asks for it.

## What I would not build

- **One label for each ticket state**, kept current so that a GitHub project board shows the railroad. It
  was proposed here and is dropped (`proposals/features.md`, **Dropped**): it costs label churn and REST calls
  on every transition, and `rail status` and the `rail:needs-you` label already say where a ticket is and
  whether it waits. Notifications to a chat tool belong in a bot outside Rail.
- **Per-person statistics.** `rail stats` by area or by source says where the process fails. By person, it
  says whom to blame, and people will route around it.
- **Roles inside Rail.** GitHub already has collaborators, teams and code owners. A second permission
  system would drift from the first.

## Suggested order

1. A ticket a person keeps (4).
2. Addressed waits (1), with `CODEOWNERS` as the source of owners (2).
3. The machine identity (3) as the one runner's owner (3a), once it is verified what a cloud session
   allows. A runner for each person only when one account's limits are reached.
4. Claims by changed files (5), if `rail stats` shows tickets resting behind overlapping scopes.
