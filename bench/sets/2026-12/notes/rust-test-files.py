# bench: run only the given Rust test files. Each .rs file goes to the cargo target that compiles it (read from
# `cargo metadata`): an integration test target (--test NAME), the library (--lib) or a binary (--bin NAME), with a
# libtest filter for the file's module path (or its test function names), so only that file's tests run; child modules
# kept in other files are skipped unless they are listed too. Data files and helper modules with no test in them
# travel but are not run. Exits non-zero when a file can't be placed, when nothing in the list can run, or when a call
# runs no test (an empty run would pass vacuously).
import json, os, re, subprocess, sys

RUNNER = "test"   # "test": cargo test; "nextest": cargo nextest run (same selectors and filters after --)
ALL_ARGS = []     # cargo args for every call, e.g. ["--all-features"]
PKG_ARGS = {}     # package name -> extra cargo args, e.g. {"ruff_linter": ["--all-features"]}

files = [f for f in sys.argv[1:] if f]
meta = json.loads(subprocess.run(["cargo", "metadata", "--no-deps", "--offline", "--format-version", "1"],
                                 check=True, capture_output=True, text=True).stdout)
root = meta["workspace_root"]
members = set(meta["workspace_members"])
TARGETS = []  # dicts: pid, pkg, sel (cargo args), src, dir (the crate root's folder); paths relative to root
for p in meta["packages"]:
    if p["id"] not in members:
        continue
    for t in p["targets"]:
        kinds = set(t["kind"])
        if "test" in kinds:
            sel = ["--test", t["name"]]
        elif kinds & {"lib", "rlib", "proc-macro", "cdylib", "staticlib", "dylib"}:
            sel = ["--lib"]
        elif "bin" in kinds:
            sel = ["--bin", t["name"]]
        else:
            continue  # build scripts, examples, benches
        if t.get("required-features"):
            sel += ["--features", ",".join(t["required-features"])]
        src = os.path.relpath(t["src_path"], root)
        TARGETS.append({"pid": p["id"], "pkg": p["name"], "sel": sel, "src": src, "dir": os.path.dirname(src)})


