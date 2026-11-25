"""A run: its own folder, home, temp folder and scrubbed environment, its log, and its saved stages.

store/runs/RUN/
  run.toml        what the run is: situation, arm, session id, the commits it starts from, where it was restarted from
  log.jsonl       one line per driver step, appended
  home/ tmp/      HOME and TMPDIR of every child
  copy/           the run's own copy of the sealed repository
  streams/        each worker run's whole output, NNN-ROLE.jsonl
  stages/         saved stages: NN-NAME.tar.gz pieces, and stages.jsonl, one line per complete stage
  ended.toml      how the run ended, written before the grade
  result.toml     the end and the grade: a run is graded only once it has one

A saved stage holds everything needed to go on: the copy with every ref, the worktrees and .git/rail/, and the driver's
counters and session id. Build folders are left out and put back from the sealed copy when a stage is restored."""

import json
import os
import shutil
import tarfile
import tomllib

from . import sealed, tomlw
from .common import BenchError, git, now_iso, run, write

PIECE = 1024 * 1024  # piece_mb is counted in these


class Run:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.id = os.path.basename(self.path)
        self.copy = os.path.join(self.path, "copy")
        self.home = os.path.join(self.path, "home")
        self.tmp = os.path.join(self.path, "tmp")
        self.streams = os.path.join(self.path, "streams")
        self.stages_dir = os.path.join(self.path, "stages")
        self.meta = read_toml(os.path.join(self.path, "run.toml"))

    def __getattr__(self, key):
        try:
            return self.__dict__["meta"][key]
        except KeyError:
            raise AttributeError(key)

    # --- the log ---------------------------------------------------------------------------

    def log(self, kind, **fields):
        with open(os.path.join(self.path, "log.jsonl"), "a") as f:
            f.write(json.dumps({"at": now_iso(), "kind": kind, **fields}) + "\n")

    def log_lines(self):
        path = os.path.join(self.path, "log.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    # --- the end -----------------------------------------------------------------------------

    @property
    def ended(self):
        return read_toml(os.path.join(self.path, "ended.toml"))

    @property
    def result(self):
        return read_toml(os.path.join(self.path, "result.toml"))

    def write_ended(self, data):
        write(os.path.join(self.path, "ended.toml"), tomlw.dumps(data))

    def write_result(self, data):
        write(os.path.join(self.path, "result.toml"), tomlw.dumps(data))

    def stream(self, n, role):
        os.makedirs(self.streams, exist_ok=True)
        return os.path.join(self.streams, f"{n:03d}-{role}.jsonl")

    def stream_files(self):
        if not os.path.isdir(self.streams):
            return []
        return sorted(f for f in os.listdir(self.streams) if f.endswith(".jsonl"))

    # --- stages ----------------------------------------------------------------------------

    def stages(self):
        path = os.path.join(self.stages_dir, "stages.jsonl")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    def stage(self, name):
        for s in self.stages():
            if s["name"] == name:
                return s
        raise BenchError(f"run {self.id} has no stage '{name}'; it has {', '.join(s['name'] for s in self.stages())}")

    def save_stage(self, name, state, build_dirs, piece_mb):
        """Pack the copy into pieces under piece_mb, then add the stage to the index. A stage in the index is
        complete: a driver killed while packing leaves only pieces nobody reads."""
        os.makedirs(self.stages_dir, exist_ok=True)
        index = len(self.stages()) + 1
        base = f"{index:02d}-{name}"
        packed = os.path.join(self.stages_dir, base + ".tar.gz.packing")
        skip = set(build_dirs)

        def keep(info):
            return None if os.path.basename(info.name) in skip else info

        with tarfile.open(packed, "w:gz", compresslevel=6) as tar:
            tar.add(self.copy, arcname="copy", filter=keep)
        pieces = split(packed, os.path.join(self.stages_dir, base + ".tar.gz"), piece_mb * PIECE)
        os.unlink(packed)
        meta = {"name": name, "index": index, "at": now_iso(), "pieces": pieces, "state": state,
                "streams": self.stream_files()}
        with open(os.path.join(self.stages_dir, "stages.jsonl"), "a") as f:
            f.write(json.dumps(meta) + "\n")
        self.log("stage", name=name, index=index, pieces=len(pieces))
        return meta

    def stage_before(self, name):
        """The stage saved just before `name`: what a run restarted at `name` starts from."""
        stages = self.stages()
        names = [s["name"] for s in stages]
        if name not in names:
            raise BenchError(f"run {self.id} has no stage '{name}'; it has {', '.join(names)}")
        i = names.index(name)
        if i == 0:
            raise BenchError(f"nothing is saved before '{name}': start a new run instead")
        return stages[i - 1]


def aside_if_again(path):
    """A run whose result says to run it again is moved aside to PATH.again-N, so the same run id starts afresh. The
    report still counts the one set aside."""
    if not read_toml(os.path.join(path, "result.toml")).get("again"):
        return None
    n = 1
    while os.path.exists(f"{path}.again-{n}"):
        n += 1
    os.replace(path, f"{path}.again-{n}")
    return f"{path}.again-{n}"


def read_toml(path):
    if not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def split(path, base, size):
    """Cut a file into pieces of at most `size` bytes: BASE.000, BASE.001, ... Returns their names."""
    names = []
    with open(path, "rb") as src:
        n = 0
        while True:
            chunk = src.read(size)
            if not chunk and n:
                break
            name = f"{os.path.basename(base)}.{n:03d}"
            with open(os.path.join(os.path.dirname(base), name + ".tmp"), "wb") as out:
                out.write(chunk)
            os.replace(os.path.join(os.path.dirname(base), name + ".tmp"), os.path.join(os.path.dirname(base), name))
            names.append(name)
            n += 1
            if not chunk:
                break
    return names


class Pieces:
    """The pieces of a stage read back as one file."""

    def __init__(self, folder, names):
        self.files = [os.path.join(folder, n) for n in names]
        self.current = None

    def read(self, size=-1):
        out = b""
        while size < 0 or len(out) < size:
            if self.current is None:
                if not self.files:
                    break
                self.current = open(self.files.pop(0), "rb")
            chunk = self.current.read(-1 if size < 0 else size - len(out))
            if not chunk:
                self.current.close()
                self.current = None
                continue
            out += chunk
        return out


def restore(source, meta, dest_run, situation, store_root, env, build_dirs):
    """Restore a stage of run `source` as `dest_run`'s copy: unpack it, put the build folders back from the sealed copy,
    point the worktrees at their new place, and run Rail's setup in each worktree."""
    dest = dest_run.copy
    if os.path.exists(dest):
        shutil.rmtree(dest)
    unpack = dest_run.copy + ".restoring"
    shutil.rmtree(unpack, ignore_errors=True)
    os.makedirs(unpack)
    with tarfile.open(fileobj=Pieces(source.stages_dir, meta["pieces"]), mode="r|gz") as tar:
        try:
            tar.extractall(unpack, filter="tar")
        except TypeError:  # Python before 3.11.4 has no filter
            tar.extractall(unpack)
    os.replace(os.path.join(unpack, "copy"), dest)
    shutil.rmtree(unpack, ignore_errors=True)
    sealed_copy = os.path.join(sealed.folder(store_root, situation), "copy")
    for base, dirs, _ in os.walk(sealed_copy):
        for d in list(dirs):
            if d in build_dirs:
                rel = os.path.relpath(os.path.join(base, d), sealed_copy)
                target = os.path.join(dest, rel)
                if os.path.isdir(os.path.dirname(target)) and not os.path.exists(target):
                    shutil.copytree(os.path.join(base, d), target, symlinks=True)
                dirs.remove(d)
    worktrees = worktree_paths(dest)
    if worktrees:
        git(["worktree", "repair", *worktrees], dest, env)
    setup = read_toml(os.path.join(dest, ".rail", "config.toml")).get("commands", {}).get("setup", "")
    for wt in worktrees:
        if setup:
            code, out = run(setup, wt, env, 900)
            if code != 0:
                raise BenchError(f"Rail's setup failed in a restored worktree {wt}: {out[-1000:]}")
    for name in meta["streams"]:
        src = os.path.join(source.streams, name)
        if source.path != dest_run.path and os.path.exists(src):
            os.makedirs(dest_run.streams, exist_ok=True)
            shutil.copyfile(src, os.path.join(dest_run.streams, name))
    for name in dest_run.stream_files():  # the streams of work after this stage are gone with it
        if name not in meta["streams"]:
            os.unlink(os.path.join(dest_run.streams, name))


def worktree_paths(copy):
    folder = os.path.join(copy, ".claude", "worktrees")
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, d) for d in os.listdir(folder) if os.path.exists(os.path.join(folder, d, ".git")))
