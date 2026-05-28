"""Neo4j graph scope and overview query text builders."""

from __future__ import annotations


def graph_stats_query() -> str:
    return """
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


def graph_scope_query() -> str:
    return """
        OPTIONAL MATCH (graph:RepoGraphGraph {graph_id: "current"})
        OPTIONAL MATCH (graph)-[:INCLUDES_SOURCE]->(source:RepoGraphSource)
        WITH graph, source
        ORDER BY source.index, source.name
        RETURN graph, [item IN collect(source) WHERE item IS NOT NULL] AS sources
    """


def entity_type_counts_query() -> str:
    return """
        MATCH (entity:RepoGraphEntity)
        RETURN
          coalesce(entity.entity_type, "unknown") AS entity_type,
          count(entity) AS entity_count
        ORDER BY entity_count DESC, entity_type
        LIMIT $limit
    """


def edge_type_counts_query() -> str:
    return """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IS NOT NULL
        RETURN
          coalesce(edge.edge_type, "unknown") AS edge_type,
          count(edge) AS edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 1 ELSE 0 END) AS resolved_edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 0 ELSE 1 END) AS unresolved_edge_count
        ORDER BY edge_count DESC, edge_type
        LIMIT $limit
    """


def source_metadata_query() -> str:
    return """
        MATCH (source:RepoGraphSource)
        RETURN
          source.name AS source_name,
          coalesce(source.type, "") AS source_type,
          coalesce(source.ref, "") AS ref,
          coalesce(source.commit, "") AS commit
        ORDER BY source.index, source.name
    """


def source_entity_counts_query() -> str:
    return """
        MATCH (entity:RepoGraphEntity)
        WHERE coalesce(entity.source_name, "") <> ""
        RETURN
          entity.source_name AS source_name,
          count(entity) AS entity_count
    """


def source_edge_counts_query() -> str:
    return """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IS NOT NULL
          AND coalesce(edge.source_name, "") <> ""
        RETURN
          edge.source_name AS source_name,
          count(edge) AS edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 0 ELSE 1 END) AS unresolved_edge_count
    """


def cross_source_edges_query() -> str:
    return """
        MATCH ()-[edge]->(to:RepoGraphEntity)
        WHERE edge.edge_id IS NOT NULL
          AND coalesce(edge.resolved, false) = true
          AND coalesce(edge.source_name, "") <> ""
          AND coalesce(to.source_name, "") <> ""
          AND edge.source_name <> to.source_name
        RETURN
          edge.source_name AS from_source,
          to.source_name AS to_source,
          coalesce(edge.edge_type, "unknown") AS edge_type,
          count(edge) AS edge_count
        ORDER BY edge_count DESC, from_source, to_source, edge_type
        LIMIT $limit
    """


__all__ = [
    "cross_source_edges_query",
    "edge_type_counts_query",
    "entity_type_counts_query",
    "graph_scope_query",
    "graph_stats_query",
    "source_edge_counts_query",
    "source_entity_counts_query",
    "source_metadata_query",
]
