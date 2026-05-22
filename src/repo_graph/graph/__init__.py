"""Graph model public API."""

from __future__ import annotations

from repo_graph.graph.builder import add_facts_to_graph, edge_from_fact, entity_from_fact
from repo_graph.graph.model import Edge, Entity, Graph, stable_id
from repo_graph.graph.resolution import normalize_key, resolution_entity_types

__all__ = [
    "Edge",
    "Entity",
    "Graph",
    "add_facts_to_graph",
    "edge_from_fact",
    "entity_from_fact",
    "normalize_key",
    "resolution_entity_types",
    "stable_id",
]
