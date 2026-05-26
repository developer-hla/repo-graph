"""Shared helpers for report builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_GROUP_LIMIT = 50
DEFAULT_EXAMPLE_LIMIT = 3


def edge_from_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    edge = item.get("edge")
    if isinstance(edge, Mapping):
        return edge
    return item


def edge_matches(edge: Mapping[str, Any], source_name: str | None, edge_type: str | None) -> bool:
    if source_name and edge.get("source_name") != source_name:
        return False
    return not (edge_type and edge.get("edge_type") != edge_type)


def graph_items(graph_data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw_items = graph_data.get(key, [])
    if not isinstance(raw_items, list):
        raise ValueError(f"Graph field '{key}' must be a list.")
    return [item for item in raw_items if isinstance(item, Mapping)]


def mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def string_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def add_if_present(values: set[str], value: str | None) -> None:
    if value:
        values.add(value)


def compact_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, {})}


def validate_positive_int(value: int, name: str) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1.")
