"""Interaction report summary calculations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import mapping_value, string_value


def interaction_summary(
    edges: list[Mapping[str, Any]],
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
) -> dict[str, Any]:
    boundary_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    edge_type_counts: Counter[str] = Counter()
    for edge in edges:
        properties = mapping_value(edge.get("properties"))
        boundary_counts[string_value(properties.get("target_boundary")) or "unknown"] += 1
        scope_counts[string_value(properties.get("dependency_scope")) or "unknown"] += 1
        kind_counts[string_value(properties.get("interaction_kind")) or "unknown"] += 1
        edge_type_counts[string_value(edge.get("edge_type")) or "unknown"] += 1
    return {
        "interaction_edge_count": len(edges),
        "resolved_edge_count": sum(1 for edge in edges if bool(edge.get("resolved"))),
        "unresolved_edge_count": sum(1 for edge in edges if not bool(edge.get("resolved"))),
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "target_boundary_counts": dict(sorted(boundary_counts.items())),
        "dependency_scope_counts": dict(sorted(scope_counts.items())),
        "interaction_kind_counts": dict(sorted(kind_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
    }
