"""Shared serialization helpers for harness integrations."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any


def json_default(obj: Any) -> Any:
    """Fallback serializer for objects ``json.dumps`` can't handle natively.

    Tool results often include Pydantic models, dataclasses, or other rich
    objects. Fall back to their dict representation, then to ``str()`` as a
    last resort so adjudication never fails on serialization.
    """
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump()
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return str(obj)


def to_json_str(value: Any) -> str:
    """Serialize a tool result to a string for adjudication payloads.

    Passes strings through unchanged; falls back to ``json_default`` for
    non-native types.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, default=json_default)
