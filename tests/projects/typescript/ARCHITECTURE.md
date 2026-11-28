# Architecture

A notes web app: one page and an API route, both answered by a handler that takes a Request and gives a Response.
No dependencies; Node runs the TypeScript as it is.

## Areas
| Area | Paths | Holds |
|---|---|---|
| app | src/** | the notes, the API route and the page |
| serve | bin/** | the Node server that hands each request to the handler |
| tests | test/** | node:test: the handler alone, and the app driven over a real socket |
