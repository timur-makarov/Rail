"""`[product] seed`: the note every driving check expects to find."""

import sys

from run import call

status, note = call("POST", body={"title": "seeded"})
print(f"seed: POST answered {status} {note}")
sys.exit(0 if status == 201 else 1)
