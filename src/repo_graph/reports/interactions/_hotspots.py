"""Interaction report hotspot summaries."""

from __future__ import annotations

from typing import Any

from repo_graph.reports._common import add_if_present, compact_dict, string_value


def interaction_source_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for item in items:
        source_name = item["from_source"]
        hotspot = hotspots.setdefault(
            source_name,
            {"source_name": source_name, "count": 0, "group_count": 0, "target_sources": set(), "edge_types": set()},
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["target_sources"], string_value(item.get("target_source")))
        add_if_present(hotspot["edge_types"], item["edge_type"])
    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "group_count": hotspot["group_count"],
                "target_sources": sorted(hotspot["target_sources"]),
                "edge_types": sorted(hotspot["edge_types"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def interaction_target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    for item in items:
        key = (string_value(item.get("target_source")), item["to_type"], item["to_name"])
        hotspot = hotspots.setdefault(
            key,
            {
                "target_source": key[0],
                "to_type": key[1],
                "to_name": key[2],
                "count": 0,
                "group_count": 0,
                "from_sources": set(),
                "edge_types": set(),
            },
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["from_sources"], item["from_source"])
        add_if_present(hotspot["edge_types"], item["edge_type"])
    return sorted(
        (
            compact_dict(
                {
                    "target_source": hotspot["target_source"],
                    "to_type": hotspot["to_type"],
                    "to_name": hotspot["to_name"],
                    "count": hotspot["count"],
                    "group_count": hotspot["group_count"],
                    "from_sources": sorted(hotspot["from_sources"]),
                    "edge_types": sorted(hotspot["edge_types"]),
                }
            )
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (
            -hotspot["count"],
            hotspot.get("target_source") or "",
            hotspot["to_type"],
            hotspot["to_name"],
        ),
    )[:limit]
