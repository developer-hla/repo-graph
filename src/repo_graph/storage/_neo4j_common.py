"""Shared Neo4j storage normalization helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

DEFAULT_RELATIONSHIP_TYPE = "RELATED_TO"
RELATIONSHIP_TYPE_RE = re.compile(r"[^A-Z0-9_]")
PROPERTY_KEY_RE = re.compile(r"[^A-Za-z0-9_]")
SOURCE_SURFACE_ENTITY_TYPES = (
    "api_route",
    "deployment",
    "ingress",
    "package",
    "project",
    "service",
    "sql_function",
    "sql_table",
    "sql_view",
    "stored_procedure",
)


def json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def compact_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def optional_filter(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def lower_filter(value: str | None) -> str | None:
    normalized = optional_filter(value)
    if normalized is None:
        return None
    return normalized.lower()


def normalize_limit(value: int, maximum: int) -> int:
    if value < 1:
        raise ValueError("Limit must be at least 1.")
    if value > maximum:
        raise ValueError(f"Limit must be at most {maximum}.")
    return value


def normalize_direction(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"in", "out", "both"}:
        raise ValueError("Direction must be one of: in, out, both.")
    return normalized


def normalize_depth(value: int) -> int:
    if value < 1:
        raise ValueError("Depth must be at least 1.")
    if value > 3:
        raise ValueError("Depth must be at most 3.")
    return value


def normalize_edge_types(values: Iterable[str] | None) -> list[str] | None:
    if values is None:
        return None
    edge_types = sorted({value.strip() for value in values if value and value.strip()})
    return edge_types or None


def graph_items(graph_data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw_items = graph_data.get(key, [])
    if not isinstance(raw_items, list):
        raise ValueError(f"Graph field '{key}' must be a list.")
    return [item for item in raw_items if isinstance(item, dict)]


def neo4j_properties(raw: Mapping[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    nested = mapping_value(raw.get("properties"))
    for key, value in raw.items():
        if key == "properties":
            continue
        normalized = neo4j_property_value(value)
        if normalized is not None:
            properties[safe_property_key(key)] = normalized

    if nested:
        properties["properties_json"] = json.dumps(nested, sort_keys=True)
        for key, value in nested.items():
            normalized = neo4j_property_value(value)
            if normalized is not None:
                properties[f"property_{safe_property_key(key)}"] = normalized
    return properties


def neo4j_property_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple | set) and all(isinstance(item, bool | int | float | str) for item in value):
        return sorted(value) if isinstance(value, set) else list(value)
    return json.dumps(value, sort_keys=True)


def sanitize_relationship_type(value: str) -> str:
    normalized = RELATIONSHIP_TYPE_RE.sub("_", value.strip().upper()).strip("_")
    if not normalized:
        return DEFAULT_RELATIONSHIP_TYPE
    if normalized[0].isdigit():
        return f"EDGE_{normalized}"
    return normalized


def safe_property_key(value: Any) -> str:
    normalized = PROPERTY_KEY_RE.sub("_", str(value).strip()).strip("_")
    if not normalized:
        return "value"
    if normalized[0].isdigit():
        return f"property_{normalized}"
    return normalized


def mapping_value(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def required_string(value: Mapping[str, Any], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value:
        raise ValueError(f"Graph item must define non-empty '{key}'.")
    return raw_value


def string_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


__all__ = [
    "compact_dict",
    "graph_items",
    "json_object",
    "lower_filter",
    "mapping_value",
    "neo4j_properties",
    "neo4j_property_value",
    "normalize_depth",
    "normalize_direction",
    "normalize_edge_types",
    "normalize_limit",
    "optional_filter",
    "required_string",
    "safe_property_key",
    "sanitize_relationship_type",
    "string_or_none",
]
