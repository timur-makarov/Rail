# Architecture

A notes command-line program: a library crate that holds the notes and reads and writes their file, and a binary
crate that is the command. Standard library only.

## Areas
| Area | Paths | Holds |
|---|---|---|
| crates | crates/** | `notes`, the library, and `notes-cli`, the command; each crate's tests are beside it |
