# Architecture

A notes API: an HTTP server over a SQLite store. Standard library only.

## Areas
| Area | Paths | Holds |
|---|---|---|
| notes | src/** | the store, the HTTP handler and the command that serves it |
| tests | tests/** | pytest: the store alone, and the API driven over a real socket |
