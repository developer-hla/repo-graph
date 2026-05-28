"""Interaction report assembly."""

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
from repo_graph.reports.interactions._groups import interaction_groups
from repo_graph.reports.interactions._hotspots import (
    interaction_source_hotspots,
    interaction_target_hotspots,
)
from repo_graph.reports.interactions._summaries import interaction_summary
from repo_graph.vocabulary import INTERACTION_EDGE_TYPES


def interactions_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    entities_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in graph_items(graph_data, "entities")
        if string_value(entity.get("entity_id"))
    }
    edges = [
        interaction_edge_with_target_source(edge, entities_by_id)
        for edge in graph_items(graph_data, "edges")
        if edge.get("edge_type") in INTERACTION_EDGE_TYPES
    ]
    return interactions_report(
        edges,
        source_name=source_name,
        target_source=target_source,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def interactions_report_from_items(
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    return interactions_report(
        [interaction_edge_from_item(item) for item in items],
        source_name=source_name,
        target_source=target_source,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def interactions_report(
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")
    filtered_edges = [
        edge
        for edge in edges
        if edge.get("edge_type") in INTERACTION_EDGE_TYPES
        and interaction_edge_matches(edge, source_name, target_source, edge_type)
    ]
    items = interaction_groups(filtered_edges, examples_per_group)
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "target_source": target_source, "edge_type": edge_type}),
            "summary": interaction_summary(filtered_edges, items, limited_items),
            "source_hotspots": interaction_source_hotspots(items),
            "target_hotspots": interaction_target_hotspots(items),
            "items": limited_items,
        }
    )


def interaction_edge_with_target_source(
    edge: Mapping[str, Any],
    entities_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    target_entity_id = string_value(edge.get("to_entity_id"))
    target_entity = entities_by_id.get(target_entity_id) if target_entity_id else None
    if not target_entity:
        return edge
    return {**edge, "target_source": string_value(target_entity.get("source_name"))}


def interaction_edge_from_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    edge = edge_from_item(item)
    target_source = string_value(item.get("to_source"))
    target = item.get("target")
    if not target_source and isinstance(target, Mapping):
        target_source = string_value(target.get("source_name"))
    if not target_source:
        return edge
    return {**edge, "target_source": target_source}


def interaction_edge_matches(
    edge: Mapping[str, Any],
    source_name: str | None,
    target_source: str | None,
    edge_type: str | None,
) -> bool:
    if not edge_matches(edge, source_name, edge_type):
        return False
    return not (target_source and edge.get("target_source") != target_source)
