# The sweep

The sweep looks back over what merged since the last sweep. It does three things:

- It reviews the changes that merged with no reviewer: a ticket whose every changed file is in
  `[review] skip_paths`, and a commit a person made with no ticket. These are the commits on the base branch
  that have no `Ticket:` trailer, or whose `Review:` trailer says `none`. A merge commit counts once, however
  many commits it holds.
- Once `[sweep] every` tickets merged, whatever their review, it reads the code of the areas they changed as
  it is now. Each ticket's own review saw one change. Duplication and logic in the wrong area show up across
  tickets.
- It gathers what every merged ticket left behind, reviewed or not: the findings reviewers parked, the
  advisory findings the author left open, the checks reviewers proposed for findings that were fixed, the
  findings an author declined, the lines workers wrote about problems outside their tickets, the notes a
  person gave, the failures that recur, and the comments that name a ticket that ended. Nothing else reads
  these.

`rail next` offers `rail sweep` when no ticket work is waiting and either is true:

- `[sweep] after` changes (20 by default) merged with no review;
- `[sweep] every` tickets (20 by default) merged, counted by the `Ticket:` trailers on the base branch. `0`
  switches this off.

With the default config every change is reviewed, so `every` is what brings the sweep. A person can run
`rail sweep` at any time: before `every` tickets merged, it gathers and reads no area.

A sweep is itself an AUTO ticket that changes only its journal summary. It changes no product file, so it
needs no review and merges on its own. Its squash commit carries a `Sweep:` trailer, which marks where the
next sweep starts. The first sweep starts where Rail was set up.

- **Free part:** doc-lint on the base branch, and each structure rule counted over the whole tree.
- **Review part:** one pass of the reviewer, looking for duplication across tickets, logic in the wrong
  area, weak checks, security and stale docs. It reads two things, and runs when there is either. The first
  is the changes that merged with no review: their diffs are in the brief. The second, once `[sweep] every`
  tickets merged, is each area that a ticket merged since the last sweep changed: a row of `## Areas` in the
  base branch's `ARCHITECTURE.md` with a path that matches a file the ticket changed. The brief names each
  such area with its paths and the tickets that changed it, and the ids of all the merged tickets, and the
  reviewer reads the area's code in its working directory, which is the base branch. What a ticket changed
  under `.rail/` counts for no area. The pass also reads the parked and open advisory findings and the
  proposed checks. It costs one model run for each sweep. With nothing unreviewed and no area to read there
  is no model run: the journal gets a `harvest` step instead. The brief's wording for the areas has not been
  tested with a model run.
- **Findings an author declined, by kind:** the advisory findings an author closed with
  `rail answer NN F1 declined "why"`. A kind is one claim, spacing and case aside, however many tickets it
  was made in; the summary gives the first author's reason. A kind that is a real problem gets a ticket. A
  kind declined in more than one ticket for a reason that holds gets one ticket that adds a line to
  `REVIEW.md`, so reviewers stop reporting it.
- **Problems workers saw outside their tickets:** the `Noticed:` and `not tested:` lines of each merged
  ticket (`rail docs tickets`). Each is a candidate for a ticket.
- **What a person said:** every note a person gave with `rail accept NN "note"`. The briefs of that ticket
  carry a note only until its next ship. A note that holds for later tickets too is a standing rule, and gets
  one ticket that makes it a line in the project's part of `AGENTS.md`, a check or a structure rule.
- **Failures that recur across tickets:** a failed step whose signature (`rail docs retries`) two or more
  merged tickets share. Signatures leave numbers, hashes and paths out, so the same failure in two worktrees
  is one. Failed review runs are left out: they all share one signature. Each gets one ticket: a check that
  catches the cause before a ship, or a line in the project's part of `AGENTS.md`.
- **Work left for later whose ticket ended:** a `TODO(NN)` or `FIXME(NN)` comment on the base branch whose
  ticket NN merged or was dropped, anywhere in the tree and whenever that was. No ticket will do the work it
  names. The summary lists the comments for each such ticket, with a `Check:` line that fails while one
  stands, and the agent opens one ticket with `external_id = "todo#NN"` that does what is left or removes
  them. While that ticket is open, later sweeps leave NN out. A `SHORTCUT(NN)` names the ticket that cut the
  corner, and stays.
- **Patterns in the worker runs:** each `rail work` run records the dead ends its tool calls show, with a short
  key each (`rail docs journal`, the `worked` event): a command that failed before it first passed, a command
  the machine doesn't have, a call a rule or the guard denied, a file read more than twice. The same key in the
  runs of three or more tickets merged since the last sweep is a pattern: something the project could have
  told the worker. No model reads for this, and the run logs, which are never committed, aren't needed.
- **Flaky checks:** a command that both failed and passed on the same code (`rail docs retries`) in two or more
  tickets merged since the last sweep. Commands are matched as failure signatures are, with numbers, hashes and
  paths left out. The summary gives each with a `Check:` line that runs it 20 times in a row.
- **Question types with one answer:** a type of the triage step (`rail docs triage`) whose last 20 answered
  questions, in every journal on the base branch, got the same answer 19 times or more. The agent opens one
  ticket that makes the answer a rule of the engine or removes the type.
- **Kinds a person refuses at the merge:** a kind held by three or more of the last 20 PERSON tickets that
  ended, merged or dropped, which a person closed without a merge, and which `approve_contract` does not name.
  Read from the drop marks. The agent opens one ticket that puts the kind into `approve_contract`, so a person
  approves such a contract before the build (`rail docs kinds`). The summary's wording for this has not been
  tested with a model run.
- **Kind paths reviewers found:** a file a reviewer named a kind on, in a ticket merged since the last sweep,
  that the base branch still has and that no path of that kind in the config matches. A file under a folder
  whose coverage ticket is open is left out: that ticket adds the path (`rail docs languages`). The agent opens
  one ticket that adds the path under its kind in `[kinds]`. The summary's wording for this has not been tested
  with a model run.
- **Output:** tickets, never edits, and a summary in `.rail/journal/NN-summary.md` with a section for each
  part above. A section the agent files from says under its heading what gets a ticket; that wording has not
  been tested with a model run for the five sections from "Findings an author declined" to "Work left for
  later". The agent opens a ticket for
  each finding that names something wrong (a finding about style gets none), and one ticket
  "make it a check: ..." for each kind of proposed check, so a mistake that could happen again ends as a
  test, a rule or a lint. It opens one ticket for each pattern, for what would have told the worker: a `setup`
  or `provision` command, a line in the project's part of `AGENTS.md`, or a guide's text; and one ticket for each
  flaky check, to make it deterministic, with the `Check:` line the summary gives. Filing tickets is writing contracts, so the answer (`SWEEP_TICKETS`) names
  `[worker] contract`'s model and effort, and `rail work NN` runs it like any ticket's work: a script that
  drives Rail with `rail next`, `rail work` and `rail advance` goes through a sweep with no step of its own.

When the sweep finds nothing, the agent gets no task: `rail next` answers `SWEEP_EMPTY` with
`rail advance NN`, and the sweep's ticket merges, which moves the marker. Nothing means that doc-lint is
clean, every section of the summary is empty, and the review pass either did not run or reported no finding.

A sweep never blocks a merge. To turn other signals into tickets, such as failed CI runs or an error
tracker's export, write a [source](sources.md).
