"""Compatibility facade for Neo4j read operations."""

from __future__ import annotations

from repo_graph.storage._neo4j_entity_reads import get_entity, list_entities_by_types, search_entities
from repo_graph.storage._neo4j_read_common import records_as_dicts
from repo_graph.storage._neo4j_relationship_reads import (
    get_entity_neighbors,
    list_unresolved_edges,
    search_relationships,
    search_relationships_by_edge_types,
)
from repo_graph.storage._neo4j_scope_reads import (
    merge_source_activity,
    read_graph_overview,
    read_graph_scope,
    read_graph_stats,
    source_activity_records,
)
from repo_graph.storage._neo4j_source_reads import read_source_overview

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
