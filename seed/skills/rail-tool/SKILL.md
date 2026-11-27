---
name: rail-tool
description: Add a tool to a project that runs on Rail (a service with a key, a CLI that signs in, an MCP server), declared so that every agent is told of it and a missing key stops a ticket before work is wasted on it. Use when a ticket adds or changes a tool, or when a request needs a service the project has not declared.
---

<!-- Not tested with a model run: this whole text. -->

# Add a tool

- **Assumes:** the work needs something outside the repository that the project has not declared: a service
  with a key, a CLI that signs in, an MCP server.
- **Produces:** a `[tools.NAME]` table in `.rail/config.toml` with a probe you ran, the tool's names in every
  file that reads them, and a list of what a person has to set, each with the place.
- **Done means:** the config loads, `rail doctor` has a line for the tool, and you saw the probe fail with
  the key taken away. Where this machine has the key, you also saw it pass.

You write the declaration. A person gives each machine its key. You never ask for a key's value, read one or
write one: only its name goes into a file.

## 1. Is it a tool, and is it new

It is a tool when the work reaches it outside the repository and it can be out of reach or refuse: an API
with a key, a CLI that has to be signed in, an MCP server. A program that a command installs and that needs
no credential is not one: it belongs in the project's `provision` or `setup` command.

Read `[tools]` in `.rail/config.toml` first. Where the service is declared already, change that table; don't
declare one service twice under two names.

## 2. One ticket for the tool

The tool gets a ticket of its own, with nothing in it that uses the tool. A ticket that needs the tool names
this one in `after`.

- Its scope is `.rail/config.toml`, and each other file from section 5 that it changes.
- It is a PERSON ticket: `.rail/config.toml` and the workflows are paths only a person merges.
- Its `Check:` lines read the declaration, not the service. A check that calls the service fails in CI unless
  the tool is `ci = true`, and on every machine that has no key yet.

## 3. The declaration

```toml
[tools.payments]
use = "The payment service in test mode: create customers and charges in checks"
env = ["PAY_TEST_KEY"]
probe = 'curl -sf --oauth2-bearer "$PAY_TEST_KEY" https://api.example.com/v1/balance >/dev/null'
review = false
ci = false
```

- **The name.** For an MCP server, the name it has in `.mcp.json`. For a CLI, the program's name. Otherwise
  one short word for the service. Rail counts which runs used a tool by this name.
- **`use`** is one line that every agent reads in its brief: what the tool is for, and its limit ("test mode
  only", "read only").
- **`env`** lists the names of the variables the tool reads, the same on every machine. A tool whose key a
  cloud environment's network proxy adds to requests has no variable: leave `env` out and rely on the probe.
- **`review = true`** only when the reviewer has to read from the tool to judge a change.
- **`ci = true`** only for a key whose leak is undone by rotating it and costs nothing meanwhile: a test-mode
  or dev key. A ticket's branch can read every key a pull request's run is given. When you can't tell which
  kind the key is, leave it `false` and ask the person in the pull request.

## 4. The probe

A probe is one command that says whether the tool can be reached from this machine.

- It exits 0 only when the service answered with the credential accepted.
- It changes nothing there: read a balance, ask who is signed in, list one record.
- It is fast. It has 60 seconds; aim for a few.
- It reads the key from its variable and prints nothing: send output to `/dev/null`, and pass the key in a
  header, never in the URL.

For a CLI, the command that says who is signed in is usually enough. For an MCP server, probe the service
behind it; when nothing can be asked without a session, leave the probe out and say so.

Run it both ways. With the variable unset it has to fail: `env -u PAY_TEST_KEY bash -c '<the probe>'`. With
the key set it has to pass. When this machine has no key, you saw one half only: say that in the pull
request, so that a person runs the other half.

## 5. The name in each place

One name, spelled the same, in each place that applies.

| Place | What goes there | Whose act |
|---|---|---|
| `.rail/config.toml` | the `[tools.NAME]` table, with the name in `env` | yours |
| `.env.example` | the name with no value, and a comment that says where a person gets a key | yours |
| `.worktreeinclude` | the line `.env`, when the project keeps keys there and the line is missing | yours |
| `.mcp.json` | for an MCP server: the server under the same name, reading the key from the variable | yours |
| `.github/workflows/rail.yml` | for `ci = true` only: one line for the name (section 6) | yours |
| A person's own machine | the value, in the shell that starts the agent or in the project's `.env` | a person's |
| The cloud environment | the value, as an environment variable in the environment's settings | a person's |
| The repository's Actions secrets | for `ci = true` only: the value | a person's |

A key that is not `ci = true` goes into no workflow a pull request starts. Where a deploy needs one, it lives
in a GitHub environment that only the base branch may deploy to, and the job that needs it names that
environment.

## 6. The line in `rail.yml`

For each name of a `ci = true` tool, add one line under the `env` of the step that runs `rail ci`:

```yaml
        env:
          RAIL_BRANCH: ${{ github.head_ref }}
          PAY_TEST_KEY: ${{ secrets.PAY_TEST_KEY }}
```

Pass each key by its own line. Never pass every secret at once, with `toJSON(secrets)` or
`secrets: inherit`: the ticket's branch runs its own copy of this file. `rail doctor` checks these lines in
`pull request secrets`: run it and read that line.

## 7. Close

- Run `rail doctor` and read the tool's line: its names, set or not, and the probe's result.
- In the pull request, write for the person who merges it: each thing they set and where, from the table;
  which half of the probe you saw; and why `ci` is what it is.
- Tell them the order. Once the declaration is on the base branch, a machine without the key claims no
  ticket: `rail next` answers `TOOL_MISSING` there until the name is set. So the keys go onto the machines
  before the merge, or straight after it.
