#!/bin/bash
# The setup script of a Claude Code cloud environment, for any repository that runs on Rail.
# Paste these lines into the environment's settings, under "Setup script". They are the same for every project.
#
# The script runs as root when a new machine is built, from the folder that holds the repositories, before the
# first session starts. For each repository with Rail in it, `rail provision` links rail onto PATH, writes Rail's
# hooks into the machine's own Claude Code settings, and runs the project's `[commands] provision` from
# .rail/config.toml, which installs what its checks need. What a project needs is written there, not here.
#
# A repository without Rail is skipped, and a provision that fails does not stop the session from starting:
# `rail doctor` then says what is missing.
for d in */; do
  [ -x "$d.rail/bin/rail" ] && (cd "$d" && RAIL_CLOUD=1 .rail/bin/rail provision) || true
done
