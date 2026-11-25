#!/usr/bin/env python3
"""Put admitted situations back into a store that lost them (a new machine, or a reclaimed one), from the admission
records kept in the results repository: build each sealed copy again (`bench build`: the mirror, the copy, the hidden
tests, the fix, the project's setup, with the network) and write its admission.toml with the overall verdict of
admit_one.py, which the report and choose.py read. A situation whose sealed copy is there is left as it is.

  restore_store.py ADMISSION_DIR PROJECT_FILE [--id ID ...]

ADMISSION_DIR holds admit_one.py's ID.json files for that project (such as RESULTS/admission/PROJECT). Only admitted
situations are restored; with --id, only those. Prints one line per situation. Exit 1 when one could not be built."""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bench import sealed, sets, tomlw  # noqa: E402
from bench.common import BenchError, settings, store, write  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("admission_dir")
    p.add_argument("project")
    p.add_argument("--id", action="append")
    a = p.parse_args(argv)
    root = store(settings())
    project = sets.load(a.project)
    failed = 0
    for path in sorted(glob.glob(os.path.join(a.admission_dir, "*.json"))):
        with open(path) as f:
            record = json.load(f)
        sid = record["situation"]
        if not record.get("admitted") or (a.id and sid not in a.id):
            continue
        situation = project.situation(sid)
        folder = sealed.folder(root, situation)
        if os.path.isdir(os.path.join(folder, "copy")) and os.path.exists(os.path.join(folder, "admission.toml")):
            print(f"{sid}: there")
            continue
        if os.path.exists(os.path.join(folder, "meta.toml")) and not os.path.isdir(os.path.join(folder, "copy")):
            import shutil
            shutil.rmtree(folder)  # a folder without its copy would be taken as built
        try:
            sealed.build(root, situation, log=lambda m: print(m, flush=True))
        except BenchError as e:
            print(f"{sid}: could not build: {str(e)[-500:]}")
            failed += 1
            continue
        bench_record = dict(record.get("bench") or {})
        bench_record.update(admitted=True, reasons=[], restored_from=os.path.abspath(path))
        write(os.path.join(folder, "admission.toml"), tomlw.dumps(bench_record))
        print(f"{sid}: restored")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
