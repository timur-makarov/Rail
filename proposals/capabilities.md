# Tools, secrets and grants: what could be built

This page is a proposal. None of it is implemented. It says how the agents Rail works with get the tools,
MCP servers and secrets their work needs, and how each limit the machine meets becomes something a person
grants once. Status: written 2026-11-24. The owner approved the direction. Three Claude Code behaviours it
depends on were tested that day; the results are below. Each claim is marked *tested*, *docs* (Claude
Code's documentation, read that day) or *not verified*. A fresh agent read the draft against the engine's
docs and code, and its findings are folded in.

## The principle

A person serves the machine. They set things up once and give the machine what it needs to work well: an
identity, keys, permissions, tools. So every limit the machine meets becomes a **grant**: a named act a
person does once, after which the machine can do the thing until the grant lapses (a key expires, a token is
revoked). `rail doctor` lists every grant the machine has and every one it lacks, and a request for a grant
names it exactly. A grant is never replaced by a workaround, and it never turns into a chore the person
repeats.

`rail docs environments` lists four acts people keep: merging a PERSON ticket, deleting data, handling
credentials and releasing to prod. A grant is how the third is done: once, named, and listed. The other
three, and approving a PERSON ticket's contract, stay as they are.

Which layer each part belongs to: the tools themselves, and how to use them well, are craft and belong to
the project. Rail's part is the rail: declaring what exists, putting it in front of every agent that needs it,
and telling a missing grant apart from a bad change.

**Two terms.** A **wait** is a ticket whose owner is a person (`owner: human`), as today. A **grant request**
is a repository-level issue for something the machine lacks; it belongs to no ticket.

## What was tested

**The reviewer can't get MCP tools under `--safe-mode`** (*tested* on Claude Code 2.1.292 locally and 2.1.331
in a cloud session). `claude -p --safe-mode --mcp-config FILE` loads no server from `FILE`. These flags
isolate the run as well, load the server, and let the run call its tool:

```text
--setting-sources "" --disable-slash-commands --strict-mcp-config --mcp-config FILE --allowedTools mcp__probe__ping
```

The test project had a canary word in `CLAUDE.md`, a project skill and a project Stop hook. With these flags
none of them reached the run, and the plugin skills were gone too; a plain `claude -p` loaded all three.
Signing in worked as usual. The tool was allowed by its full name; whether a server-level name
(`mcp__probe`) allows all of a server's tools is *not verified*.

**A network secret reaches every process that uses the session's proxy** (*tested* in a cloud session, with a
dummy value on `httpbin.org`, which echoes the headers it gets). The value is never in the environment.

