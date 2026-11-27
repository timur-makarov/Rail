# Driving the product

A ticket's checks can pass on code that still does not work once the product is started and used. A project
can tell Rail how its product is started and how users reach it, and then ship and CI start the product, drive
it, stop it, and keep what they saw.

A project that sets none of this works as before: there is no product step, and no line about one.

## The config

```toml
[product]
start = "scripts/start.sh"        # starts the product and returns
ready = "scripts/ready.sh"        # exits 0 once the product answers; changes nothing
seed = "scripts/seed.sh"          # loads test data and the test identity from files in the repository
stop = "scripts/stop.sh"          # stops what start started
ready_secs = 120                  # how long ready may take before the product counts as not started

[[surfaces]]
name = "web"
kind = "web"                      # web, api, cli, agent, data, integration or mobile
projects = ["frontend", "backend"]
check = ".rail/checks/web.sh"     # the script that drives this surface
```

A surface is one way users reach the product: a web page, an HTTP API, a command line, an interface built for
agents, a data set, an integration with another service, a mobile app.

- **`[product]`** commands run in the ticket's worktree, with `RAIL_TICKET` and `RAIL_BASE` set. Two tickets
  can be at work at once, so `start` takes a port and a database of its own, from `RAIL_TICKET` or by asking
  the system for a free port and writing it where `ready` and the checks read it. Every key may be empty. A
  `cli` or `data` surface often needs no `start`: its check runs the built program itself.
- **`start` returns.** It puts the product in the background and exits. The engine sends what `start` and the
  product print to a file, so a product left running does not hold the step.
- **`projects`** names projects of the repository (`rail docs languages`). A change that reaches one of them
  reaches the surface. A surface with no `projects` is reached by every change. A changed file inside no
  project reaches every project, and so every surface.
- **`check`** is the path of a script in the repository, from its root. It has to be executable. It gets
  `RAIL_EVIDENCE`, an empty folder to write what it saw into, and `RAIL_SURFACE`, the surface's name. It finds
  the product where `start` put it.
- **`kind`** is one of the seven. The engine reads no other meaning into it than the lines of
  `rail doctor` below.
- **A driving check is a test.** Its path counts as one of `[tests] paths` for as long as its surface names
  it, with nothing written into the config. A ticket that edits a check script is held against the base
  branch's version of it (`rail docs triage`).
- An unknown key or kind is refused when the config is read, like any unknown key.

## The product step

The step is the last of the checks ship and CI share (`rail docs loop`), after `verify`, the `Check:` lines
and the sensors: it is the dearest, so everything cheaper has passed. It runs when the change reaches at least
one surface.

1. `start`, then `ready` every half second until it exits 0 or `ready_secs` pass, then `seed`. This is the
   step `product`.
2. For each surface the change reaches, its `check`. Each is a step of its own, `product:NAME`.
3. `stop`, always, whatever failed. Afterwards the engine ends every process `start` left running.

A failed driving check counts like a failed `Check:` line: it moves the retry budget and the cap as any step
does (`rail docs retries`), and the next brief carries what the check printed.

**When the product does not start.** When `start` or `ready` fails, the engine starts the product once on the
base branch, in a throwaway worktree. If it does not start there either, the attempt does not count, the step
says `red base`, and `rail next` files one ticket that makes the product start on the base again; the ticket
waits for it (`RED_BASE`), as it does when `verify` fails on the base. If only the ticket's branch fails, the
failure is the ticket's. A command the shell cannot find checked nothing and costs no attempt. A failure while
a declared tool is out of reach costs none either (`rail docs tools`). The brief of a failed start carries
what `start` and the product printed.

`rail ci` runs the same step on the pull request's head. `[commands] provision` installs what it needs on the
runner (`rail docs cloud`).

A driving check that fails is not run a second time, so the engine does not tell a flaky one from a broken one.

## Evidence

Each driving check writes what it saw into `$RAIL_EVIDENCE`: the steps it took, requests and responses, a
command with its output and exit code, and for a web page screenshots or a trace.

- **Text is kept in the journal.** Each text file is kept up to 64 KB, and a surface up to 256 KB in all; a
  longer file is cut there and says so. The files of the last shipped patch are in `NN-evidence.json`
  (`rail docs journal`), committed with the step's events. Only the engine writes the journal, so the worker
  cannot rewrite what the product did.
- **Secrets are named, not kept.** Before anything is committed, the value of each environment name a
  `[tools.NAME]` declares (`rail docs tools`), and of each entry of a `.env` file in the worktree with four
  characters or more, is replaced by its name in brackets, as `[PAY_TEST_KEY]`. A secret the project never
  declared is not caught. Evidence should hold test identities and test-mode responses only: a committed
  secret cannot be taken out of history.
- **Anything else is never committed.** A screenshot, a trace or a recording stays on the machine, under
  `.git/rail/cache/evidence/NN/NAME/`, until that surface is driven again for the ticket. The journal names
  the file. What `start` and the product printed is beside it, in `start.log`.
- **In CI** `rail ci` writes nothing into the repository. When `RAIL_EVIDENCE` is set for it, the evidence
  folders go there, one for each surface, and the seed workflow uploads that folder as the artifact
  `rail-evidence` of the run.
- **The pull request's Evidence table** has a row for the start and one for each surface, such as
  `product:web | ran, pass: 3 evidence files, 2 more left on the machine`.
- **The reviewer's brief** carries the text evidence of the patch it reviews, up to 16 KB a surface, so that
  what the change says it does can be held against what the product did. The reviewer can also run a check
  itself. The brief's wording for this has not been tested with a model run.
