"""Blast-radius report assembly."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import graph_items, mapping_value, string_value, validate_positive_int
from repo_graph.reports.blast_radius._profiles import (
    DEFAULT_BLAST_RADIUS_DEPTH,
    DEFAULT_BLAST_RADIUS_LIMIT,
    blast_radius_profile_edge_types,
    normalize_blast_radius_direction,
    normalize_blast_radius_profile,
    validate_blast_radius_depth,
)
from repo_graph.reports.blast_radius._summaries import (
    blast_radius_path_groups,
    blast_radius_sources,
    blast_radius_summary,
)
from repo_graph.reports.blast_radius._traversal import blast_radius_items_from_graph


def blast_radius_report_from_graph(
    graph_data: Mapping[str, Any],
    entity_id: str,
    direction: str = "in",
    edge_type: str | None = None,
    depth: int = DEFAULT_BLAST_RADIUS_DEPTH,
    limit: int = DEFAULT_BLAST_RADIUS_LIMIT,
    profile: str = "impact",
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    entities_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in graph_items(graph_data, "entities")
        if string_value(entity.get("entity_id"))
    }
    entity = entities_by_id.get(entity_id)
    if entity is None:
        raise KeyError(entity_id)
    normalized_profile = normalize_blast_radius_profile(profile)
    allowed_edge_types = blast_radius_profile_edge_types(normalized_profile, edge_type)
    items = blast_radius_items_from_graph(
        entities_by_id,
        graph_items(graph_data, "edges"),
        entity_id,
        direction=direction,
        edge_type=edge_type,
        allowed_edge_types=allowed_edge_types,
        depth=depth,
        limit=limit,
    )
    return blast_radius_report_from_items(
        entity,
        items,
        entity_id=entity_id,
        direction=direction,
        edge_type=edge_type,
        depth=depth,
        limit=limit,
        profile=normalized_profile,
        allowed_edge_types=allowed_edge_types,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def blast_radius_report_from_items(
    entity: Mapping[str, Any],
    items: Iterable[Mapping[str, Any]],
    entity_id: str | None = None,
    direction: str = "in",
    edge_type: str | None = None,
    depth: int = DEFAULT_BLAST_RADIUS_DEPTH,
    limit: int | None = DEFAULT_BLAST_RADIUS_LIMIT,
    profile: str = "impact",
    allowed_edge_types: Iterable[str] | None = None,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_profile = normalize_blast_radius_profile(profile)
    normalized_direction = normalize_blast_radius_direction(direction)
    validate_blast_radius_depth(depth)
    if limit is not None:
        validate_positive_int(limit, "limit")
    edge_types = (
        frozenset(allowed_edge_types)
        if allowed_edge_types is not None
        else blast_radius_profile_edge_types(normalized_profile, edge_type)
    )
    item_list = list(items)
    if limit is not None:
        item_list = item_list[:limit]
    affected_sources = blast_radius_sources(item_list)
    path_groups = blast_radius_path_groups(item_list)
    return {
        "scope_name": scope_name,
        "generated_at": generated_at,
        "entity": dict(entity),
        "entity_id": entity_id or string_value(entity.get("entity_id")),
        "direction": normalized_direction,
        "depth": depth,
        "edge_type": edge_type,
        "profile": normalized_profile,
        "allowed_edge_types": sorted(edge_types) if edge_types else None,
        "limit": limit,
        "items": item_list,
        "count": len(item_list),
        "affected_source_count": len(affected_sources),
        "affected_sources": affected_sources,
        "path_groups": path_groups,
        "summary": blast_radius_summary(item_list, affected_sources, path_groups),
    }
