"""Neo4j source overview read operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_common import (
    SOURCE_SURFACE_ENTITY_TYPES,
    normalize_edge_types,
    normalize_limit,
    optional_filter,
)
from repo_graph.storage._neo4j_payloads import entity_payload, source_payload
from repo_graph.storage._neo4j_queries import (
    source_detail_query,
    source_edge_type_counts_query,
    source_entity_type_counts_query,
    source_incoming_cross_source_query,
    source_outgoing_cross_source_query,
    source_owned_surface_query,
    source_summary_query,
    source_uses_query,
)
from repo_graph.storage._neo4j_read_common import records_as_dicts
from repo_graph.storage._neo4j_settings import Neo4jSettings


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
