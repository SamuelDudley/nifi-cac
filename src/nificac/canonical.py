"""Deterministic serialization.

Two flows that behave the same produce byte-identical output here, regardless
of export order, NiFi instance, or canvas geometry.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def _sort_key(item: Any) -> tuple[int, str]:
    """Total order over canonicalized values. The leading int keeps mixed-type
    lists comparable."""
    if isinstance(item, dict):
        for key in ("identifier", "name", "type"):
            if key in item:
                return (0, str(item[key]))
        return (1, json.dumps(item, sort_keys=True))
    return (2, str(item))


def canonicalize(value: Any, *, ordered: bool = False) -> Any:
    """Drop volatile fields, then impose a total order on what remains.

    A model field that is None or empty is omitted: it carries no
    configuration. A None *inside* a dict is kept, because
    ``{"Password": null}`` means "set but sensitive" and is not the same as an
    absent key.
    """
    if isinstance(value, BaseModel):
        out: dict[str, Any] = {}
        for name, field in type(value).model_fields.items():
            extra = field.json_schema_extra
            extra = extra if isinstance(extra, dict) else {}
            if extra.get("volatile"):
                continue
            attr = getattr(value, name)
            if attr is None or attr == [] or attr == {}:
                continue
            out[field.alias or name] = canonicalize(attr, ordered=bool(extra.get("ordered")))
        for key, attr in (value.model_extra or {}).items():
            out[key] = canonicalize(attr)
        return {k: out[k] for k in sorted(out)}

    if isinstance(value, dict):
        return {k: canonicalize(value[k]) for k in sorted(value, key=str)}

    if isinstance(value, list):
        items = [canonicalize(v) for v in value]
        return items if ordered else sorted(items, key=_sort_key)

    return value


def canonical_json(model: BaseModel) -> str:
    """Text form written to ``flow.json``. Ends with a newline."""
    return json.dumps(canonicalize(model), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def fingerprint(model: BaseModel) -> str:
    """SHA-256 over the canonical form with no whitespace."""
    payload = json.dumps(
        canonicalize(model), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
