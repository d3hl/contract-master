"""Small validator for the JSON Schema subset used by our portable v1 contracts."""
import functools
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    pass


class ProviderError(ContractError):
    """A provider call failed or returned incomplete data. Says nothing about the issue itself."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe_path(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or ":" in value or value != p.as_posix():
        raise ContractError("Expected a normalized repository-relative path")
    return value


def within(path, scopes):
    safe_path(path)
    return any(path == s or path.startswith(s.rstrip("/") + "/") for s in scopes)


TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
# The JSON Schema subset _validate implements. Anything else in a schema is an
# error, so a new keyword can never be silently ignored.
KEYWORDS = {"$schema", "$id", "title", "type", "properties", "required", "additionalProperties", "items",
            "const", "enum", "minItems", "uniqueItems", "minLength", "pattern", "minimum"}


@functools.lru_cache(maxsize=None)
def schema(name):
    value = json.loads((ROOT / "contracts" / "v1" / (name + ".schema.json")).read_text())
    check_schema(value, name)
    return value


def check_schema(node, location="schema"):
    unknown = set(node) - KEYWORDS
    if unknown:
        raise ContractError(location + ": unsupported schema keyword " + ", ".join(sorted(unknown)))
    if "type" in node and node["type"] not in TYPES:
        raise ContractError(location + ": unsupported type " + str(node["type"]))
    if not isinstance(node.get("additionalProperties", False), bool):
        raise ContractError(location + ": additionalProperties must be true or false")
    pattern = node.get("pattern")
    if pattern is not None and not (pattern.startswith("^") and pattern.endswith("$")):
        # Standard validators search; ours full-matches. Anchors make both agree.
        raise ContractError(location + ": pattern must be anchored with ^ and $")
    for key, child in node.get("properties", {}).items():
        check_schema(child, location + "." + key)
    if "items" in node:
        check_schema(node["items"], location + "[]")


def validate(name, value):
    _validate(schema(name), value, name)
    return value


def _validate(schema, value, location):
    kind = schema.get("type")
    if kind and (not isinstance(value, TYPES[kind]) or (kind == "integer" and isinstance(value, bool))):
        raise ContractError(location + ": invalid type")
    if "const" in schema and value != schema["const"]:
        raise ContractError(location + ": unsupported constant/version")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(location + ": invalid enum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ContractError(location + ": missing " + key)
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise ContractError(location + ": unknown fields")
        for key, item in value.items():
            if key in props:
                _validate(props[key], item, location + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ContractError(location + ": empty collection")
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ContractError(location + ": duplicate items")
        for i, item in enumerate(value):
            _validate(schema.get("items", {}), item, location + "[" + str(i) + "]")
    if isinstance(value, str):
        # Deliberately stricter than JSON Schema: whitespace-only text does not count.
        if len(value.strip()) < schema.get("minLength", 0):
            raise ContractError(location + ": empty string")
        if schema.get("pattern") and not re.fullmatch(schema["pattern"], value):
            raise ContractError(location + ": invalid format")
    if isinstance(value, int) and "minimum" in schema and value < schema["minimum"]:
        raise ContractError(location + ": below minimum")
