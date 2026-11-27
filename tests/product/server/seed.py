"""`[product] seed`: the test identity, from a file in the repository."""

import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
shutil.copy(os.path.join(HERE, "seed.json"), os.path.join(HERE, ".run", "seed.json"))
print("seed: loaded the test user")
