"""Small validator for the JSON Schema subset used by our portable v1 contracts."""
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    pass


def digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe_path(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or "\\" in value or ":" in value or value != p.as_posix():
        raise ContractError("Expected a normalized repository-relative path")
    return value


def within(path, scopes):
    safe_path(path)
    return any(path == s or path.startswith(s.rstrip("/") + "/") for s in scopes)


def validate(name, value):
    schema = json.loads((ROOT / "contracts" / "v1" / (name + ".schema.json")).read_text())
    _validate(schema, value, name)
    return value


def _validate(schema, value, location):
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    kind = schema.get("type")
    if kind and (not isinstance(value, types[kind]) or (kind == "integer" and isinstance(value, bool))):
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
        if len(value.strip()) < schema.get("minLength", 0):
            raise ContractError(location + ": empty string")
        if schema.get("pattern") and not re.fullmatch(schema["pattern"], value):
            raise ContractError(location + ": invalid format")
    if isinstance(value, int) and "minimum" in schema and value < schema["minimum"]:
        raise ContractError(location + ": below minimum")
