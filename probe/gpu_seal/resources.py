"""Package-owned runtime resources."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

__all__ = ["RUNTIME_SCHEMA_NAMES", "load_schema"]

RUNTIME_SCHEMA_NAMES = (
    "experiment.schema.json",
    "provider-policy.schema.json",
    "report-card.schema.json",
    "result.schema.json",
)


def load_schema(name: str) -> dict[str, Any]:
    """Load one of the reviewed JSON schemas from the installed package."""
    if name not in RUNTIME_SCHEMA_NAMES:
        raise ValueError(
            f"unknown GPU-SEAL schema {name!r}; expected one of "
            f"{RUNTIME_SCHEMA_NAMES}"
        )
    resource = files("gpu_seal").joinpath("schemas", name)
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"installed GPU-SEAL package is missing runtime schema {name!r}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"schema {name!r} must contain a JSON object")
    return value
