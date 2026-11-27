"""The check of a verb's JSON answer against engine/answer-v1.json (rail docs loop).

The file names every `reason.code`, the kinds of action and the owners a code may have, and the keys of
`action.facts` for a code that has facts. The suite runs this check on every answer a test reads, so a code, a kind or
a fact the file does not name fails there.
"""

import functools
import json
import os

from . import schema, table

FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "answer-v1.json")
WITH_FACTS = ("agent_task", "person_wait")  # what `rail next` answers with facts, whatever the code


@functools.lru_cache(maxsize=1)
def load():
    with open(FILE, encoding="utf-8") as f:
        return json.load(f)


def facts_schema(doc, code, one_ticket):
    """The schema of a code's facts: its own keys, the keys every answer about one ticket has, and what is put around
    a brief."""
    own = doc["codes"][code]["facts"]
    shared, ends = doc["shared_facts"]["properties"], doc["added_facts"]["properties"]
    return {"type": "object", "additionalProperties": False,
            "required": [*(shared if one_ticket else []), *own.get("required", [])],
            "properties": {**shared, **ends, **own["properties"]}}


def check(answer, verb=None, doc=None):
    """The ways an answer breaks the schema, each as "where: what"; an empty list when it holds. With `verb`, the rule
    of that verb is checked too: an agent's task or a person's wait from `rail next` has facts."""
    doc = doc or load()
    if answer.get("ok") is False:
        return schema.check(answer, doc["error"], doc)
    found = schema.check(answer, doc["answer"], doc)
    if found:
        return found
    code, action = answer["reason"]["code"], answer["action"]
    named = doc["codes"].get(code)
    if named is None:
        return [f"$.reason.code: the schema names no code '{code}'"]
    if action["kind"] not in named["kinds"]:
        found.append(f"$.action.kind: {code} is {' or '.join(named['kinds'])}, not {action['kind']}")
    if answer["owner"] not in named["owners"]:
        found.append(f"$.owner: {code} belongs to {' or '.join(named['owners'])}, not {answer['owner']}")
    if "facts" not in action:
        if verb == "next" and action["kind"] in WITH_FACTS:
            found.append(f"$.action: {code} from rail next has no facts")
        return found
    if "facts" not in named:
        return found + [f"$.action.facts: the schema names no facts for {code}"]
    found += schema.check(action["facts"], facts_schema(doc, code, answer["ticket"] is not None), doc, "$.action.facts")
    if not found and table.render(code, action["facts"]) != action["brief"]:
        found.append(f"$.action.brief: is not what {code}'s facts render")
    return found
