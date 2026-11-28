#!/usr/bin/env python3
"""Run the end-to-end tests on several workers: python3 tests/run.py [-j N] [-k TEXT] [--languages].

Every test builds its own project in a temporary folder, so tests don't touch each other. unittest has no
parallel mode, so this splits the tests across worker processes and prints the output of any worker that
fails. `python3 -m unittest discover -s tests` still runs them one after another.

--languages runs only the language tests (tests/test_languages.py), which take one small real project per
supported language (tests/projects/) from rail init to a merged ticket with that language's own toolchain. A
plain run skips a language whose toolchain this machine lacks; with --languages that is a failure, so a pass
means all four ran. It ends with the parts of a profile's verify that were left out because their tool is
missing here: those lines of the profile are still unchecked.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from ids(item)
        else:
            yield item.id()


def main():
    parser = argparse.ArgumentParser(description="Run Rail's tests on several workers.")
    parser.add_argument("-j", "--jobs", type=int, default=2 * (os.cpu_count() or 2),
                        help="worker processes (default: twice the CPUs; the tests mostly wait on git)")
    parser.add_argument("-k", dest="text", help="run only the tests whose id contains this text")
    parser.add_argument("--languages", action="store_true",
                        help="run only the language tests, and fail where a language's toolchain is missing")
    args = parser.parse_args()

    sys.path.insert(0, HERE)
    names = sorted(ids(unittest.defaultTestLoader.discover(HERE)))
    broken = [n for n in names if n.startswith("unittest.loader._FailedTest")]
    if broken:
        print("These test files don't import: " + ", ".join(n.rsplit(".", 1)[-1] for n in broken))
        return 1
    env, report = dict(os.environ), None
    if args.languages:
        names = [n for n in names if n.startswith("test_languages.")]
        report = tempfile.NamedTemporaryFile(prefix="rail-languages-", suffix=".txt", delete=False).name
        env.update(RAIL_LANGUAGES="1", RAIL_LANGUAGES_REPORT=report)
    if args.text:
        names = [n for n in names if args.text in n]
    if not names:
        print("No tests match.")
        return 1
    jobs = max(1, min(args.jobs, len(names)))
    start = time.time()
    workers = [subprocess.Popen([sys.executable, "-m", "unittest", *names[i::jobs]], cwd=HERE, text=True, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT) for i in range(jobs)]
    failed = 0
    for worker in workers:
        output, _ = worker.communicate()
        if worker.returncode != 0:
            failed += 1
            print(output)
    took = time.time() - start
    if report:
        with open(report) as f:
            left = sorted(set(f.read().splitlines()))
        os.unlink(report)
        print("\n".join(left) if left else "Every part of every profile's verify ran.")
    print(f"{len(names)} tests on {jobs} workers in {took:.0f}s: " + ("OK" if not failed else f"FAILED in {failed} workers"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
