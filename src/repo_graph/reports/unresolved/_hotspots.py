"""Unresolved-reference hotspot summaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import add_if_present, string_value
from repo_graph.reports.unresolved._classification import classification_rank, classify_unresolved_edge


def source_hotspots_from_edges(edges: list[Mapping[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for edge in edges:
        source_name = string_value(edge.get("source_name")) or "unknown"
        classification, _reason = classify_unresolved_edge(edge)
        edge_type = string_value(edge.get("edge_type")) or "unknown"
        target_type = string_value(edge.get("to_type")) or "unknown"
        target_name = string_value(edge.get("to_name")) or "unknown"
        hotspot = hotspots.setdefault(
            source_name,
            {
                "source_name": source_name,
                "count": 0,
                "group_keys": set(),
                "classifications": set(),
                "edge_types": set(),
            },
        )
        hotspot["count"] += 1
        hotspot["group_keys"].add((edge_type, target_type, target_name, classification))
        add_if_present(hotspot["classifications"], classification)
        add_if_present(hotspot["edge_types"], edge_type)

    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "group_count": len(hotspot["group_keys"]),
                "classifications": sorted(hotspot["classifications"], key=classification_rank),
                "edge_types": sorted(hotspot["edge_types"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["to_type"], item["to_name"])
        hotspot = hotspots.setdefault(
            key,
            {
                "to_type": item["to_type"],
                "to_name": item["to_name"],
                "count": 0,
                "group_count": 0,
                "classifications": set(),
                "edge_types": set(),
                "source_names": set(),
            },
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["classifications"], item["classification"])
        add_if_present(hotspot["edge_types"], item["edge_type"])
        hotspot["source_names"].update(item["source_names"])

    return sorted(
        (
            {
                "to_type": hotspot["to_type"],
                "to_name": hotspot["to_name"],
                "count": hotspot["count"],
                "group_count": hotspot["group_count"],
                "classifications": sorted(hotspot["classifications"], key=classification_rank),
                "edge_types": sorted(hotspot["edge_types"]),
                "source_names": sorted(hotspot["source_names"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["to_type"], hotspot["to_name"]),
    )[:limit]
