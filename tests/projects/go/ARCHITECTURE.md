# Architecture

A notes service: an HTTP API over a store kept in memory, and one command that serves it or calls it. Standard
library only.

## Areas
| Area | Paths | Holds |
|---|---|---|
| cmd | cmd/** | the `notes` command: `serve`, and `add`, `done` and `list` as a client of a running server |
| internal | internal/** | `notes`, the store, and `api`, the HTTP handler; each package's tests are beside it |
