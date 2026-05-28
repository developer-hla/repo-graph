"""Interaction report grouping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import add_if_present, compact_dict, mapping_value, string_value
from repo_graph.reports.interactions._examples import interaction_example

InteractionGroupKey = tuple[str, str, str, str, str, str, str, str]


def interaction_groups(edges: list[Mapping[str, Any]], examples_per_group: int) -> list[dict[str, Any]]:
    groups: dict[InteractionGroupKey, dict[str, Any]] = {}
    for edge in edges:
        properties = mapping_value(edge.get("properties"))
        key = (
            string_value(edge.get("source_name")) or "unknown",
            string_value(edge.get("target_source")) or "unresolved",
            string_value(edge.get("to_type")) or "unknown",
            string_value(edge.get("to_name")) or "unknown",
            string_value(edge.get("edge_type")) or "unknown",
            string_value(properties.get("target_boundary")) or "unknown",
            string_value(properties.get("dependency_scope")) or "unknown",
            string_value(properties.get("interaction_kind")) or "unknown",
        )
        group = groups.setdefault(
            key,
            {
                "from_source": key[0],
                "target_source": None if key[1] == "unresolved" else key[1],
                "to_type": key[2],
                "to_name": key[3],
                "edge_type": key[4],
                "target_boundary": key[5],
                "dependency_scope": key[6],
                "interaction_kind": key[7],
                "count": 0,
                "resolved_count": 0,
                "unresolved_count": 0,
                "parsers": set(),
                "protocols": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        if bool(edge.get("resolved")):
            group["resolved_count"] += 1
        else:
            group["unresolved_count"] += 1
        add_if_present(group["parsers"], string_value(edge.get("parser")))
        add_if_present(group["protocols"], string_value(properties.get("protocol")))
        if len(group["examples"]) < examples_per_group:
            group["examples"].append(interaction_example(edge))

    items = [finalize_interaction_group(group) for group in groups.values()]
    items.sort(
        key=lambda item: (
            -item["count"],
            item["from_source"],
            item.get("target_source") or "",
            item["target_boundary"],
            item["dependency_scope"],
            item["to_type"],
            item["to_name"],
        )
    )
    return items


def finalize_interaction_group(group: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "from_source": group["from_source"],
            "target_source": group["target_source"],
            "to_type": group["to_type"],
            "to_name": group["to_name"],
            "edge_type": group["edge_type"],
            "target_boundary": group["target_boundary"],
            "dependency_scope": group["dependency_scope"],
            "interaction_kind": group["interaction_kind"],
            "count": group["count"],
            "resolved_count": group["resolved_count"],
            "unresolved_count": group["unresolved_count"],
            "parsers": sorted(group["parsers"]),
            "protocols": sorted(group["protocols"]),
            "examples": group["examples"],
        }
    )
