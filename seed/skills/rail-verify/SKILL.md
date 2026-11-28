---
name: rail-verify
description: Write or improve a project's verify command and a check that drives the real product, so that done is decided by commands. Use when setting a project up for Rail, or when a ticket asks for better verification.
---

# Build the project's verification

- **Assumes:** you are setting a project up for Rail (the init task), or a ticket asks you to improve how
  the project is verified.
- **Produces:** the checks in `.rail/config.toml` (a `[[projects]]` entry where a project's own commands belong
  in the default's place or where no manifest marks the project, and `[commands] verify` for the whole
  repository), and, where the product can be run, one check that drives it the way a user would.
- **Done means:** you ran each part and saw it pass, and you saw each part fail on a mistake you planted
  and then removed.

Rail decides "done" by commands. Everything a command can't see is left to the reviewer or to a person, so
this is where a project gains or loses the most.

## 1. Ask the repository, not the person

Read the manifests, the CI workflows, the Makefile or task runner and the README. Use the commands the
project already declares for tests, lint, types, a secret scan and a dependency scan.

<!-- Not tested with a model run: the next two paragraphs. -->
Rail finds the repository's projects from its tracked manifests and gives each its language's default `setup`
and `verify`, run in the project's folder: `rail doctor` prints them. Where a project declares its own command
for a part, write a `[[projects]]` entry with that project's name and the `verify` or `setup` to run instead.
Where it declares none, keep the default and say so in the pull request. Beyond that, don't invent a command the project doesn't have: say it is missing, and
propose a ticket for it.

A folder no manifest marks, such as infrastructure code, gets an entry with a new name: its `paths`, and the
checks its kind of file has (a formatter, a validator, a linter, tests). `[commands] verify` holds only what
belongs to the whole repository, such as the secret scan.

## 2. Show that each part bites

For each part of each `verify`, plant one mistake it should catch, run it, see it fail, and remove the mistake.
A check you have only seen pass may be unable to fail.

## 3. Drive the real product

Tests show the code. One check should show the product. Write a script that:

1. starts the product the way a user does;
2. checks first that the environment is ready, changing nothing;
3. takes one real path through it and captures what came out;
4. cleans up, and leaves the captured output in place.

How this looks depends on the product: an HTTP call for a service; a command and its output for a CLI;
`blender --background --python check.py` for a Blender add-on, with a check on the scene it produced;
`ffprobe` on a rendered file for a video pipeline, with checks on duration, codec and loudness.

## 4. Say how far each claim was proven

Use these levels, and name the highest one you reached: read the source, built it, installed it, ran it
live, took a whole user path. Write the rest as "not tested". A feature with no check is written down as a
gap, so the next ticket can close it.

## 5. Keep it fast enough to run every time

`verify` runs at every ship and in CI. Keep it under `[commands] verify_timeout_secs` (`timeout_secs` when that
is 0). When the full suite is too slow, put the fast part in `verify` and name the slow part in a `Check:` line
of the tickets that need it.
