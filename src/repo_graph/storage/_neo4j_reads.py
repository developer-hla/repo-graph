"""Neo4j read operations and query result shaping."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_common import (
    SOURCE_SURFACE_ENTITY_TYPES,
    lower_filter,
    normalize_depth,
    normalize_direction,
    normalize_edge_types,
    normalize_limit,
    optional_filter,
)
from repo_graph.storage._neo4j_payloads import (
    entity_payload,
    neighbor_payload,
    relationship_evidence_payload,
    scope_payload,
    source_payload,
    unloaded_scope_payload,
    unresolved_edge_payload,
)
from repo_graph.storage._neo4j_queries import (
    cross_source_edges_query,
    edge_type_counts_query,
    entity_type_counts_query,
    incoming_neighbors_query,
    outgoing_neighbors_query,
    relationship_search_by_edge_types_query,
    relationship_search_query,
    source_detail_query,
    source_edge_counts_query,
    source_edge_type_counts_query,
    source_entity_counts_query,
    source_entity_type_counts_query,
    source_incoming_cross_source_query,
    source_metadata_query,
    source_outgoing_cross_source_query,
    source_owned_surface_query,
    source_summary_query,
    source_uses_query,
)
from repo_graph.storage._neo4j_settings import Neo4jSettings


def read_graph_stats(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                CALL () {
                  MATCH (entity:RepoGraphEntity)
                  RETURN count(entity) AS entity_count
                }
                CALL () {
                  MATCH (target:RepoGraphTarget)
                  RETURN count(target) AS unresolved_target_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL
                  RETURN count(edge) AS edge_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL AND coalesce(edge.resolved, false) = true
                  RETURN count(edge) AS resolved_edge_count
                }
                CALL () {
                  MATCH ()-[edge]->()
                  WHERE edge.edge_id IS NOT NULL AND coalesce(edge.resolved, false) = false
                  RETURN count(edge) AS unresolved_edge_count
                }
                OPTIONAL MATCH (graph:RepoGraphGraph {graph_id: "current"})
                RETURN
                  graph.scope_name AS scope_name,
                  graph.schema_version AS schema_version,
                  graph.generated_at AS generated_at,
                  entity_count,
                  edge_count,
                  resolved_edge_count,
                  unresolved_edge_count,
                  unresolved_target_count
                """
            ).single()
    if record is None:
        return {}
    return dict(record)


def read_graph_overview(settings: Neo4jSettings, limit: int = 50) -> dict[str, Any]:
    normalized_limit = normalize_limit(limit, maximum=200)
    scope = read_graph_scope(settings)
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            entity_type_records = [
                dict(record) for record in session.run(entity_type_counts_query(), limit=normalized_limit)
            ]
            edge_type_records = [
                dict(record) for record in session.run(edge_type_counts_query(), limit=normalized_limit)
            ]
            source_records = source_activity_records(session, normalized_limit)
            cross_source_records = [
                dict(record) for record in session.run(cross_source_edges_query(), limit=normalized_limit)
            ]
    return {
        "loaded": bool(scope.get("loaded")),
        "scope_name": scope.get("scope_name"),
        "generated_at": scope.get("generated_at"),
        "summary": scope.get("summary", {}),
        "source_count": scope.get("source_count", 0),
        "entity_types": entity_type_records,
        "edge_types": edge_type_records,
        "sources": source_records,
        "cross_source_edges": cross_source_records,
    }


