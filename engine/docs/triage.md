# The triage step

Where a worker would judge its own case, a run with no stake in the answer judges it. The engine states a fact
it produced itself, such as a test that fails or a line the change added. A fresh run that did not write the
change answers one closed question about that fact, with one of a few fixed answers. The engine then does what
the answer means. The refuter works this way for one question, whether a finding holds (`rail docs review`);
triage is that step with a table of question types, so a new question costs a table entry and its test.

Only closed questions go here. Whether a change is good stays the reviewer's question.

## How a question runs

- **Raised at ship.** When every ship step has passed, each type looks for its fact in the patch. A fact found
  is a `question` event with the type, the `patch_id` and the fact (`rail docs journal`). One fact raises one
  question for a patch: shipping the same patch again raises nothing.
- **Answered before any review.** A shipped ticket with an open question is `reviewing`, and `rail next`
  answers `TRIAGE` with `rail advance NN`. `advance` starts one run for each open question, then the review
  runs the patch needs, so no review is spent on a patch that is about to change. A ticket whose change needs
  no reviewer (`[review] skip_paths`) still gets its questions answered.
- **The run** starts as a review run starts: in the ticket's worktree, with the brief on stdin, tools that read
  and run, and no push. The brief holds the question, the answers with what each means, the fact, and only
  what the type says to show: never the whole change. `[triage] command` and `[triage] model` name the command
  and the model; empty means `[review]`'s. The command gets `RAIL_REVIEW_PROMPT` (the path of the triage
  prompt), `RAIL_REVIEW_SCHEMA` (the path of the schema its JSON answer must match: `answer`, `reason`, and
  `evidence` where the answer asks for it) and `RAIL_TRIAGE` (the type). The worktree is put back afterwards.
- **An answer that lets the change through** is an `answered` event, and the ticket goes on. Where the type
  asks such an answer for evidence, the engine checks what it can: a quoted contract line is in the ticket, a
  named file is in the change. The event's `evidence_ok` says how the check went.
- **An answer that stops the change** fails the step `triage`. The ticket is `implementing` again, and the
  worker's brief (`STEP_FAILED`) holds the question, the fact, the answer with what it means, the run's reason
  and what to do; `action.facts.triage` has the same as values. The failure counts toward the retry budget
  like any failed step (`rail docs retries`), and two stops by the same answer to the same type are the same
  failure. Nothing goes to the refuter: a second run on the first one's answer is not added.
- **The next patch** is asked again only if the fact still holds. The same patch shipped again keeps its
  stopping answer, and `triage` fails with no run, unless `rail amend` changed the contract since: the contract
  is part of what was asked, so the question is raised once more.
- **No answer.** A run that passes `timeout_secs`, answers with something the schema does not allow, or names
  evidence that is not where it says, fails `triage` with `counted: false`: it is the run's fault, and no
  attempt of the author's is spent. The run is started once more. Two in a row wait for a person
  (`STUCK_REVIEW`, as for a review with no verdict), who looks at why and continues with `rail accept NN`.
- **CI** fails at `triage` while a question about the head's patch is open, or answered with what stops the
  change, as it fails at `review` while the review is not complete.

## The question types

The table is `QUESTIONS` in `.rail/engine/rail/triage.py`. An entry holds the type's id, the fact that raises
it, the question, what the brief shows, two to four answers with what each means and whether the ticket then
goes on or stops, and, for an answer that lets the change through, the evidence it must name and the engine's
check of it.

This engine has no type yet, so no question is raised.

## What to read in the numbers

`rail stats` has a `TRIAGE` table (`rail docs stats`): for each type the questions asked about the merged
tickets' patches, the runs, the runs that gave no answer, what the runs reported they cost, and each answer's
share. The sweep (`rail docs sweep`) names a type whose last 20 answered questions got the same answer 19
times or more. Such a type is no longer a question: it is a rule the engine can apply with no run, and the
sweep's ticket makes it one or removes the type.

The prompt and the briefs of this step have not been tested with a model run.
