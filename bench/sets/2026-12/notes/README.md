# Notes on the project files of set 2026-12

Written on 2026-11-26 by reading each project's CI, build files and docs at the oldest and newest start commit of its
candidates, with nothing installed, built or run. Every command in the project files is marked `unverified` until the
cloud admission step has run it; that step records what it changed in the project file and here.

- `PROJECT.md`: what was read, each command and its state, the toolchain pins, sizes and times expected, the traps,
  candidates unlikely to pass, and a list "for the admission session to try first".
- `rust-common.md`, `go-common.md`, `typescript-common.md`: the choices shared by one language's projects.
- `rust-test-files.py`: the Rust test-file runner; each Rust project file embeds a copy of it in `test_files`.

The store path is `/srv/rail-bench` (`BENCH_STORE`): the Rust project files name `CARGO_HOME` and `RUSTUP_HOME` under
it, because `[commands] env` values are taken literally, and rolldown's fixture tests are ignored under any folder
whose name starts with a dot.
