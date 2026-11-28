#!/bin/bash
# The tools Rail's own tests use, for a machine made for the work: a Claude Code cloud session or a CI runner.
#
# Rail is developed without Rail, so this repository has no .rail/config.toml whose `provision` command could say
# what its tests need. This file says it. The language tests (python3 tests/run.py --languages) leave out a check
# whose tool is missing and print it as "not run", so a green run on a machine without these tools checks less.
#
# In a cloud environment for work on Rail, the setup script is one line, run from the folder that holds the
# repositories:
#
#   [ -f Rail/tests/tools.sh ] && RAIL_CLOUD=1 bash Rail/tests/tools.sh || true
#
# On a person's own machine it installs nothing: it lists what is missing and how this file would install it.
# A tool that is on PATH already is left alone, and an install that fails prints "skipped: NAME" and goes on, so
# the script never stops a session from starting. It always exits 0.
#
# Each line says whether it was run: "ran" lines installed their tool in a cloud session on 2026-11-26.
# "Not run" lines are the tool's documented install as far as known, and nobody has run them from this file.

# Where the installers put what they install, for a setup script whose PATH lacks these folders. RAIL_TOOLS_PATH
# names other folders on a machine where they differ.
export PATH="$PATH:${RAIL_TOOLS_PATH-$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/go/bin:/usr/local/bin:/opt/node22/bin}"

GITLEAKS=8.24.2
GITLEAKS_SHA256=fa0500f6b7e41d28791ebc680f5dd9899cd42b58629218a5f041efa899151a8e

install_gitleaks() {
  local tmp
  tmp=$(mktemp) &&
    curl -fsSL -o "$tmp" \
      "https://github.com/gitleaks/gitleaks/releases/download/v$GITLEAKS/gitleaks_${GITLEAKS}_linux_x64.tar.gz" &&
    echo "$GITLEAKS_SHA256  $tmp" | sha256sum -c - >/dev/null &&
    tar -xzf "$tmp" -C /usr/local/bin gitleaks
  local code=$?
  rm -f "$tmp"
  return $code
}

# NAME|what uses it|the command that installs it
TOOLS='
pip-audit|python audit|uv tool install pip-audit
basedpyright|python types|uv tool install basedpyright
govulncheck|go audit|GOBIN=/usr/local/bin go install golang.org/x/vuln/cmd/govulncheck@latest
cargo-deny|rust audit|cargo install --locked cargo-deny
gitleaks|the secret scan of every language|install_gitleaks
oxlint|typescript lint|npm install -g oxlint
jscpd|the duplication sensor|npm install -g jscpd
lizard|the complexity sensor|uv tool install lizard
mutmut|python mutation|uv tool install mutmut
gremlins|go mutation|GOBIN=/usr/local/bin go install github.com/go-gremlins/gremlins/cmd/gremlins@latest
cargo-mutants|rust mutation|cargo install --locked cargo-mutants
'
# Ran: pip-audit, basedpyright, govulncheck, cargo-deny. The gitleaks download ran on a GitHub runner.
# Not run: oxlint, jscpd, lizard, mutmut, gremlins, cargo-mutants.

made_for_the_work() {
  case "${RAIL_CLOUD:-}" in 1 | true) return 0 ;; 0 | false) return 1 ;; esac
  [ "${CLAUDE_CODE_REMOTE:-}" = true ] || [ "${GITHUB_ACTIONS:-}" = true ]
}

echo "$TOOLS" | while IFS='|' read -r name use command; do
  [ -n "$name" ] || continue
  if command -v "$name" >/dev/null 2>&1; then
    echo "present: $name"
  elif ! made_for_the_work; then
    echo "missing: $name ($use). This is your own machine, so nothing is installed; this file would run: $command"
  elif output=$(eval "$command" 2>&1) && command -v "$name" >/dev/null 2>&1; then
    echo "installed: $name"
  else
    echo "skipped: $name ($use): $(echo "$output" | tail -n 1)"
  fi
done
exit 0
