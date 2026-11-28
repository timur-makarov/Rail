"""The bench's command line: bench/bench VERB ... (or python3 -m bench VERB ... from the repository's root)."""

import argparse
import fcntl
import json
import os
import sys
import time

from . import admit as admitmod
from . import arms as armsmod
from . import driver, fixture, runs, sealed, sets
from . import grade as grademod
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


def summary(result):
    if result.get("again"):
        return f"{result['run']}: to run again ({result.get('detail', result['end'])})"
    words = [f"ended {result['end']}", "merged" if result["merged"] else "not merged",
             "right" if result.get("right_stop") else "wrong" + (f" ({result['grade_why']})" if result.get("grade_why")
                                                                  else "")]
    if result["person_acts"]:
        words.append(f"{len(result['person_acts'])} person acts stood in for")
    if not result.get("locked"):
        words.append("unlocked")
    if result["tainted"]:
        words.append("TAINTED: " + ", ".join(sorted({h["term"] for h in result["taint"]})))
    return f"{result['run']}: " + "; ".join(words)


def locked(run_):
    """Hold the run's lock while it runs: a second bench run on the same run waits for the first to end. The lock
    goes with the process, so a killed driver leaves none."""
    handle = open(os.path.join(run_.path, "lock"), "w")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def go(conf, root, situation, arm, run_):
    handle = locked(run_)
    try:
        ctx = driver.Context(conf, root, situation, arm, runs.Run(run_.path))
        return driver.go(ctx)
    finally:
        handle.close()


def cmd_run(args, conf):
    root = store(conf)
    arm = armsmod.load(args.arm)
    if args.from_run:
        if not args.stage:
            raise BenchError("--from needs --stage")
        source = runs.Run(args.from_run if os.sep in args.from_run else os.path.join(root, "runs", args.from_run))
        if not source.meta:
            raise BenchError(f"no run {args.from_run}")
        project = sets.load(source.project)
        situation = project.situation(source.situation)
        targets = [driver.restart(conf, root, source, args.stage, situation, arm, n, plan=args.plan)
                   for n in range(1, args.runs + 1)]
    else:
        if not args.project or not args.id:
            raise BenchError("bench run needs a project file and --id, or --from RUN --stage NAME")
        project = sets.load(args.project)
        situation = project.situation(args.id[0])
        sealed.build(root, situation)
        targets = []
        for n in range(1, args.runs + 1):
            rid = driver.run_id(situation, arm, n)
            path = os.path.join(root, "runs", rid)
            runs.aside_if_again(path)
            targets.append(runs.Run(path) if os.path.exists(os.path.join(path, "run.toml"))
                           else driver.create(conf, root, situation, arm, rid, plan=args.plan))
    failed = 0
    for target in targets:
        result = go(conf, root, situation, arm, target)
        print(json.dumps(result) if args.json else summary(result))
        failed += result.get("again", False)
    return 1 if failed else 0


def cmd_check_arm(args, conf):
    """One trivial situation of the fixture project, end to end. An arm that fails it joins no run."""
    root = store(conf)
    arm = armsmod.load(args.name)
    dest = os.path.join(root, "check", f"{arm.name}-{time.strftime('%Y%m%d-%H%M%S')}")
    project = sets.load(fixture.build(dest))
    situation = project.situation("calc-01")
    sealed.build(root, situation)
    run_ = driver.create(conf, root, situation, arm, f"check.{os.path.basename(dest)}")
    result = go(conf, root, situation, arm, run_)
    ok = result["merged"] and result.get("right_merged") and not result["tainted"] and not result["again"]
    print(json.dumps(result) if args.json else summary(result))
    print(f"check-arm {arm.name}: {'pass' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_report(args, conf):
    """The numbers of PLAN section 5 per arm, from every result in the store."""
    from . import report
    arms = args.arms.split(",") if args.arms else None
    rep = report.from_store(store(conf), conf, arms=arms, held=args.held, seed=args.seed, resamples=args.resamples,
                            any_situation=args.any_situation)
    print(report.dumps(rep) if args.json else report.render(rep), end="" if not args.json else "\n")
    return 0


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
    r = verb("run", "run an arm on a situation, or go on with a run; with --from, restart a run from a saved stage")
    r.add_argument("project", nargs="?")
    r.add_argument("--id", action="append")
    r.add_argument("--arm", required=True, help="an arm in bench/arms, or the path of an arm file")
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--from", dest="from_run", help="a run's id or folder")
    r.add_argument("--stage", help="with --from: the stage to start at; the state saved before it is restored")
    r.add_argument("--plan", help="the fake agent's plan, for the fake arms")
    c = verb("check-arm", "run one trivial situation of the fixture project end to end with an arm")
    c.add_argument("name")
    rp = verb("report", "the numbers per arm on the situations every compared arm may be scored on")
    rp.add_argument("--arms", help="the arms to compare, comma-separated; all with results when left out")
    rp.add_argument("--held", action="store_true", help="the held-out half instead of the working half")
    rp.add_argument("--any-situation", action="store_true", help="also situations that were not admitted (the suite)")
    rp.add_argument("--seed", type=int, default=7, help="the seed of the resampling, stated in the report")
    rp.add_argument("--resamples", type=int, default=2000)
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
