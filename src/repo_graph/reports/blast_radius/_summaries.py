"""Blast-radius grouping and summary helpers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import mapping_value, string_value

BLAST_RADIUS_GROUP_EXAMPLE_LIMIT = 5


def blast_radius_report_source_name(item: Mapping[str, Any]) -> str:
    neighbor = mapping_value(item.get("neighbor"))
    neighbor_source = string_value(neighbor.get("source_name"))
    if neighbor_source:
        return neighbor_source
    edge = mapping_value(item.get("edge"))
    return string_value(edge.get("source_name")) or "unknown"


def blast_radius_report_neighbor_type(item: Mapping[str, Any]) -> str:
    neighbor = mapping_value(item.get("neighbor"))
    return string_value(neighbor.get("entity_type")) or string_value(neighbor.get("target_type")) or "unknown"


def blast_radius_sources(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        source_name = blast_radius_report_source_name(item)
        group = grouped.setdefault(
            source_name,
            {
                "source_name": source_name,
                "count": 0,
                "min_depth": item.get("depth"),
                "entity_types": set(),
                "edge_types": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        group["min_depth"] = min_depth_value(group["min_depth"], item.get("depth"))
        add_string_value(group["entity_types"], blast_radius_report_neighbor_type(item))
        add_string_value(group["edge_types"], string_value(mapping_value(item.get("edge")).get("edge_type")))
        if len(group["examples"]) < BLAST_RADIUS_GROUP_EXAMPLE_LIMIT:
            group["examples"].append(item)

    result = [
        {
            "source_name": group["source_name"],
            "count": group["count"],
            "min_depth": group["min_depth"],
            "entity_types": sorted(group["entity_types"]),
            "edge_types": sorted(group["edge_types"]),
            "examples": group["examples"],
        }
        for group in grouped.values()
    ]
    result.sort(key=lambda item: (item["min_depth"] or 0, -item["count"], item["source_name"]))
    return result


def blast_radius_path_groups(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        source_name = blast_radius_report_source_name(item)
        edge_type = string_value(mapping_value(item.get("edge")).get("edge_type")) or "unknown"
        key = (source_name, edge_type)
        group = grouped.setdefault(
            key,
            {
                "source_name": source_name,
                "edge_type": edge_type,
                "count": 0,
                "min_depth": item.get("depth"),
                "examples": [],
            },
        )
        group["count"] += 1
        group["min_depth"] = min_depth_value(group["min_depth"], item.get("depth"))
        if len(group["examples"]) < BLAST_RADIUS_GROUP_EXAMPLE_LIMIT:
            group["examples"].append(item)

    result = list(grouped.values())
    result.sort(key=lambda item: (item["min_depth"] or 0, -item["count"], item["source_name"], item["edge_type"]))
    return result


def blast_radius_summary(
    items: list[Mapping[str, Any]],
    affected_sources: list[Mapping[str, Any]],
    path_groups: list[Mapping[str, Any]],
) -> dict[str, Any]:
    edge_type_counts: Counter[str] = Counter()
    neighbor_type_counts: Counter[str] = Counter()
    depths = [item.get("depth") for item in items if isinstance(item.get("depth"), int)]
    for item in items:
        edge_type_counts[string_value(mapping_value(item.get("edge")).get("edge_type")) or "unknown"] += 1
        neighbor_type_counts[blast_radius_report_neighbor_type(item)] += 1
    return {
        "path_count": len(items),
        "affected_source_count": len(affected_sources),
        "path_group_count": len(path_groups),
        "max_observed_depth": max(depths) if depths else None,
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "neighbor_type_counts": dict(sorted(neighbor_type_counts.items())),
    }


def min_depth_value(left: Any, right: Any) -> int | None:
    depths = [value for value in (left, right) if isinstance(value, int)]
    return min(depths) if depths else None


def add_string_value(values: set[str], value: Any) -> None:
    if isinstance(value, str) and value:
        values.add(value)