def read(path):
    try:
        with open(os.path.join(root, path), errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def place(path):
    """The targets compiling `path`: the target whose crate root it is, else those whose crate root folder is the
    deepest one holding it; among several, those whose root declares the file's top module, a library before a
    binary."""
    exact = [t for t in TARGETS if t["src"] == path]
    if exact:
        return exact
    holding = [t for t in TARGETS if t["dir"] == "" or path.startswith(t["dir"] + "/")]
    if not holding:
        return []
    deepest = max(len(t["dir"]) for t in holding)
    cands = [t for t in holding if len(t["dir"]) == deepest]
    if len(cands) > 1:
        top = os.path.relpath(path, cands[0]["dir"]).split("/")[0]
        top = top[:-3] if top.endswith(".rs") else top
        declaring = [t for t in cands if re.search(rf"\bmod\s+{re.escape(top)}\b|#\[path\s*=\s*\"[^\"]*{re.escape(top)}",
                                                    read(t["src"]))]
        cands = declaring or cands
        libs = [t for t in cands if t["sel"][0] == "--lib"]
        cands = libs or cands
    return cands


TEST_ATTR = re.compile(r"#\[\s*(?:[\w:]+::)?(?:test|tokio::test|test_case|rstest|case|quickcheck|proptest)\b")


def test_fns(path):
    """Test function names in a file: a `fn` soon after an attribute naming a test."""
    names, armed = [], 0
    for line in read(path).splitlines():
        s = line.strip()
        if TEST_ATTR.search(s):
            armed = 8
        m = re.match(r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)", s)
        if m and armed:
            names.append(m.group(1))
            armed = 0
        elif armed and s and not s.startswith(("#", "//")):
            armed -= 1
    return names


def module_path(path, t):
    rel = os.path.relpath(path, t["dir"])[:-3].split("/")
    if rel[-1] == "mod":
        rel = rel[:-1]
    return "::".join(rel)


def child_modules(path):
    """Modules the file declares that live in other files (`mod x;`, not `mod x { ... }`)."""
    return re.findall(r"^\s*(?:#\[[^\]]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;", read(path), re.M)


# Per-project hooks. project_hook: return True when it handled the file (added a run to `other`, a list of
# (argv, cwd) or (argv, cwd, count regex), or skipped it on purpose). project_finish: a last look at `runs` and `other`.
def project_hook(path, runs, other):
    return False


def project_finish(runs, other):
    pass


runs = {}    # (pid, pkg, sel) -> {"filters": set, "skips": set}, or None for the whole target
other = []   # (argv, cwd[, count regex]) a project hook adds
placed, errors = [], []
for f in files:
    if project_hook(f, runs, other):
        continue
    if not f.endswith(".rs"):
        print(f"bench: {f} is a data file: it travels, it is not run", flush=True)
        continue
    ts = place(f)
    if not ts:
        errors.append(f"{f}: no cargo target of this workspace compiles it")
        continue
    placed.append((f, ts))
listed = {}
for f, ts in placed:
    for t in ts:
        listed.setdefault((t["pid"], t["pkg"], tuple(t["sel"])), set()).add(f)
for f, ts in placed:
    fns = test_fns(f)
    for t in ts:
        key = (t["pid"], t["pkg"], tuple(t["sel"]))
        skips = []
        if f == t["src"]:
            if t["sel"][0] == "--test" and len(listed[key]) == 1 and (fns or child_modules(f)):
                runs[key] = None          # the test target is this file (and the modules it declares): all of it
                continue
            filt = fns                    # a crate root: its own test functions only
        elif fns:
            mp = module_path(f, t)
            filt = [mp + "::"]
            others = {module_path(g, t) for g in listed[key] if g != f}
            skips = [f"{mp}::{c}::" for c in child_modules(f)
                     if not any(o == f"{mp}::{c}" or o.startswith(f"{mp}::{c}::") for o in others)]
        else:
            filt = []
        if not filt:
            print(f"bench: {f} holds no test of {t['pkg']} {' '.join(t['sel'])}: it travels, it is not run", flush=True)
            continue
        if key in runs and runs[key] is None:
            continue
        r = runs.setdefault(key, {"filters": set(), "skips": set()})
        r["filters"] |= set(filt)
        r["skips"] |= set(skips)
project_finish(runs, other)
for e in errors:
    print(f"bench: {e}", flush=True)
if errors:
    sys.exit(2)
if not runs and not other:
    print("bench: nothing in the list can run", flush=True)
    sys.exit(2)


def stream(cmd, cwd, count=None):
    """Run cmd, echo its output, return (exit code, tests that ran: passed + failed, ignored ones left out). `count`
    is a hook command's own regex whose groups, summed, count its tests."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    ran = 0
    for line in proc.stdout:
        sys.stdout.write(line)
        m = re.search(r"test result: (?:\x1b\[[\d;]*m)*\w+(?:\x1b\[[\d;]*m)*\. (\d+) passed; (\d+) failed", line)  # libtest, libtest-mimic, kitest
        n = re.search(r"Summary \[[^\]]*\]\s+(\d+) tests? run", line)               # nextest
        o = re.search(count, line) if count else None
        if m:
            ran += int(m.group(1)) + int(m.group(2))
        elif n:
            ran += int(n.group(1))
        elif o:
            ran += sum(int(g) for g in o.groups() if g)
    sys.stdout.flush()
    return proc.wait(), ran


status = 0
for (pid, pkg, sel), r in sorted(runs.items(), key=lambda kv: (kv[0][1], kv[0][2])):
    sub = ["nextest", "run"] if RUNNER == "nextest" else ["test"]
    cmd = ["cargo", *sub, "-p", pid, *sel, *ALL_ARGS, *PKG_ARGS.get(pkg, []), "--no-fail-fast"]
    if RUNNER == "nextest":
        cmd += ["--no-tests=fail"]
    cmd += ["--"]
    if r:
        cmd += sorted(r["filters"])
        for s in sorted(r["skips"]):
            cmd += ["--skip", s]
    print("bench: " + " ".join(c if c != pid else pkg for c in cmd), flush=True)
    code, ran = stream(cmd, root)
    if code != 0:
        status = 1
    elif ran == 0:
        print(f"bench: no test ran for {pkg} {' '.join(sel)}", flush=True)
        status = 1
for cmd, cwd, *count in other:
    print(f"bench: (in {os.path.relpath(cwd, root)}) " + " ".join(cmd), flush=True)
    code, ran = stream(cmd, cwd, *count)
    if code != 0:
        status = 1
    elif count and ran == 0:
        print("bench: no test ran for " + " ".join(cmd), flush=True)
        status = 1
sys.exit(status)
