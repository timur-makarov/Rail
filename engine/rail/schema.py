"""A small reader of JSON Schema, for the JSON the engine checks against a schema file of its own.

It knows the keywords those files use and no more: `type` (a name or a list of names), `enum`, `const`, `required`,
`properties`, `additionalProperties` (false, or a schema for the other keys), `items`, `anyOf`, and `$ref` to a
`#/$defs/NAME` of the same file. A keyword it does not know is ignored, as a description is.
"""

TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list,
         "null": type(None)}


def _is(value, name):
    if name in ("integer", "number") and isinstance(value, bool):
        return False  # in Python True is an int; in JSON it is not a number
    return isinstance(value, TYPES[name])


def check(value, schema, root=None, at="$"):
    """The ways `value` breaks `schema`, each as "where: what"; an empty list when it holds. `root` is the file the
    schema is part of, where a `$ref` is looked up."""
    root = root if root is not None else schema
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return check(value, (root.get("$defs") or {})[name], root, at)
    if "anyOf" in schema:
        tries = [check(value, option, root, at) for option in schema["anyOf"]]
        if all(tries):
            return [f"{at}: fits none of the {len(tries)} shapes allowed here ({tries[0][0]})"]
    names = schema.get("type")
    if names is not None:
        names = [names] if isinstance(names, str) else names
        if not any(_is(value, name) for name in names):
            return [f"{at}: is {type(value).__name__}, not {' or '.join(names)}"]
    found = []
    if "const" in schema and value != schema["const"]:
        found.append(f"{at}: is {value!r}, not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{at}: {value!r} is not one of {', '.join(map(str, schema['enum']))}")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        found += [f"{at}: lacks '{key}'" for key in schema.get("required") or [] if key not in value]
        other = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                found += check(item, properties[key], root, f"{at}.{key}")
            elif other is False:
                found.append(f"{at}: has a key the schema does not name, '{key}'")
            elif isinstance(other, dict):
                found += check(item, other, root, f"{at}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value):
            found += check(item, schema["items"], root, f"{at}[{i}]")
    return found
