# Releasing what can be undone: what is left to build

This page is a proposal: what remains of a larger one. It says how Rail could decide and record each release to
prod while the project's CD carries it out, so that a release that can be undone needs no person and one that
can't waits for a person. Status: written 2026-11-25 from Rail's engine code and docs and the owner's positions
of 2026-11-25, cut on 2026-11-26 to what is not built. Nothing was run.

Its foundations are built and are no longer described here: the kinds of change a revert doesn't undo, with the
moments they take effect (`release` among them), recorded in the journal's `accepted` and `tier_raised` events
(`rail docs kinds`, `rail docs journal`); tickets whose contract is built in, as `kind = "revert"` is
(`rail docs tickets`); the brake `rail:stop` (`rail docs cloud`); the revert that goes first after a failed
deploy to dev (`rail docs environments`); tool declarations with the wait kinds `approval`, `grant` and `hold`
(`rail docs tools`, `rail docs retries`); and doctor's check that an environment holding a secret lets only the
base branch deploy (`rail docs tools`). Nothing below is implemented.

Marks: **confirmed** means read in Rail's code or on the primary source while writing this; **reported**
means a research agent read the primary source and it was not read again; **inferred** means it follows from
those, with the reason given.

## Why

**Today Rail stops at dev.** A ticket ends at its merge; the project's CD deploys the base branch to dev; prod
is "Nothing. A release goes through the project's CD gate; Rail has no part in it", and the machine holds no
prod secret (`engine/docs/environments.md`, confirmed). So every change, however small and however easy to
undo, waits for a person before users get it.

**That is where the work piles up.** In NBER working paper w35275 (500,000+ GitHub developers), autonomous
agents raised commits by 240% and releases by about 30%; the authors read it as bottlenecks of people later in
the chain (observational; two authors consult for Microsoft). (reported)

**The owner's rule decides it.** What can't be undone is a person's responsibility; what can be undone needs
no person to approve, review or learn about it (decided by the owner, 2026-11-25). A web service release with a
rollback that works is undone by the rollback. A published library version, an app store build, or data written
in a new shape is not.

**Why Rail decides and CD carries out, and not Rail deploying itself.** Deployment is what CD and hosting
platforms do, and each project's is different; rebuilding it would tie Rail to platforms. What only Rail has is
the record of what each merged ticket did and which kinds it holds, so it can say whether a release can be
undone. And prod secrets can stay with CD: the machine starts the deploy and never holds them.

## Part 1: a release is a ticket

A release is a ticket of its own, as the sweep is (`engine/docs/sweep.md`, confirmed): it changes only its
journal summary, and its squash commit carries a trailer, `Release: <sha>`, the commit it released. The
trailer marks where the next release starts, as `Sweep:` does for the sweep (`engine/rail/sweep.py`,
`engine/rail/steps.py`, confirmed). A trailer, not a git tag, because a cloud session refuses tag pushes
(`engine/docs/cloud.md`, "What the cloud refuses", confirmed). The ticket's `kind` field takes `release` beside
`revert` (`TICKET_KINDS` in `engine/rail/ticket.py` holds `revert` alone today, confirmed).

**When.** `rail next` offers a release when no ticket work is waiting and the base branch holds at least
`[release] after` merged tickets (by their `Ticket:` trailers) since the last `Release:` trailer. A person can
run `rail release` at any time. The candidate is the base branch's tip, provided:

- it has been on the base branch for `[release] soak_minutes`, so the dev deploy and its smoke check ran;
- no issue labelled `rail` that starts with `Commit:` is open for a commit in the range, since that is a failed
  dev smoke check (`environments.md`, confirmed);
- no `rail:stop` brake is open.

Otherwise the release rests, and the answer says why.

**Its contract** is built in: `kind = "release"`, the range, and the list of tickets in it with their tiers and
kinds. Its one check is the release check (Part 2).

**Its tier** is AUTO when the release can be undone, and PERSON otherwise:

| PERSON when | Why |
|---|---|
| `[release] reversible = false` for the project | A published library version, an app store build: others already have it (`public-release`) |
| A ticket in the range holds a kind that takes effect at release: `data-loss`, `data-shape`, `data-exposure`, `external-effect`, `access`, `infrastructure` (`rail docs kinds`) | Prod data and prod users meet it now; a rollback restores the code, not the data or the effect |
| `[release] drill_days = 0` (drills off) and no real rollback has passed | With drills off, "can be undone" is a claim nobody has run, like a migration's `rollback` field |

