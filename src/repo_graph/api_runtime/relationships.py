"""Relationship grouping helpers for API responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def relationship_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in items:
        edge = item.get("edge", {})
        neighbor = item.get("neighbor", {})
        direction = str(item.get("direction") or "unknown")
        edge_type = string_mapping_value(edge, "edge_type") or "unknown"
        source_name = relationship_source_name(edge, neighbor)
        neighbor_type = relationship_neighbor_type(neighbor)
        key = (direction, edge_type, source_name, neighbor_type)
        group = grouped.setdefault(
            key,
            {
                "direction": direction,
                "edge_type": edge_type,
                "source_name": source_name,
                "neighbor_type": neighbor_type,
                "count": 0,
                "min_depth": item.get("depth"),
                "examples": [],
            },
        )
        group["count"] += 1
        group["min_depth"] = min_depth(group["min_depth"], item.get("depth"))
        if len(group["examples"]) < 5:
            group["examples"].append(item)

    result = list(grouped.values())
    result.sort(
        key=lambda item: (
            item["direction"],
            -item["count"],
            item["source_name"],
            item["edge_type"],
            item["neighbor_type"],
        )
    )
    return result


def relationship_evidence_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, bool], dict[str, Any]] = {}
    for item in items:
        edge = item.get("edge", {})
        edge_type = string_mapping_value(edge, "edge_type") or ""
        from_type = string_mapping_value(item, "from_type") or ""
        to_type = string_mapping_value(item, "to_type") or ""
        from_source = string_mapping_value(item, "from_source") or ""
        to_source = string_mapping_value(item, "to_source") or ""
        resolved = bool(edge.get("resolved")) if isinstance(edge, Mapping) else False
        key = (edge_type, from_type, to_type, from_source, to_source, resolved)
        group = grouped.setdefault(
            key,
            {
                "edge_type": edge_type,
                "from_type": from_type,
                "to_type": to_type,
                "from_source": from_source,
                "to_source": to_source,
                "resolved": resolved,
                "count": 0,
                "examples": [],
            },
        )
        group["count"] += 1
        if len(group["examples"]) < 5:
            group["examples"].append(item)

    result = list(grouped.values())
    result.sort(
        key=lambda item: (
            -item["count"],
            item["from_source"],
            item["to_source"],
            item["edge_type"],
            item["from_type"],
            item["to_type"],
        )
    )
    return result


def relationship_source_name(edge: Any, neighbor: Any) -> str:
    neighbor_source = string_mapping_value(neighbor, "source_name")
    if neighbor_source:
        return neighbor_source
    edge_source = string_mapping_value(edge, "source_name")
    if edge_source:
        return edge_source
    return "unknown"


def relationship_neighbor_type(neighbor: Any) -> str:
    return string_mapping_value(neighbor, "entity_type") or string_mapping_value(neighbor, "target_type") or "unknown"


def string_mapping_value(value: Any, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    item = value.get(key)
    if isinstance(item, str) and item:
        return item
    return None


def min_depth(left: Any, right: Any) -> int | None:
    depths = [value for value in (left, right) if isinstance(value, int)]
    return min(depths) if depths else None


def add_if_string(values: set[str], value: Any) -> None:
    if isinstance(value, str) and value:
        values.add(value)


__all__ = [
    "add_if_string",
    "min_depth",
    "relationship_evidence_groups",
    "relationship_groups",
    "relationship_neighbor_type",
    "relationship_source_name",
    "string_mapping_value",
]
