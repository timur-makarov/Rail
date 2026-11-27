"""tests/tools.sh: the tools Rail's own tests use, installed on a machine made for the work and only there.
Stand-ins play uv, go, cargo, npm and curl, so nothing is installed by these tests."""

import glob
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from railtest import RailTest  # noqa: E402

FRAMEWORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(FRAMEWORK, "tests", "tools.sh")

# An installer's stand-in: it records its call and, unless told to fail, puts a program named after what it was
# asked for into its own folder, which is on PATH. curl always fails, so the gitleaks download never happens.
INSTALLER = """#!/bin/sh
here=$(dirname "$0"); me=$(basename "$0")
echo "$me $*" >> "$here/calls.log"
case " $FAIL " in *" $me "*) echo "$me: no network"; exit 1 ;; esac
[ "$me" = curl ] && { echo "curl: no network"; exit 22; }
for last; do :; done
name=$(basename "${last%@*}")
printf '#!/bin/sh\\n' > "$here/$name" && chmod +x "$here/$name"
"""

# What a profile's command uses and this file does not install: the toolchains and their package managers, which
# the machine brings, and the tools a project keeps among its own dependencies.
NOT_THIS_FILES = {"uv", "pnpm", "npm", "yarn", "bun", "cargo", "cargo-clippy", "rustfmt", "go", "gofmt",
                  "golangci-lint", "pytest", "ruff", "tsc"}


def listed():
    with open(SCRIPT) as f:
        table = re.search(r"^TOOLS='\n(.*?)^'", f.read(), re.S | re.M).group(1)
    return [line.split("|")[0] for line in table.splitlines() if line]


class Tools(RailTest):
    def machine(self):
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        for name in ("uv", "go", "cargo", "npm", "curl"):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(INSTALLER)
            os.chmod(path, 0o755)

    def run_script(self, cloud, fail=""):
        # The stand-ins come first on PATH, and none of the machine's own tool folders is on it: /usr/bin and /bin
        # are there for bash's helpers only.
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": os.path.join(self.tmp, "home"), "RAIL_TOOLS_PATH": self.bin,
               "RAIL_CLOUD": "1" if cloud else "0", "FAIL": fail}
        done = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        state = {}
        for line in done.stdout.splitlines():  # "installed: NAME", "skipped: NAME (what uses it): why"
            what, rest = line.split(": ", 1)
            state[rest.split(" ")[0]] = what
        return state, done.stdout

    def calls(self):
        path = os.path.join(self.bin, "calls.log")
        return open(path).read().splitlines() if os.path.exists(path) else []

    def test_on_a_persons_own_machine_it_installs_nothing_and_says_what_it_would_run(self):
        self.machine()
        state, output = self.run_script(cloud=False)
        self.assertEqual(set(state.values()), {"missing"})
        self.assertEqual(sorted(state), sorted(listed()))
        self.assertIn("this file would run: uv tool install pip-audit", output)
        self.assertEqual(self.calls(), [])

    def test_on_a_machine_made_for_the_work_it_installs_what_is_missing_once(self):
        self.machine()
        state, output = self.run_script(cloud=True)
        # The download of gitleaks fails here, which stops nothing: its line says why, and the rest is installed.
        self.assertEqual(state.pop("gitleaks"), "skipped")
        self.assertIn("skipped: gitleaks (the secret scan of every language): curl: no network", output)
        self.assertEqual(set(state.values()), {"installed"})
        self.assertIn("uv tool install pip-audit", self.calls())
        self.assertIn("cargo install --locked cargo-deny", self.calls())
        self.assertIn("npm install -g oxlint", self.calls())
        first = len(self.calls())

        state, _ = self.run_script(cloud=True)  # a second run finds them on PATH and installs none again
        self.assertEqual(state.pop("gitleaks"), "skipped")
        self.assertEqual(set(state.values()), {"present"})
        self.assertEqual(len(self.calls()), first + 1)  # only the download was tried again

    def test_an_install_that_fails_is_skipped_and_the_others_go_on(self):
        self.machine()
        state, _ = self.run_script(cloud=True, fail="cargo")
        self.assertEqual({name for name, what in state.items() if what == "skipped"},
                         {"cargo-deny", "cargo-mutants", "gitleaks"})
        self.assertEqual(state["pip-audit"], "installed")
        self.assertEqual(state["oxlint"], "installed")

    def test_every_tool_a_profile_names_is_installed_here_or_comes_with_the_machine_or_the_project(self):
        named = set()
        for path in glob.glob(os.path.join(FRAMEWORK, "profiles", "*", "profile.toml")):
            with open(path) as f:
                named |= set(re.findall(r'\btool = "([^"]+)"', f.read()))
        self.assertTrue(named, "the profiles name their tools")
        self.assertEqual(named - set(listed()) - NOT_THIS_FILES, set())