def read_source_overview(
    settings: Neo4jSettings,
    source_name: str,
    limit: int = 50,
    use_edge_types: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    normalized_source_name = optional_filter(source_name)
    if normalized_source_name is None:
        raise ValueError("Source name is required.")
    normalized_limit = normalize_limit(limit, maximum=200)
    normalized_use_edge_types = normalize_edge_types(use_edge_types)
    params = {
        "source_name": normalized_source_name,
        "limit": normalized_limit,
        "surface_entity_types": list(SOURCE_SURFACE_ENTITY_TYPES),
        "use_edge_types": normalized_use_edge_types,
    }

    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            source_record = session.run(source_detail_query(), source_name=normalized_source_name).single()
            if source_record is None:
                return None
            summary = dict(session.run(source_summary_query(), source_name=normalized_source_name).single() or {})
            entity_types = records_as_dicts(session.run(source_entity_type_counts_query(), **params))
            edge_types = records_as_dicts(session.run(source_edge_type_counts_query(), **params))
            owned_surface = [
                entity_payload(record["entity"]) for record in session.run(source_owned_surface_query(), **params)
            ]
            uses = records_as_dicts(session.run(source_uses_query(), **params))
            outgoing = records_as_dicts(session.run(source_outgoing_cross_source_query(), **params))
            incoming = records_as_dicts(session.run(source_incoming_cross_source_query(), **params))

    return {
        "source": source_payload(source_record["source"]),
        "summary": summary,
        "entity_types": entity_types,
        "edge_types": edge_types,
        "owned_surface": owned_surface,
        "uses": uses,
        "outgoing_cross_source_edges": outgoing,
        "incoming_cross_source_edges": incoming,
    }


def source_activity_records(session: Any, limit: int) -> list[dict[str, Any]]:
    sources = [dict(record) for record in session.run(source_metadata_query())]
    entity_counts = [dict(record) for record in session.run(source_entity_counts_query())]
    edge_counts = [dict(record) for record in session.run(source_edge_counts_query())]
    return merge_source_activity(sources, entity_counts, edge_counts, limit)


def merge_source_activity(
    sources: Iterable[Mapping[str, Any]],
    entity_counts: Iterable[Mapping[str, Any]],
    edge_counts: Iterable[Mapping[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    items = {
        str(source.get("source_name")): {
            "source_name": source.get("source_name"),
            "source_type": source.get("source_type"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
            "entity_count": 0,
            "edge_count": 0,
            "unresolved_edge_count": 0,
        }
        for source in sources
        if source.get("source_name")
    }
    for item in entity_counts:
        source_name = item.get("source_name")
        if source_name in items:
            items[source_name]["entity_count"] = item.get("entity_count", 0)
    for item in edge_counts:
        source_name = item.get("source_name")
        if source_name in items:
            items[source_name]["edge_count"] = item.get("edge_count", 0)
            items[source_name]["unresolved_edge_count"] = item.get("unresolved_edge_count", 0)
    return sorted(
        items.values(),
        key=lambda item: (-int(item["edge_count"]), -int(item["entity_count"]), str(item["source_name"])),
    )[:limit]


def records_as_dicts(records: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]


def read_graph_scope(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                OPTIONAL MATCH (graph:RepoGraphGraph {graph_id: "current"})
                OPTIONAL MATCH (graph)-[:INCLUDES_SOURCE]->(source:RepoGraphSource)
                WITH graph, source
                ORDER BY source.index, source.name
                RETURN graph, [item IN collect(source) WHERE item IS NOT NULL] AS sources
                """
            ).single()
    if record is None or record["graph"] is None:
        return unloaded_scope_payload()
    return scope_payload(record["graph"], record["sources"])


def search_entities(
    settings: Neo4jSettings,
    query: str | None = None,
    entity_type: str | None = None,
    source_name: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    params = {
        "search_text": lower_filter(query),
        "entity_type": optional_filter(entity_type),
        "source_name": optional_filter(source_name),
        "limit": normalize_limit(limit, maximum=100),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (entity:RepoGraphEntity)
                WHERE
                  ($search_text IS NULL
                    OR toLower(coalesce(entity.name, "")) CONTAINS $search_text
                    OR toLower(coalesce(entity.entity_id, "")) = $search_text
                    OR toLower(coalesce(entity.file_path, "")) CONTAINS $search_text
                    OR toLower(coalesce(entity.property_full_name, "")) CONTAINS $search_text
                    OR any(alias IN coalesce(entity.aliases, [])
                      WHERE toLower(toString(alias)) CONTAINS $search_text))
                  AND ($entity_type IS NULL OR entity.entity_type = $entity_type)
                  AND ($source_name IS NULL OR entity.source_name = $source_name)
                RETURN entity
                ORDER BY entity.entity_type, entity.source_name, entity.name
                LIMIT $limit
                """,
                **params,
            )
            return [entity_payload(record["entity"]) for record in records]


def list_entities_by_types(
    settings: Neo4jSettings,
    entity_types: Iterable[str],
    source_name: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    normalized_types = sorted({entity_type for entity_type in entity_types if entity_type})
    if not normalized_types:
        return []
    params = {
        "entity_types": normalized_types,
        "source_name": optional_filter(source_name),
        "limit": normalize_limit(limit, maximum=1000),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (entity:RepoGraphEntity)
                WHERE entity.entity_type IN $entity_types
                  AND ($source_name IS NULL OR entity.source_name = $source_name)
                RETURN entity
                ORDER BY entity.entity_type, entity.source_name, entity.name
                LIMIT $limit
                """,
                **params,
            )
            return [entity_payload(record["entity"]) for record in records]


def search_relationships(
    settings: Neo4jSettings,
    from_source: str | None = None,
    to_source: str | None = None,
    edge_type: str | None = None,
    from_type: str | None = None,
    to_type: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    params = {
        "from_source": optional_filter(from_source),
        "to_source": optional_filter(to_source),
        "edge_type": optional_filter(edge_type),
        "from_type": optional_filter(from_type),
        "to_type": optional_filter(to_type),
        "resolved": resolved,
        "limit": normalize_limit(limit, maximum=200),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(relationship_search_query(), **params)
            return [relationship_evidence_payload(record) for record in records]


def search_relationships_by_edge_types(
    settings: Neo4jSettings,
    edge_types: Iterable[str],
    from_source: str | None = None,
    to_source: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    params = {
        "edge_types": sorted({edge_type for edge_type in edge_types if edge_type}),
        "from_source": optional_filter(from_source),
        "to_source": optional_filter(to_source),
        "limit": normalize_limit(limit, maximum=1000),
    }
    if not params["edge_types"]:
        return []
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(relationship_search_by_edge_types_query(), **params)
            return [relationship_evidence_payload(record) for record in records]


def get_entity(settings: Neo4jSettings, entity_id: str) -> dict[str, Any] | None:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(
                """
                MATCH (entity:RepoGraphEntity {entity_id: $entity_id})
                RETURN entity
                LIMIT 1
                """,
                entity_id=entity_id,
            ).single()
    if record is None:
        return None
    return entity_payload(record["entity"])


def get_entity_neighbors(
    settings: Neo4jSettings,
    entity_id: str,
    direction: str = "both",
    edge_type: str | None = None,
    allowed_edge_types: Iterable[str] | None = None,
    depth: int = 1,
    limit: int = 50,
) -> list[dict[str, Any]]:
    normalized_direction = normalize_direction(direction)
    normalized_depth = normalize_depth(depth)
    normalized_limit = normalize_limit(limit, maximum=200)
    params = {
        "entity_id": entity_id,
        "edge_type": optional_filter(edge_type),
        "edge_types": normalize_edge_types(allowed_edge_types),
        "limit": normalized_limit,
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records: list[Any] = []
            if normalized_direction in {"out", "both"}:
                records.extend(session.run(outgoing_neighbors_query(normalized_depth), **params))
            if normalized_direction in {"in", "both"}:
                records.extend(session.run(incoming_neighbors_query(normalized_depth), **params))

    return [neighbor_payload(record) for record in records[:normalized_limit]]


def list_unresolved_edges(
    settings: Neo4jSettings,
    source_name: str | None = None,
    edge_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params = {
        "source_name": optional_filter(source_name),
        "edge_type": optional_filter(edge_type),
        "limit": normalize_limit(limit, maximum=1000),
    }
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            records = session.run(
                """
                MATCH (source:RepoGraphEntity)-[edge]->(target:RepoGraphTarget)
                WHERE edge.edge_id IS NOT NULL
                  AND ($source_name IS NULL OR edge.source_name = $source_name)
                  AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
                RETURN source, edge, target
                ORDER BY edge.source_name, edge.edge_type, edge.to_name
                LIMIT $limit
                """,
                **params,
            )
            return [unresolved_edge_payload(record) for record in records]


__all__ = [
    "get_entity",
    "get_entity_neighbors",
    "list_entities_by_types",
    "list_unresolved_edges",
    "merge_source_activity",
    "read_graph_overview",
    "read_graph_scope",
    "read_graph_stats",
    "read_source_overview",
    "records_as_dicts",
    "search_entities",
    "search_relationships",
    "search_relationships_by_edge_types",
    "source_activity_records",
]
