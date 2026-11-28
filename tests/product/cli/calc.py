"""The fixture product's command line: python3 cli/calc.py add 2 3"""

import os
import sys


def add(a, b):
    return a + b + int(os.environ.get("CALC_FAULT", "0"))  # the planted fault, as the server has it


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "add":
        sys.exit("usage: calc.py add A B")
    print(add(int(sys.argv[2]), int(sys.argv[3])))
