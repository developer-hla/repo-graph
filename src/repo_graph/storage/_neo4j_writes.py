"""Neo4j write transactions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def initialize_schema(session: Any) -> None:
    for query in (
        "CREATE CONSTRAINT repo_graph_entity_id IF NOT EXISTS "
        "FOR (entity:RepoGraphEntity) REQUIRE entity.entity_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_target_id IF NOT EXISTS "
        "FOR (target:RepoGraphTarget) REQUIRE target.target_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_source_id IF NOT EXISTS "
        "FOR (source:RepoGraphSource) REQUIRE source.source_id IS UNIQUE",
        "CREATE CONSTRAINT repo_graph_graph_id IF NOT EXISTS "
        "FOR (graph:RepoGraphGraph) REQUIRE graph.graph_id IS UNIQUE",
    ):
        session.run(query).consume()


def clear_graph_tx(tx: Any) -> None:
    tx.run(
        """
        MATCH (node)
        WHERE
          node:RepoGraphEntity
          OR node:RepoGraphTarget
          OR node:RepoGraphSource
          OR node:RepoGraphGraph
        DETACH DELETE node
        """
    ).consume()


def delete_current_edges_tx(tx: Any, edges: list[dict[str, Any]]) -> None:
    edge_ids = [edge["edge_id"] for edge in edges]
    if not edge_ids:
        return
    tx.run(
        """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IN $edge_ids
        DELETE edge
        """,
        edge_ids=edge_ids,
    ).consume()


def delete_source_data_tx(tx: Any, source_names: Iterable[str]) -> None:
    names = list(source_names)
    if not names:
        return
    tx.run(
        """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IS NOT NULL
          AND edge.source_name IN $source_names
        DELETE edge
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (entity:RepoGraphEntity)
        WHERE entity.source_name IN $source_names
        DETACH DELETE entity
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (target:RepoGraphTarget)
        WHERE target.source_name IN $source_names
        DETACH DELETE target
        """,
        source_names=names,
    ).consume()
    tx.run(
        """
        MATCH (source:RepoGraphSource)
        WHERE source.name IN $source_names
        DETACH DELETE source
        """,
        source_names=names,
    ).consume()


def write_graph_tx(tx: Any, graph: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (graph:RepoGraphGraph {graph_id: $graph_id})
        SET graph += $properties
        """,
        graph_id=graph["graph_id"],
        properties=graph,
    ).consume()


def write_sources_tx(tx: Any, sources: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $sources AS source
        MERGE (node:RepoGraphSource {source_id: source.source_id})
        SET node += source.properties
        WITH node, source
        MATCH (graph:RepoGraphGraph {graph_id: "current"})
        MERGE (graph)-[relationship:INCLUDES_SOURCE {source_id: source.source_id}]->(node)
        SET relationship.source_id = source.source_id
        """,
        sources=sources,
    ).consume()


def write_entities_tx(tx: Any, entities: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $entities AS entity
        MERGE (node:RepoGraphEntity {entity_id: entity.entity_id})
        SET node += entity.properties
        """,
        entities=entities,
    ).consume()


def write_targets_tx(tx: Any, targets: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $targets AS target
        MERGE (node:RepoGraphTarget {target_id: target.target_id})
        SET node += target.properties
        """,
        targets=targets,
    ).consume()


def write_resolved_edges_tx(tx: Any, relationship_type: str, edges: list[dict[str, Any]]) -> None:
    if not edges:
        return
    tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (source:RepoGraphEntity {{entity_id: edge.from_entity_id}})
        MATCH (target:RepoGraphEntity {{entity_id: edge.to_entity_id}})
        MERGE (source)-[relationship:{relationship_type} {{edge_id: edge.edge_id}}]->(target)
        SET relationship += edge.properties
        """,
        edges=edges,
    ).consume()


def write_unresolved_edges_tx(tx: Any, relationship_type: str, edges: list[dict[str, Any]]) -> None:
    if not edges:
        return
    tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (source:RepoGraphEntity {{entity_id: edge.from_entity_id}})
        MATCH (target:RepoGraphTarget {{target_id: edge.target_id}})
        MERGE (source)-[relationship:{relationship_type} {{edge_id: edge.edge_id}}]->(target)
        SET relationship += edge.properties
        """,
        edges=edges,
    ).consume()


def delete_orphan_targets_tx(tx: Any) -> None:
    tx.run(
        """
        MATCH (target:RepoGraphTarget)
        WHERE NOT (target)<-[]-()
        DELETE target
        """
    ).consume()


def delete_orphan_external_resources_tx(tx: Any) -> None:
    tx.run(
        """
        MATCH (entity:RepoGraphEntity)
        WHERE coalesce(entity.property_canonical_external_resource, false) = true
          AND NOT (entity)--()
        DETACH DELETE entity
        """
    ).consume()


__all__ = [
    "clear_graph_tx",
    "delete_current_edges_tx",
    "delete_orphan_external_resources_tx",
    "delete_orphan_targets_tx",
    "delete_source_data_tx",
    "initialize_schema",
    "write_entities_tx",
    "write_graph_tx",
    "write_resolved_edges_tx",
    "write_sources_tx",
    "write_targets_tx",
    "write_unresolved_edges_tx",
]
