"""The bench's command line: bench/bench VERB ... (or python3 -m bench VERB ... from the repository's root)."""

import argparse
import json
import os
import sys

from . import admit as admitmod
from . import grade as grademod
from . import sealed, sets
from .common import BenchError, settings, store


def situations(project, ids):
    return [project.situation(i) for i in ids] if ids else project.situations


def cmd_build(args, conf):
    project = sets.load(args.project)
    root = store(conf)
    for s in situations(project, args.id):
        path = sealed.build(root, s)
        print(f"{s.id}: {path}")
    return 0


def cmd_admit(args, conf):
    project = sets.load(args.project)
    root = store(conf)
    failed = 0
    for s in situations(project, args.id):
        ok, reasons, record = admitmod.admit(root, s, conf)
        if args.json:
            print(json.dumps(record))
        elif ok:
            print(f"{s.id}: admitted")
        else:
            print(f"{s.id}: not admitted")
            for r in reasons:
                print(f"  - {r}")
        failed += not ok
    return 1 if failed else 0


def cmd_grade(args, conf):
    project = sets.load(args.project)
    root = store(conf)
    s = project.situation(args.id[0])
    sealed.build(root, s)
    with open(args.diff, "rb") as f:
        patch = f.read()
    result = grademod.grade(root, s, patch, rounds=conf["grade_rounds"])
    if args.json:
        print(json.dumps(result))
    else:
        print(f"{s.id}: {'right' if result['right'] else 'wrong'}" + (f" ({result['why']})" if result.get("why") else ""))
    return 0 if result["right"] else 1


def parser():
    p = argparse.ArgumentParser(prog="bench", description="Rail's bench: situations, sealed copies, runs and grades.")
    sub = p.add_subparsers(dest="verb", required=True)

    def verb(name, help_):
        v = sub.add_parser(name, help=help_)
        v.add_argument("--json", action="store_true")
        return v

    for name, help_ in (("build", "build the sealed copies of a project's situations"),
                        ("admit", "admit a project's situations with no model: oracle, null, Rail's setup and verify")):
        v = verb(name, help_)
        v.add_argument("project", help="the project file, bench/sets/SET/PROJECT.toml")
        v.add_argument("--id", action="append", help="one situation; repeat for more; all when left out")
    g = verb("grade", "grade a change, a patch from the start commit, against a situation")
    g.add_argument("project")
    g.add_argument("--id", action="append", required=True)
    g.add_argument("--diff", required=True, help="the change as a git patch")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        conf = settings()
        return globals()[f"cmd_{args.verb.replace('-', '_')}"](args, conf)
    except BenchError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
