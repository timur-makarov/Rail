# Tools

A tool is anything the work reaches outside the repository: a service with a key, a CLI that signs in, an MCP
server. A project declares each one in `.rail/config.toml`, so that every agent is told what it may use, and a
missing credential stops a ticket before any work is wasted on it.

```toml
[tools.payments]
use = "The payment service in test mode: create customers and charges in checks"   # what the agents read
env = ["PAY_TEST_KEY"]             # names only, never values; the same name on every machine
probe = 'curl -sf -u "$PAY_TEST_KEY:" https://api.example.com/v1/balance >/dev/null'   # fast, changes nothing
review = false                     # true: the reviewer, the refuter and consult are told of it too
```

- `use` is needed: one line saying what the tool is for.
- `env` lists the names of the variables the tool needs. A value never goes into the config: an entry that
  is no variable name is refused, and the refusal doesn't repeat it.
- `probe` is a command that exits 0 when the tool can be reached and changes nothing there.
- An MCP server stays in `.mcp.json` under the same name; `[tools.NAME]` adds what the engine reads.

`.rail/config.toml` is in `person_paths`, so a ticket that adds or changes a tool is a person's to approve.
Giving a machine a key is a person's act too.

## What the engine does with a declaration

**Briefs list the tools.** The implement brief lists every tool with its `use` line and the names it reads.
The briefs of the review, the security seat, the refuter and consult list only the tools with `review = true`,
and say they are for reading. A value is never in a brief.

**A missing name stops before the claim.** Before a ticket is claimed, each `env` name of every tool must be
set on the machine: in the environment, or with a value in the `.env` at the project's root (the engine reads
that file's names, never its values). While one is missing, `rail next` answers `TOOL_MISSING`, a person's
wait: nothing was tried, so no attempt is counted. It is one wait however many tickets it holds. A ticket
already under way goes on. The brief says where the name is set on that kind of machine: the cloud
environment's variables, the repository's Actions secrets, or the shell and `.env` on a person's own machine.

In a cloud session nobody reads the answer, so the engine opens one issue per tool, labelled
`rail:needs-you`, and closes it when a session finds the name set. No ticket's pull request is labelled for it.

A key that a cloud environment's network proxy adds to requests never shows up as a variable. A tool reached
that way declares no `env` and relies on its probe.

**`rail doctor` shows each tool:** its names, set or not, where to set a missing one, and the result of its
probe. A probe is not run while a name is missing.

**`rail init` names candidates.** The init task lists the MCP servers in `.mcp.json`, the names in
`.env.example` and the secrets the workflows in `.github/workflows` read, and asks for a declaration of each
one the work uses.
