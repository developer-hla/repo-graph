"""Unresolved-reference report summary calculations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import add_if_present
from repo_graph.reports.unresolved._classification import classification_rank, recommended_action


def classification_group_summaries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        classification = item["classification"]
        group = groups.setdefault(
            classification,
            {
                "classification": classification,
                "recommended_action": recommended_action(classification),
                "count": 0,
                "group_count": 0,
                "source_names": set(),
                "edge_types": set(),
            },
        )
        group["count"] += item["count"]
        group["group_count"] += 1
        group["source_names"].update(item["source_names"])
        add_if_present(group["edge_types"], item["edge_type"])

    summaries = [
        {
            "classification": group["classification"],
            "recommended_action": group["recommended_action"],
            "count": group["count"],
            "group_count": group["group_count"],
            "source_names": sorted(group["source_names"]),
            "edge_types": sorted(group["edge_types"]),
        }
        for group in groups.values()
    ]
    summaries.sort(key=lambda group: (classification_rank(group["classification"]), -group["count"]))
    return summaries


def report_summary(
    edges: list[Mapping[str, Any]],
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
) -> dict[str, Any]:
    classification_edge_counts: Counter[str] = Counter()
    classification_group_counts = Counter(item["classification"] for item in items)
    for item in items:
        classification_edge_counts[item["classification"]] += item["count"]
    return {
        "unresolved_edge_count": len(edges),
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "classification_edge_counts": dict(sorted(classification_edge_counts.items())),
        "classification_group_counts": dict(sorted(classification_group_counts.items())),
    }