| Process | Got the secret |
|---|---|
| curl; Python's urllib | Yes |
| curl run by a child `claude -p` (the reviewer's situation) | Yes |
| An MCP server that a child `claude -p` started | Yes |
| curl with a cleared environment (`env -i`) | No |
| Node's built-in `fetch` | No |

The proxy works through `HTTPS_PROXY` and related variables, so a process that ignores them gets nothing.
The engine passes its whole environment to the commands it runs (`engine/rail/util.py`, `run_shell`), so
`setup`, `verify`, the checks and the reviewer all get the secret.

**The proxy replaces a placeholder.** When a process sends its own `Authorization: Bearer placeholder`, the
host receives the network secret instead (*tested*). A command-line tool that refuses to start without a
token can be given a dummy one.

**Who can read what in the cloud** (*docs*, code.claude.com/docs/en/cloud-environments.md):

- An environment's **variables** are readable by anyone who uses the environment, and by every command the
  agent runs, so one `env` puts them in the transcript, and a shared transcript shows command output. A
  personal environment is used by its owner and the people it is shared with; an organisation-shared one by
  every member, and only Owners edit it. Scheduled tasks use an environment too. The setup script runs
  before the variables are set, and what it writes to disk is kept in the cached snapshot.
- A **network secret** never enters the machine and can't be read back after it is saved. The proxy adds it
  as a header (`Authorization: Bearer` by default; any header name and prefix) to requests for the hosts
  listed on it, in every session in the environment, whoever starts it, and those hosts are reachable even
  when the environment's network level wouldn't allow them. It doesn't apply to the setup script, to GitHub,
  `api.anthropic.com` or the public package registries, or to MCP connectors (they run on Anthropic's
  servers). The owner of a personal environment manages its secrets; Owners manage a shared one's.
  Organisations with customer-managed keys, and self-hosted environments, have none.

## Part 1: tools and secrets

### 1. Declare a tool once

A tool is anything outside the repository an agent or a command needs: a docs service such as context7, an
internal API, a secret manager. It is declared once, in `.rail/config.toml` (the hosts and probes below are
illustrations, not checked against the real services):

```toml
[tools.billing-api]
use = "Billing service sandbox. Check a request's shape with bin/billing or docs/billing.yaml before changing a billing call."
hosts = ["billing.sandbox.example.com"]   # its key is a network secret for these hosts
probe = "bin/billing ping"                # fast, changes nothing, exits 0 when the tool works
review = false                            # true: read-only, so the reviewer, refuter and consult load it too

[tools.context7]
use = "Current docs for a library at the version in the lockfile. Look a library up before writing or flagging code against its API."
hosts = ["mcp.context7.com"]
probe = "curl -fsS https://mcp.context7.com/ >/dev/null"
review = true
```

- `use` says what the tool is and when to use it, in one line. It is the only text agents see.
- `env` lists the names of environment variables the tool needs, for a value a process must hold itself.
  `hosts` lists the hosts the tool calls; in the cloud a network secret covers them. A tool has `env`,
  `hosts`, both or neither. Rail never holds a value.
- `probe` is a command, run the way `verify` runs, that shows the tool works. It must use the same client
  as the project: a curl probe passes while the project's Node code, which ignores the proxy, gets nothing.
- An MCP server stays in `.mcp.json` under the tool's name, as Claude Code expects. List it in
  `enabledMcpjsonServers` in `.claude/settings.json`, so an unattended run never meets the prompt that
  approves it (*not verified* in a cloud run).
- The seed config ships one commented example and no tool.
- A new outside connection is a PERSON ticket. `.rail/config.toml` is on the seed's `person_paths` already;
  `.mcp.json` joins it.

### 2. What the engine does with the declaration

**The brief.** `next` and `advance` list the tools in every brief, by name and `use` line. A review brief
lists only the tools marked `review = true`.

**A missing name stops work on that machine.** Checking that every `env` name is set costs nothing, so
`rail next` does it before it claims a ticket or ships one. `verify` runs for every ticket, so a name the
project's tools need is needed by every ticket, and the engine can't tell which tickets need which tool
without a per-ticket field (left out below). When a name is missing, `next` claims and ships nothing,
still moves shipped tickets through CI and the merge, and answers `NEEDS_GRANT` with the name and where to
set it.

- In a cloud session or in CI, it also opens a **grant request**: an issue titled `Rail needs: NAME`, with a
  marker line `<!-- rail-grant: tools.NAME -->` and the label `rail:needs-you`. Before opening one it lists
  the open issues with that label and looks for the marker, so there is never a second one. It closes the
  request when a later `next` finds the name set. The engine then reads `rail:needs-you` for the first time
  (`forge.py` says it never does), only to find its own marker.
- On a person's own machine it opens no issue: a name set in the cloud and missing on a laptop would open
  and close one by turns. The answer and `rail doctor` say what is missing.
- The label starts one runner run, through the "issue labelled" trigger, which has no filter. That run finds
  the name still missing and ends at its first `rail next`.

**A broken tool is an environment fault, not the change's failure.** When `verify` or a check fails at
ship, the engine runs the probes, in the ticket's worktree and in a checkout of the base branch. A probe that
fails in both says the machine lacks something:

- the step is recorded as `environment_fault` (a new journal event with the tool, the probe and its output's
  tail), spends no attempt and doesn't move the model ladder;
- the ticket waits (`owner: human`, reason `NEEDS_GRANT`), and a grant request opens as above;
- each `next` runs that one probe again for the waiting tickets, and when it passes the ticket goes back to
  the agent with its attempts as they were. No `rail accept` is needed.

A probe that passes on the base and fails in the worktree says the change broke the tool. That is the
change's failure, counted as today; the brief says which probe broke. A probe that passes in both leaves the
failure to the change, as today. Probes run only after a failure, so they cost nothing when everything
passes, and an expired key no longer looks like bad code. A network secret is invisible to the engine, so its
probe is the only way to know it works.

**The engine's agents load the read-only tools.**

- Before each review, security, refuter or consult run, the engine writes an MCP config holding the
  `.mcp.json` servers of the tools marked `review = true`, with `${VAR}` expanded by the engine itself. It
  writes it outside the worktree (a temp file, mode 0600, removed after the run), because the review's
  clean-up removes untracked files in the worktree.
- It passes the path as `RAIL_MCP_CONFIG` and the allow list as `RAIL_MCP_TOOLS` (`mcp__NAME__TOOL`
  names, comma-separated), as it passes `RAIL_MODEL` today. The command decides what to do with them, so a
  command for another agent (Codex, Antigravity) uses its own flags or none.
- The seed `[review]` and `[consult]` commands change from `--safe-mode` to the tested flags:

  ```text
  claude -p --setting-sources "" --disable-slash-commands --strict-mcp-config --mcp-config "$RAIL_MCP_CONFIG" --allowedTools "Bash,Edit,Write,$RAIL_MCP_TOOLS" ...
  ```

- A project set up earlier keeps its copied command: after `rail init` every file is the project's. It
  takes the change the way it takes any later framework change, through a PERSON ticket.
- The tool names are listed by the engine because it reads each server's tools when it checks the config
  (`rail doctor` does the same). How the engine lists them without running an agent is *not verified*; the
  fallback is a server-level name, if `mcp__NAME` turns out to allow a whole server.

**A network secret reaches the reviewer anyway.** Every process that calls a listed host gets it, so
`review = false` can't keep a key away from the engine's agents. Keys held as network secrets are read-only
or test keys.

**Network access is a grant too.** On a person's machine, a sandboxed command reaches only
`sandbox.network.allowedDomains` (the seed allows `api.anthropic.com` alone). `rail doctor` compares each
tool's `hosts` with that list and names the hosts to add. In the cloud, a host covered by a network secret is
reachable at any network level; a tool that uses only `env` needs its hosts on the environment's allowlist,
which the engine can't read, so its probe shows it and the grant request names the hosts.

**CI never needs editing.** `rail.yml` passes `${{ toJSON(secrets) }}` to the job once, as `RAIL_SECRETS`.
`rail ci` reads it, exports only the declared `env` names, and removes `RAIL_SECRETS` from the environment
before it runs any command, so no undeclared secret reaches `verify` or a check. A pull request that gets no
secrets (Dependabot's, a fork's) fails with the names it lacks, not with a test's error. The workflow's
comment "CI runs no model, so it needs no secrets" changes with it.

**`rail doctor`** shows each tool: every name set or missing, its hosts against the sandbox list, and the
probe's result. For a missing value it prints where it goes: the cloud environment's settings, GitHub's
secrets page (the link built from the remote), or the shell.

### 3. Where a secret lives

One name everywhere: the cloud environment, GitHub's secrets and the shell use the same variable name, so
nothing is mapped from one to the other.

| What it is for | Cloud session | CI | Own machine |
|---|---|---|---|
| A key an HTTP API reads from a header (context7, an internal API) | Network secret | GitHub secret | Shell or keychain |
| A value a process must hold (a test database password, a key that signs requests) | Environment variable, dev values only | GitHub secret | Shell |
| Many secrets, rotation, the same secrets in many repositories | A secret manager (4) | The manager, through GitHub's OIDC token | Your own login to the manager |

A network secret can't sign a request, so a signing key (AWS SigV4, for one) is in the second row or comes
from a manager. Environment variables in the cloud are readable by every person and agent of the
environment, which is why they hold dev values only, as `rail docs environments` already says.

### 4. A secret manager, when one is needed

Rail never talks to a secret manager. The person grants one starting credential, and the manager supplies
the rest:

```toml
[commands]
secrets = "op run --env-file .rail/secrets.env --"   # or doppler run --, a vault or aws wrapper
```

- The engine puts `secrets` in front of every command that may need a key: `setup`, `verify`, each check
  and each probe. The values live in that command's process, not in the agent's shell.
- In a cloud session the starting credential is a network secret for the manager's host, so its value never
  enters the machine either; the manager's tool gets a dummy token, which the proxy replaces (*tested* with
  curl and Python, *not verified* with a real manager's tool).
- In CI, GitHub's OIDC token can stand in for the starting credential with managers that accept it, so
  nothing is stored. On the person's own machine, their own login to the manager.
- Bringing a manager in is an ordinary ticket. Rail needs no code for any one manager.

### 5. Mask secrets before anything is stored

This closes a gap that exists today. The engine stores what commands print: the tail of a failed step in the
brief and the journal event, the reviewer's quoted evidence and the engine's re-run of it, consult's advice
(`NN-advice.md`), the sweep's summary, pull request bodies and issue comments. The journal is committed, so a
test that prints a key keeps it in git for good.

- The engine masks at one place: where it captures a command's output (`run_shell`), the review, consult
  and sweep runs included. Every value of a declared `env` name it can see, and of each name `rail ci`
  exported, becomes `***` before anything else reads the output.
- Values shorter than 8 characters are not masked, because masking them would mangle ordinary output;
  `rail doctor` warns about such a value.
- What the engine can't see, it can't mask: a value only the `secrets` wrapper fetched (masked by the
  manager or not at all; `op run` masks by default, *not verified*), and a network secret that a service
  echoes back (httpbin did, in the test). Probes and checks shouldn't print response headers.

### 6. Finding and adding tools

- **At setup** the init task builds candidate tools from what the repository already declares: the servers
  in `.mcp.json`, the names in `.env.example`, and the `secrets.X` names in the CI workflows. It writes the
  declarations and probes into the setup pull request and lists the values a person must set.
- **Later**, a `rail-tool` skill adds one: declare it, choose where its secret lives (3), write a probe in the
  project's own client and show it fails without the key, add the server to `.mcp.json` with a pinned
  version, and list the values for the person. The grill skill points to it when a request needs a system
  outside the repository.

## Part 2: grants in place of workarounds and chores

These are the places where Rail breaks the principle today.

### 1. A machine identity

The runner works under one person's GitHub login. That person can't approve its pull requests, GitHub
doesn't notify them (`rail docs cloud` sends them to a saved search instead), and only one person can own the
runner (`proposals/team.md`, 3 and 3a).

- **Grant:** a machine account with a fine-grained token scoped to the one repository (contents, pull
  requests, issues). A GitHub App's key can't be used directly: it signs a short-lived token every hour,
  which would be engine code.
- **Where it lives:** an environment variable, `GH_TOKEN`, in the cloud environment. A network secret can't
  hold it, because network secrets don't apply to GitHub. That makes it readable by everyone who uses the
  environment, and it is not a dev value.
- **Build:** the engine records who asked for each ticket in its pull request, since the author no longer
  says it. `rail doctor` shows which identity the runner uses and when the token expires.
- **Not verified:** that a `GH_TOKEN` you set makes the pull requests the engine opens through `gh api`
  carry the machine account. The docs say such a token passes through to the container, and that the GitHub
  proxy still refuses GraphQL with it. Pushes go through the proxy, whose identity this doesn't change.

### 2. Sources run from the one runner

Each source needs its own scheduled task today, made by hand in the UI, so every new source is a chore.

- **Build:** a source's front matter says how often it runs (`every = "1d"`). In a cloud session, `rail
  next` offers a source that is due once no ticket work waits, as it offers the sweep. A run claims a due
  source by moving a commit on a branch the engine owns, `rail/sources`, as `add` claims an ID on
  `rail/ids`: when two runners race, the second push is refused and that runner moves on. A person's own
  machine runs sources only with `rail source NAME`.
- **The runner prompt** changes at step 2: an `agent_task` with no ticket (a source's or the sweep's brief)
  is done by a subagent, and the runner goes back to step 1 with no `rail advance`.
- The runner's own schedule trigger reaches a due source when no event comes. `rail docs sources` ("The
  engine schedules nothing") changes with it.
- **Cost:** one field, one branch and one offer in `next`. Small.

### 3. A missing tool is a grant request, not an attempt

A command that couldn't start (`could_not_run`) spends an attempt today, so that a missing tool can't loop
for ever (`rail docs retries`), and a missing tool ends in a generic `RETRY_CAP` wait after several runs.

- **Build:** `could_not_run` follows the environment-fault rule in Part 1, 2. The engine runs the same
  command in a checkout of the base branch. When it can't start there either, the machine lacks the tool:
  the ticket waits with `NEEDS_GRANT`, spending no attempt, and the next `next` tries the command again.
  When it starts on the base, the change removed or broke it, which is the change's failure, as today.
- The wait itself stops the loop that counting attempts used to stop.
- In a cloud session, where the agent is root, the brief first asks the agent to install the tool and file a
  ticket that adds it to `provision`; the ticket waits only when the agent can't.

### 4. The engine's agents get read-only tools

Covered by Part 1, 2.

### 5. A wait says what kind of act it needs

A person can be asked for three different things, and today every wait has the same label and a free-text
brief. Each reason code gets a kind:

| Kind | Means | Reason codes |
|---|---|---|
| grant | Once, and the machine can do it until the grant lapses | `NEEDS_GRANT` (new) |
| approval | The PERSON tier's deliberate check | `APPROVE_CONTRACT`, `APPROVE_AMEND`, `MERGE_BY_PERSON` |
| decision | A judgment the machine couldn't make | `RETRY_CAP`, `FINDING_UPHELD`, `STUCK_REVIEW`, `MERGE_FAILED` |

`HOLD` has no kind: the person stopped the ticket, and nothing is asked of them.

- **Build:** the kind is in `rail next --json`, in the wait's brief and in the pull request or issue. A
  grant is answered by giving it, and the engine sees that by itself; approvals and decisions are answered
  as today (`rail:go`, a comment, the merge button, `rail accept`).
- `rail doctor` lists the grants held and lacking. A grant, once given, comes back only when it lapses, and
  then the request names that.
- **Cost:** a field on each wait and the table above. Small.

## Decisions for the owner

1. **The machine identity's token** (Part 2, 1) lives in an environment variable that everyone who uses the
   environment can read, and a fine-grained token expires, so it must be renewed. Accept both, or keep the
   runner under a person's login for now.
2. **Applying GitHub settings from the engine.** It would remove the manual ruleset import and repair drift,
   but the cloud refuses writes to settings and rulesets (`rail docs cloud`), so it could only run from CI or a
   person's machine; with admin rights the machine could change its own wall; and the setup is a one-time
   act of a few minutes, which the scope rules say to skip. My recommendation: don't build it; keep
   `rail doctor` checking and linking each page.
3. **A missing name stops all claims on that machine** (Part 1, 2). The alternative is a per-ticket `needs:`
   field. My recommendation: stop all claims, since `verify` runs for every ticket, and add `needs:` only if
   machines come to hold different keys.
4. **Masking skips values under 8 characters** (Part 1, 5). Any length is a choice; 8 is mine.

## What I would not build

- Installing on a person's own machine. `provision` installs as root on a machine made for the work and is
  written for the cloud's Linux image; on a person's machine it would need `sudo` and a second, per-system
  install command. Installing a tool there is a few minutes, once.
- Counting tool use in `rail stats`. The engine can record which tools a run was offered, not which it used,
  and it can't see a worker subagent's calls at all.
- A catalog of known integrations, or a pack for any one tool or manager.
- A Rail-side registry of MCP servers: `.mcp.json` is the standard.
- A table of which tool each role may use, beyond `review`.
- Secret rotation, or a secret store inside Rail.
- A per-ticket `needs:` field, until machines differ in what they hold.
- Running every probe on every `rail next`.

## Not verified

- Whether `enabledMcpjsonServers` keeps an unattended cloud run from stopping at an MCP approval.
- Whether a server-level name (`mcp__NAME`) in `--allowedTools` allows all of a server's tools, and how the
  engine lists a server's tools without running an agent.
- How a real manager's command-line tool behaves with a dummy token and the proxy.
- Whether `op run` masks values in its output.
- Whether a `GH_TOKEN` you set makes the engine's pull requests carry the machine account (Part 2, 1).
- Which Node versions can be told to use `HTTPS_PROXY`, and how.

## Suggested order

1. The declaration with brief lines and `rail doctor`, and masking (Part 1: 1, 2, 5). Masking closes a gap
   that exists today.
2. Environment faults and `NEEDS_GRANT`: missing names, failing probes and `could_not_run` (Part 1: 2;
   Part 2: 3), with the grant requests.
3. The engine's agents with read-only tools, and the new seed commands (Part 1: 2). The flags are tested.
4. CI secrets through `RAIL_SECRETS` (Part 1: 2).
5. Discovery at setup, and the `rail-tool` skill (Part 1: 6).
6. Wait kinds (Part 2: 5), then sources from the runner (Part 2: 2).
7. The machine identity (Part 2: 1), after the owner's decision and a cloud run that shows how it is used.
8. The `secrets` wrapper (Part 1: 4), when a project first needs one.
