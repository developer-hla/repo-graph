"""Unresolved-reference report grouping."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import add_if_present, string_value
from repo_graph.reports.unresolved._classification import classify_unresolved_edge, recommended_action
from repo_graph.reports.unresolved._examples import edge_example

UnresolvedGroupKey = tuple[str, str, str, str]


def unresolved_groups(edges: list[Mapping[str, Any]], examples_per_group: int) -> list[dict[str, Any]]:
    groups: dict[UnresolvedGroupKey, dict[str, Any]] = {}
    for edge in edges:
        classification, reason = classify_unresolved_edge(edge)
        key = (
            string_value(edge.get("edge_type")) or "unknown",
            string_value(edge.get("to_type")) or "unknown",
            string_value(edge.get("to_name")) or "unknown",
            classification,
        )
        group = groups.setdefault(
            key,
            {
                "edge_type": key[0],
                "to_type": key[1],
                "to_name": key[2],
                "classification": classification,
                "classification_reason": reason,
                "count": 0,
                "source_names": set(),
                "parsers": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        add_if_present(group["source_names"], string_value(edge.get("source_name")))
        add_if_present(group["parsers"], string_value(edge.get("parser")))
        if len(group["examples"]) < examples_per_group:
            group["examples"].append(edge_example(edge))

    items = [finalize_group(group) for group in groups.values()]
    items.sort(key=lambda item: (-item["count"], item["classification"], item["edge_type"], item["to_name"]))
    return items


def finalize_group(group: Mapping[str, Any]) -> dict[str, Any]:
    classification = group["classification"]
    return {
        "edge_type": group["edge_type"],
        "to_type": group["to_type"],
        "to_name": group["to_name"],
        "classification": classification,
        "classification_reason": group["classification_reason"],
        "recommended_action": recommended_action(classification),
        "count": group["count"],
        "source_names": sorted(group["source_names"]),
        "parsers": sorted(group["parsers"]),
        "examples": group["examples"],
    }
