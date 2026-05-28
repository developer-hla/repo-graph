"""Neo4j graph scope, stats, and overview read operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_common import normalize_limit
from repo_graph.storage._neo4j_payloads import scope_payload, unloaded_scope_payload
from repo_graph.storage._neo4j_read_common import records_as_dicts
from repo_graph.storage._neo4j_scope_queries import (
    cross_source_edges_query,
    edge_type_counts_query,
    entity_type_counts_query,
    graph_scope_query,
    graph_stats_query,
    source_edge_counts_query,
    source_entity_counts_query,
    source_metadata_query,
)
from repo_graph.storage._neo4j_settings import Neo4jSettings


def read_graph_stats(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(graph_stats_query()).single()
    if record is None:
        return {}
    return dict(record)


def read_graph_scope(settings: Neo4jSettings) -> dict[str, Any]:
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            record = session.run(graph_scope_query()).single()
    if record is None or record["graph"] is None:
        return unloaded_scope_payload()
    return scope_payload(record["graph"], record["sources"])


def read_graph_overview(settings: Neo4jSettings, limit: int = 50) -> dict[str, Any]:
    normalized_limit = normalize_limit(limit, maximum=200)
    scope = read_graph_scope(settings)
    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            entity_type_records = records_as_dicts(session.run(entity_type_counts_query(), limit=normalized_limit))
            edge_type_records = records_as_dicts(session.run(edge_type_counts_query(), limit=normalized_limit))
            source_records = source_activity_records(session, normalized_limit)
            cross_source_records = records_as_dicts(session.run(cross_source_edges_query(), limit=normalized_limit))
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


def source_activity_records(session: Any, limit: int) -> list[dict[str, Any]]:
    sources = records_as_dicts(session.run(source_metadata_query()))
    entity_counts = records_as_dicts(session.run(source_entity_counts_query()))
    edge_counts = records_as_dicts(session.run(source_edge_counts_query()))
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
