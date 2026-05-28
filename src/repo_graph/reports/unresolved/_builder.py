"""Unresolved-reference report assembly."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import (
    DEFAULT_EXAMPLE_LIMIT,
    DEFAULT_GROUP_LIMIT,
    compact_dict,
    edge_from_item,
    edge_matches,
    graph_items,
    mapping_value,
    string_value,
    validate_positive_int,
)
from repo_graph.reports.unresolved._groups import unresolved_groups
from repo_graph.reports.unresolved._hotspots import source_hotspots_from_edges, target_hotspots
from repo_graph.reports.unresolved._summaries import classification_group_summaries, report_summary


def unresolved_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    edges = [edge for edge in graph_items(graph_data, "edges") if not bool(edge.get("resolved"))]
    return unresolved_report(
        edges,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def unresolved_report_from_items(
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    edges = [edge_from_item(item) for item in items]
    return unresolved_report(
        edges,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def unresolved_report(
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")
    filtered_edges = [edge for edge in edges if edge_matches(edge, source_name, edge_type)]
    items = unresolved_groups(filtered_edges, examples_per_group)
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "edge_type": edge_type}),
            "summary": report_summary(filtered_edges, items, limited_items),
            "classification_groups": classification_group_summaries(items),
            "source_hotspots": source_hotspots_from_edges(filtered_edges),
            "target_hotspots": target_hotspots(items),
            "items": limited_items,
        }
    )
