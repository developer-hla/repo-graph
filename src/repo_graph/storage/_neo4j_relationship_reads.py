"""Neo4j relationship, neighbor, and unresolved-edge read operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_common import (
    normalize_depth,
    normalize_direction,
    normalize_edge_types,
    normalize_limit,
    optional_filter,
)
from repo_graph.storage._neo4j_payloads import neighbor_payload, relationship_evidence_payload, unresolved_edge_payload
from repo_graph.storage._neo4j_queries import (
    incoming_neighbors_query,
    outgoing_neighbors_query,
    relationship_search_by_edge_types_query,
    relationship_search_query,
)
from repo_graph.storage._neo4j_settings import Neo4jSettings


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