A ticket's kinds are read from its journal: the `accepted` event's kinds, each `tier_raised` event's `kind`,
and the `kinds` items of its review runs (`rail docs journal`, confirmed). The release takes the union over the
range, from the base branch, where merged tickets' journals are. A kind that takes effect at push or merge only
(`controls`, `money`, `licence`) doesn't make a release PERSON: its effect was earlier, and the ticket was PERSON
then. `runs-with-secrets` does, when the range changes the deploy workflow or a dependency whose build scripts
the prod build runs: that code meets the prod secrets now (`rail docs kinds`). The release brief lists each
PERSON reason with the tickets and kinds behind it.

**A PERSON release** waits at `APPROVE_CONTRACT`, as any PERSON contract does (`engine/rail/table.py`,
confirmed): the person approves it with `rail accept NN` or `rail:go`. Then the engine runs it. Its merge is the
engine's whatever its tier: the merge only records what happened, and the person's act was the approval. This
is the one ticket kind where a PERSON ticket's merge is not a person's, and the docs say so. It needs a change
to the table: today the `MERGE` row refuses the engine's merge of a non-AUTO ticket when there is a remote
(`and not (f.project.remote and not f.auto)`, confirmed), so a PERSON release would fall to `MERGE_BY_PERSON`.
The row gains `or kind == "release"`.

## Part 2: what the engine runs

```toml
[release]                                 # reader: next and rail release. Empty command: Rail doesn't release
command = ""                              # starts the project's deploy of $RAIL_RELEASE_SHA and returns when it is
                                          # live or failed, such as: gh workflow run deploy.yml -f sha=... and a watch
check = ""                                # the release check: read-only against prod, exit 0 when it is healthy
rollback = ""                             # deploys $RAIL_RELEASE_SHA (the last released commit) again
reversible = true                         # false for a library, a package, an app store build: every release is PERSON
after = 1                                 # merged tickets since the last release before one is offered; 0: off
soak_minutes = 30                         # time on the base branch (dev deploy and smoke check) before a release
drill_days = 30                           # an AUTO release drills its rollback when the last one passed longer ago; 0: no drills
tool = ""                                 # the [tools.NAME] whose names the commands read (`rail docs tools`)
```

Defaults: with an empty `command`, nothing changes for a project: Rail doesn't release, and prod stays a
person's act as today.

The release ticket's ship runs, in order:

1. `command` with `RAIL_RELEASE_SHA` set to the candidate. A failure stops here and counts as a failed step,
   with the retry budget and cap as for any step (`engine/docs/retries.md`, confirmed); nothing reached prod, or
   CD's own failure left the old version, which `check` confirms.
2. `check`. On a pass, the ticket merges with the `Release:` trailer.
3. On a failed `check`: `rollback` with `RAIL_RELEASE_SHA` set to the last released commit, then `check` again.
   - When that passes, the ticket merges with a `Rolled-back: <sha>` trailer instead of `Release:`, so the next
     release starts from the same place. The engine opens an issue labelled `rail` that starts with
     `Release: <sha>` and holds the check's output and the range. `rail intake github` turns it into a fix
     ticket, as it does a dev smoke issue (`environments.md`, confirmed). If the range holds one ticket, the fix
     ticket's `caused_by` is that ticket; with several, the fix ticket's brief lists them and its first task is
     to find which one. No release is offered while that issue is open.
   - When the rollback or its check fails, prod is in a state the machine can't vouch for. The ticket waits
     for a person (`RELEASE_BROKEN`, a wait of kind `approval`) with both outputs. This is the one release wait
     on an AUTO release: prod broken and not restored is harm still happening, which no later act of the machine
     undoes.

`check` must not write prod data or send anything (an `external-effect`). A rule alone is not a guard, so two
things back it:

- **It runs as a read-only identity.** The test identity it signs in with, if any, has a role that can't write
  (a project's own setting; `rail doctor` asks the project's `check` to prove it only through the gate case
  below, since Rail can't read a project's roles). Without sign-in it reads public pages and endpoints only.
- **A gate case catches a writing check before it is kept** (Tests, case "fake prod"): `check` runs against a
  local fake prod that records every request, and any write method (POST, PUT, PATCH, DELETE) or outbound
  message fails it. `rail-verify`, which writes the check, runs that case on the project's own `check`.

A person approves the `[release]` table, since `.rail/config.toml` is in `person_paths` (`seed/config.toml`,
confirmed).

## Part 3: the rollback is tested

A release counts as one that can be undone only while its rollback is known to work. The engine records each
`rollback` run that ended with a passing `check`, in the release ticket's journal. When the newest is older than
`drill_days`, or there is none, the release does a drill first: release the candidate, run `check`, roll back
to the last released commit, run `check`, release the candidate again, run `check`. The drill's rollback is the
record. A project whose first release has no record gets the drill on it.

