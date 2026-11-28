"""Write TOML: the standard library reads it (tomllib) but has no writer. Enough for the bench's own files and Rail's
config: tables, arrays of tables, strings, numbers, booleans, dates and lists of those. TOML has no null: a key whose
value is None is left out."""

import datetime
import json
import re

BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k):
    return k if BARE.match(k) else json.dumps(k, ensure_ascii=False)


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items() if x is not None) + "}"
    raise TypeError(f"no TOML for {type(v).__name__}")


def _is_table_array(v):
    return isinstance(v, list) and v and all(isinstance(x, dict) for x in v)


def dumps(data, _path=()):
    """The TOML text of a dict."""
    lines = []
    data = {k: v for k, v in data.items() if v is not None}
    for k, v in data.items():
        if not isinstance(v, dict) and not _is_table_array(v):
            lines.append(f"{_key(k)} = {_value(v)}")
    for k, v in data.items():
        path = _path + (k,)
        name = ".".join(_key(p) for p in path)
        if isinstance(v, dict):
            body = dumps(v, path)
            lines += ["", f"[{name}]"] + ([body] if body else [])
        elif _is_table_array(v):
            for item in v:
                body = dumps(item, path)
                lines += ["", f"[[{name}]]"] + ([body] if body else [])
    return "\n".join(lines).strip("\n") + ("\n" if not _path else "")
