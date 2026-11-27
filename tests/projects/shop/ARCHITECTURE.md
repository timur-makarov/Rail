# Architecture

A shop in one repository: a Python service, a TypeScript app, and a library both use.

## Areas
| Area | Paths | Holds |
|---|---|---|
| api | api/** | the billing service: what a cart costs |
| web | web/** | the cart page |
| lib | lib/** | money sums, in Python and in TypeScript |
