---
name: rail-grill
description: Turn a request for new work into a Rail ticket by questioning the person who asked, before rail add. Use when someone asks for a feature, a fix or a change in a project that runs on Rail.
---

<!-- include engine/docs/grill.md -->

In this session, file the confirmed ticket with `rail add FILE`, from a file outside the repository, with
`Channel: session` in its `## Grilling` section.

When the request is about data, look at the real data too before you ask (the stored records, a sample of the
input, the output the code makes today), so you don't ask the person what you can see there and your checks fit
the data as it really is.

<!-- Not tested with a model run: the next paragraph. -->
When the request needs a service with a key, a CLI that signs in or an MCP server that `[tools]` in
`.rail/config.toml` does not declare, the tool gets a ticket of its own, and the ticket for the request names
it in `after`. Draft the tool's ticket with `rail-tool`.
