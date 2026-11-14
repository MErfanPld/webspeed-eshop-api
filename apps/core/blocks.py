"""
Block validation with JSON Schema.

`data/block_definitions.json` is exported from the frontend registry
(src/builder/registry/block-definitions.ts). Each definition's field schema is
converted to a JSON Schema for the block's `data`. Unknown extra keys stay
allowed (internal `_style`, `_visibility`, `children`, … and forward
compatibility), but declared fields must have the right types.
"""
import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

DATA_FILE = Path(__file__).parent / "data" / "block_definitions.json"
MAX_DEPTH = 4

RESPONSIVE_NUMBER = {
    "oneOf": [
        {"type": "number"},
        {
            "type": "object",
            "properties": {k: {"type": ["number", "null"]} for k in ("desktop", "tablet", "mobile")},
            "additionalProperties": False,
        },
    ]
}


def _field_schema(field: dict) -> dict:
    t = field["type"]
    if t in ("text", "textarea", "url", "image", "color", "datetime"):
        return {"type": "string"}
    if t == "number":
        return {"type": ["number", "null"]}
    if t == "boolean":
        return {"type": "boolean"}
    if t == "select":
        return {"enum": [o["value"] for o in field.get("options", [])]}
    if t == "responsiveNumber":
        return RESPONSIVE_NUMBER
    if t == "productIds":
        return {"type": "array", "items": {"type": "string"}, "maxItems": 100}
    if t == "array":
        return {"type": "array", "maxItems": 200, "items": _object_schema(field.get("itemFields", []))}
    return {}


def _object_schema(fields: list[dict]) -> dict:
    """Fields with dotted paths become nested objects."""
    root: dict = {"type": "object", "properties": {}}
    for f in fields:
        parts = f["path"].split(".")
        node = root
        for p in parts[:-1]:
            node = node["properties"].setdefault(p, {"type": "object", "properties": {}})
        node["properties"][parts[-1]] = _field_schema(f)
    return root


@lru_cache(maxsize=1)
def _registry() -> dict:
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    common = raw["common"]
    out = {}
    for d in raw["definitions"]:
        schema = _object_schema(d["schema"] + common)
        schema["properties"]["children"] = {"type": "array"}
        schema["properties"]["_visibility"] = {
            "type": "object",
            "properties": {k: {"type": "boolean"} for k in ("desktop", "tablet", "mobile")},
        }
        out[d["type"]] = {
            "validator": Draft202012Validator(schema),
            "container": bool((d.get("nesting") or {}).get("canHaveChildren")),
            "defaultData": d["defaultData"],
        }
    return out


def known_types() -> set[str]:
    return set(_registry())


def default_data(block_type: str) -> dict:
    return json.loads(json.dumps(_registry()[block_type]["defaultData"]))


def _is_serializable(value, depth=0) -> bool:
    if depth > 12:
        return False
    if value is None or isinstance(value, (str, bool, int, float)):
        return True
    if isinstance(value, list):
        return all(_is_serializable(v, depth + 1) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_serializable(v, depth + 1) for k, v in value.items())
    return False


def validate_blocks(blocks, path: str = "blocks", depth: int = 0) -> list[dict]:
    """
    Validate a block list (recursively for containers).
    Returns normalized blocks; raises ValueError with a Persian message.
    """
    if not isinstance(blocks, list):
        raise ValueError(f"{path} باید آرایه باشد")
    reg = _registry()
    out = []
    for i, b in enumerate(blocks):
        where = f"{path}[{i}]"
        if not isinstance(b, dict):
            raise ValueError(f"{where}: بلوک باید شیء باشد")
        bid, btype, data = b.get("id"), b.get("type"), b.get("data")
        if not isinstance(bid, str) or not bid.strip():
            raise ValueError(f"{where}: شناسه بلوک الزامی است")
        if not isinstance(btype, str) or btype not in reg:
            raise ValueError(f"نوع بلوک ناشناخته: {btype} ({where})")
        if not isinstance(data, dict):
            raise ValueError(f"{where}: data باید شیء باشد")
        # children are validated recursively below; check the block's own data
        if not _is_serializable({k: v for k, v in data.items() if k != "children"}):
            raise ValueError(f"{where}: data شامل مقادیر غیرقابل‌ذخیره است")
        errors = sorted(reg[btype]["validator"].iter_errors(data), key=lambda e: list(e.path))
        if errors:
            e = errors[0]
            field = ".".join(str(p) for p in e.path) or "data"
            raise ValueError(f"مقدار نامعتبر در بلوک «{btype}» ({where}.{field})")
        children = data.get("children")
        if children is not None:
            if not reg[btype]["container"]:
                raise ValueError(f"{where}: بلوک «{btype}» نمی‌تواند فرزند داشته باشد")
            if depth + 1 > MAX_DEPTH:
                raise ValueError(f"{where}: عمق تودرتویی بیش از حد مجاز است")
            data = {**data, "children": validate_blocks(children, f"{where}.children", depth + 1)}
        out.append({"id": bid, "type": btype, "enabled": b.get("enabled") is not False, "data": data})
    return out
