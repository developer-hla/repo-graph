"""Neo4j query response builders for the API."""

from __future__ import annotations

from typing import Any

from repo_graph.api_runtime.constants import UNRESOLVED_REPORT_EDGE_LIMIT
from repo_graph.api_runtime.coverage import coverage_warnings_for_entity_source
from repo_graph.api_runtime.relationships import relationship_evidence_groups, relationship_groups
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.reports import (
    blast_radius_profile_edge_types,
    blast_radius_report_from_items,
    normalize_blast_radius_profile,
    unresolved_report_from_items,
)
from repo_graph.storage import (
    get_entity,
    get_entity_neighbors,
    list_unresolved_edges,
    read_graph_overview,
    read_graph_scope,
    read_source_overview,
    search_entities,
    search_relationships,
)
from repo_graph.vocabulary import IMPACT_EDGE_TYPES


def search_entities_response(
    settings: RuntimeSettings,
    query: str | None,
    entity_type: str | None,
    source_name: str | None,
    limit: int,
) -> dict[str, Any]:
    items = search_entities(
        settings.neo4j_settings(),
        query=query,
        entity_type=entity_type,
        source_name=source_name,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


def relationship_search_response(
    settings: RuntimeSettings,
    from_source: str | None,
    to_source: str | None,
    edge_type: str | None,
    from_type: str | None,
    to_type: str | None,
    resolved: bool | None,
    limit: int,
) -> dict[str, Any]:
    items = search_relationships(
        settings.neo4j_settings(),
        from_source=from_source,
        to_source=to_source,
        edge_type=edge_type,
        from_type=from_type,
        to_type=to_type,
        resolved=resolved,
        limit=limit,
    )
    return {
        "filters": relationship_filters_payload(
            from_source=from_source,
            to_source=to_source,
            edge_type=edge_type,
            from_type=from_type,
            to_type=to_type,
            resolved=resolved,
        ),
        "items": items,
        "groups": relationship_evidence_groups(items),
        "count": len(items),
        "limit": limit,
    }


def relationship_filters_payload(
    from_source: str | None,
    to_source: str | None,
    edge_type: str | None,
    from_type: str | None,
    to_type: str | None,
    resolved: bool | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    add_optional_filter(filters, "from_source", from_source)
    add_optional_filter(filters, "to_source", to_source)
    add_optional_filter(filters, "type", edge_type)
    add_optional_filter(filters, "from_type", from_type)
    add_optional_filter(filters, "to_type", to_type)
    if resolved is not None:
        filters["resolved"] = resolved
    return filters


def add_optional_filter(filters: dict[str, Any], name: str, value: str | None) -> None:
    if value is not None and value.strip():
        filters[name] = value.strip()


def scope_response(settings: RuntimeSettings) -> dict[str, Any]:
    return read_graph_scope(settings.neo4j_settings())


def sources_response(settings: RuntimeSettings) -> dict[str, Any]:
    scope = scope_response(settings)
    items = scope.get("sources", [])
    if not isinstance(items, list):
        items = []
    return {
        "items": items,
        "count": len(items),
        "loaded": bool(scope.get("loaded")),
        "scope_name": scope.get("scope_name"),
        "generated_at": scope.get("generated_at"),
    }


def explore_response(settings: RuntimeSettings, limit: int) -> dict[str, Any]:
    return read_graph_overview(settings.neo4j_settings(), limit=limit)


def source_overview_response(settings: RuntimeSettings, source_name: str, limit: int) -> dict[str, Any]:
    overview = read_source_overview(
        settings.neo4j_settings(),
        source_name,
        limit=limit,
        use_edge_types=IMPACT_EDGE_TYPES,
    )
    if overview is None:
        raise KeyError(source_name)
    unresolved_items = list_unresolved_edges(
        settings.neo4j_settings(),
        source_name=source_name,
        edge_type=None,
        limit=UNRESOLVED_REPORT_EDGE_LIMIT,
    )
    overview["unresolved_report"] = unresolved_report_from_items(
        unresolved_items,
        source_name=source_name,
        edge_type=None,
        group_limit=limit,
        examples_per_group=3,
    )
    return overview


def entity_response(settings: RuntimeSettings, entity_id: str) -> dict[str, Any]:
    entity = get_entity(settings.neo4j_settings(), entity_id)
    if entity is None:
        raise KeyError(entity_id)
    return entity


def entity_overview_response(settings: RuntimeSettings, entity_id: str, limit: int) -> dict[str, Any]:
    neo4j_settings = settings.neo4j_settings()
    entity = get_entity(neo4j_settings, entity_id)
    if entity is None:
        raise KeyError(entity_id)
    incoming = get_entity_neighbors(
        neo4j_settings,
        entity_id,
        direction="in",
        depth=1,
        limit=limit,
    )
    outgoing = get_entity_neighbors(
        neo4j_settings,
        entity_id,
        direction="out",
        depth=1,
        limit=limit,
    )
    return {
        "entity": entity,
        "entity_id": entity_id,
        "limit": limit,
        "coverage": coverage_warnings_for_entity_source(settings, entity),
        "incoming": {
            "items": incoming,
            "groups": relationship_groups(incoming),
            "count": len(incoming),
        },
        "outgoing": {
            "items": outgoing,
            "groups": relationship_groups(outgoing),
            "count": len(outgoing),
        },
    }


def neighbors_response(
    settings: RuntimeSettings,
    entity_id: str,
    direction: str,
    edge_type: str | None,
    depth: int,
    limit: int,
) -> dict[str, Any]:
    items = get_entity_neighbors(
        settings.neo4j_settings(),
        entity_id,
        direction=direction,
        edge_type=edge_type,
        depth=depth,
        limit=limit,
    )
    return {
        "entity_id": entity_id,
        "direction": direction,
        "depth": depth,
        "items": items,
        "count": len(items),
    }


def impact_response(
    settings: RuntimeSettings,
    entity_id: str,
    direction: str,
    edge_type: str | None,
    depth: int,
    limit: int,
    profile: str = "impact",
) -> dict[str, Any]:
    normalized_profile = normalize_blast_radius_profile(profile)
    allowed_edge_types = blast_radius_profile_edge_types(normalized_profile, edge_type)
    entity = entity_response(settings, entity_id)
    items = get_entity_neighbors(
        settings.neo4j_settings(),
        entity_id,
        direction=direction,
        edge_type=edge_type,
        allowed_edge_types=allowed_edge_types,
        depth=depth,
        limit=limit,
    )
    report = blast_radius_report_from_items(
        entity,
        items,
        entity_id=entity_id,
        direction=direction,
        edge_type=edge_type,
        depth=depth,
        limit=limit,
        profile=normalized_profile,
        allowed_edge_types=allowed_edge_types,
    )
    report["coverage"] = coverage_warnings_for_entity_source(settings, entity)
    return report


def unresolved_edges_response(
    settings: RuntimeSettings,
    source_name: str | None,
    edge_type: str | None,
    limit: int,
) -> dict[str, Any]:
    items = list_unresolved_edges(settings.neo4j_settings(), source_name=source_name, edge_type=edge_type, limit=limit)
    return {"items": items, "count": len(items)}


__all__ = [
    "add_optional_filter",
    "entity_overview_response",
    "entity_response",
    "explore_response",
    "impact_response",
    "neighbors_response",
    "relationship_filters_payload",
    "relationship_search_response",
    "scope_response",
    "search_entities_response",
    "source_overview_response",
    "sources_response",
    "unresolved_edges_response",
]