A drill puts the old version back for the time between two deploys, and the old version then reads data the
new one wrote meanwhile. That is safe only because of the tier: a range with a `data-shape`, `data-loss` or
`infrastructure` kind is PERSON (Part 1), so an AUTO release's range changed no stored shape, and the old version
reads what the new one wrote. So a missing or old rollback record doesn't make a release PERSON: an AUTO release
runs the drill, and the drill writes the record. A PERSON release has no drill, since its range may change a
stored shape the old version can't read; the person approves it knowing whether the last drill is recent. A
project that doesn't want the old version back even for a moment sets `drill_days = 0`: no drill runs, and a
release is PERSON until a real rollback has passed (Decision 3).

## Part 4: the secrets stay with CD

The machine still holds no prod secret. `command` starts the project's deploy through GitHub
(`POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`, a `workflow_dispatch` event; not
checked on GitHub's docs for this page), and the deploy workflow reads the prod secrets from a GitHub
environment that only that workflow uses.

`workflow_dispatch` takes any `ref`, so a dispatch could run the deploy workflow from a ticket branch, with that
branch's workflow file and code. The prod environment's deployment-branch rule must allow the base branch only:
then a job on any other ref can't read the environment's secrets (GitHub's environment rule; not checked on
GitHub's docs for this page). `rail doctor` already reads each environment that holds a secret and fails one
open to any branch (`rail docs tools`, confirmed). What this adds: the release setup names its deploy
environment, `rail doctor` reports a release setup whose environment fails that line as broken, and `rail next`
offers no release until it is fixed.

What a person grants once:

- the machine's identity may dispatch the deploy workflow. The machine identity (a GitHub App) is not built,
  so this grant has nothing to attach to yet;
- the prod environment's protection lets that dispatch run without a GitHub reviewer, since Rail's tier now
  decides when a person approves. A project that keeps GitHub's required reviewer gets a second approval on
  every release, and every AUTO release then waits there; `rail doctor` reports that state;
- the deploy workflow file is under `.github/workflows/**`, which the seed lists under `[kinds]
  runs-with-secrets` (`seed/config.toml`, confirmed), so the machine can't change what it runs with the prod
  secrets without a person.

`check` needs only what a user has: the prod URL, and a test identity if the check signs in. That identity is a
grant like the dev one, not a prod secret, and is `access` only if it can do more than a user.

## Part 5: what `rail stats` adds

- Releases, by tier and by PERSON reason; rollbacks; drills; releases broken (`RELEASE_BROKEN`: prod is broken
  and not restored).
- Time from merge to prod: for each ticket, from its squash commit to the `Release:` commit that carried it.
  The median, and the share released within a day. This is the line that shows the NBER gap in this project.
- Fix tickets from a release issue, and their `caused_by`.

## Docs and files that change

- `engine/docs/environments.md`: the Prod row becomes: with `[release] command` set, Rail offers a release after
  merges, starts the project's CD with the commit, runs the release check, and rolls back when the check fails;
  a release that can't be undone waits for a person's approval; without it, releasing is a person's act, as
  today. The person's acts become: merging a PERSON ticket; deleting data; handling credentials (grants);
  approving a release that can't be undone. "The machine holds no prod secret" stays true. A new page,
  `engine/docs/release.md`.
- `engine/rail/config.py` defaults, `engine/rail/docs.py` (`rail docs config`), `seed/config.toml`: `[release]`.
- `engine/rail/table.py` and `engine/docs/loop.md`: the release offer, its rests, `RELEASE_BROKEN` (in
  `WAIT_KINDS`), and the `MERGE` row's exception for a release.
- `engine/rail/steps.py`: the release ship and the trailers. `engine/rail/stats.py` and `engine/docs/stats.md`:
  Part 5 and reading `Release:` and `Rolled-back:`. `engine/rail/cli.py`: `rail release`.
- `engine/rail/cli.py` (intake): an issue that starts with `Release:`.
- `engine/docs/tickets.md`, `engine/rail/ticket.py` and ticket lint: `kind = "release"`.
- `engine/docs/github.md` and `rail doctor`: the dispatch grant, the environment's reviewer setting, and the
  release's deploy environment.
- `seed/skills/rail-verify/SKILL.md`: writing a release check that is read-only.

## Tests, each before its part is kept

1. **Gate cases, no model.** Fake `command`, `check` and `rollback` scripts that record their calls and exit as
   told:
   - with `after = 1`, a merge makes `rail next` offer a release once nothing else waits; with `command` empty,
     nothing is offered; `0` turns it off;
   - a candidate younger than `soak_minutes`, an open `Commit:` issue in the range, or an open `rail:stop` makes
     it rest with the reason;
   - a range of AUTO tickets with no kinds is an AUTO release; a range with a `data-shape` kind (from an
     `accepted` event, a `tier_raised` event, or a review's `kinds`), or `reversible = false`, or a changed deploy
     workflow, or `drill_days = 0` with no rollback since, is PERSON with that reason; a range whose only kinds
     are `controls` or `money` is AUTO; an AUTO range with no rollback record within `drill_days` stays AUTO;
   - a PERSON release, once approved, is merged by the engine with a remote, and a PERSON ticket of any other
     kind still waits at `MERGE_BY_PERSON`;
   - fake prod: a `check` that sends a POST to the fake prod, or a message, fails the case; a `check` that only
     reads passes;
   - a prod environment whose deployment-branch rule allows more than the base branch makes `rail doctor`
     report it and `rail next` offer no release (against the fake GitHub);
   - a passing release merges with `Release: <sha>`; the next release's range starts after it;
   - a failing check runs `rollback` with the last released commit, merges with `Rolled-back:`, opens a
     `Release:` issue that intake turns into a fix ticket (with `caused_by` for a one-ticket range), and no
     release is offered while it is open;
   - a failing rollback gives `RELEASE_BROKEN` on an AUTO release;
   - an AUTO release with no rollback record within `drill_days` runs the drill in order, and the drill's
     rollback counts as the record; a PERSON release runs no drill;
   - `rail stats` reads the trailers and gives time from merge to prod on fixture history.
   Kept when every case behaves as written.
2. **Pilot on a real deploy, no model needed.** A test project with a service on a host that has a deploy API
   and a rollback, its CD started by `workflow_dispatch` from a cloud session. Three releases: one that passes,
   one with a check made to fail (rolled back, issue filed), one PERSON by a `data-shape` ticket (approved, then
   run). Kept when each ends as written and no prod secret was in the cloud session's environment. It needs a
   host account and a grant, so it waits for the owner.

Not covered: canary and percentage rollouts (CD's own); releases of several services in a set order; mobile
release trains; a project whose prod data a rollback can't run against (that project's tickets are `data-shape`
and its releases PERSON).

## Assumed, not verified

- That a cloud session's GitHub access may call the `workflow_dispatch` endpoint. `cloud.md` lists what the
  cloud refuses and doesn't name it; Rail uses REST for everything else there.
- That `soak_minutes` and the absence of a `Commit:` issue mean the dev smoke check passed. The smoke step only
  opens an issue on failure, so a CD that never ran looks the same. A project can make `command` refuse a commit
  dev hasn't deployed.
- That library registries can't truly undo a published version (npm, crates.io and PyPI each restrict deleting
  or reusing one; from my own knowledge, not checked). `reversible = false` doesn't depend on the details.
- That a drill's brief return to the old version is acceptable for every service that calls itself reversible.

## Order of work

One pull request each, with docs and `CHANGELOG.md`.

1. The release ticket: `[release]`, the offer and its rests, the tier from the range's kinds, `command` and
   `check`, the fake-prod case, the trailers, the `MERGE` row's exception, `rail release`. The journal's kinds
   and the brake `rail:stop`, which a release must respect, are built.
2. The rollback, the `Release:` issue and its intake, `RELEASE_BROKEN`.
3. The drill and `drill_days`.
4. `environments.md`, the stats lines, the doctor checks (the release's deploy environment among them). The
   dispatch grant needs the machine identity, which is not built.
5. After the pilot: the `rail-verify` text for the release check.

## Decisions

**Made by the owner (2026-11-25):** what can't be undone is a person's responsibility.

**Open:**

1. Who releases. Proposed: Rail decides, records and starts the release; CD carries it out and holds
   the secrets. The alternatives are Rail only recording what CD released, or Rail deploying itself.
2. When a release is offered: after each merge (`after = 1`, proposed), after a count, or on a schedule.
3. The drill: run it when the last rollback is older than 30 days (proposed), or never, with every release
   PERSON until a real rollback has passed.
4. On a rolled-back release, file one fix ticket for the range (proposed), or revert first as a failed deploy
   to dev does (`rail docs environments`).

## Sources

Rail, confirmed: `engine/docs/environments.md`, `sweep.md`, `cloud.md`, `retries.md`, `tools.md`, `kinds.md`,
`journal.md`; `engine/rail/sweep.py`, `steps.py`, `table.py`, `ticket.py`; `seed/config.toml`.

Reported: NBER working paper w35275 (autonomous agents raised commits by 240% and releases by about 30%).
