"""Neo4j source overview query text builders."""

from __future__ import annotations


def source_detail_query() -> str:
    return """
        MATCH (source:RepoGraphSource {name: $source_name})
        RETURN source
        LIMIT 1
    """


def source_summary_query() -> str:
    return """
        CALL {
          MATCH (entity:RepoGraphEntity)
          WHERE entity.source_name = $source_name
          RETURN count(entity) AS entity_count
        }
        CALL {
          MATCH ()-[edge]->()
          WHERE edge.edge_id IS NOT NULL
            AND edge.source_name = $source_name
          RETURN
            count(edge) AS edge_count,
            sum(CASE WHEN coalesce(edge.resolved, false) THEN 1 ELSE 0 END) AS resolved_edge_count,
            sum(CASE WHEN coalesce(edge.resolved, false) THEN 0 ELSE 1 END) AS unresolved_edge_count
        }
        RETURN
          entity_count,
          edge_count,
          resolved_edge_count,
          unresolved_edge_count
    """


def source_entity_type_counts_query() -> str:
    return """
        MATCH (entity:RepoGraphEntity)
        WHERE entity.source_name = $source_name
        RETURN
          coalesce(entity.entity_type, "unknown") AS entity_type,
          count(entity) AS entity_count
        ORDER BY entity_count DESC, entity_type
        LIMIT $limit
    """


def source_edge_type_counts_query() -> str:
    return """
        MATCH ()-[edge]->()
        WHERE edge.edge_id IS NOT NULL
          AND edge.source_name = $source_name
        RETURN
          coalesce(edge.edge_type, "unknown") AS edge_type,
          count(edge) AS edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 1 ELSE 0 END) AS resolved_edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 0 ELSE 1 END) AS unresolved_edge_count
        ORDER BY edge_count DESC, edge_type
        LIMIT $limit
    """


def source_owned_surface_query() -> str:
    return """
        MATCH (entity:RepoGraphEntity)
        WHERE entity.source_name = $source_name
          AND entity.entity_type IN $surface_entity_types
        RETURN entity
        ORDER BY entity.entity_type, entity.name
        LIMIT $limit
    """


def source_uses_query() -> str:
    return """
        MATCH ()-[edge]->(target)
        WHERE edge.edge_id IS NOT NULL
          AND edge.source_name = $source_name
          AND ($use_edge_types IS NULL OR edge.edge_type IN $use_edge_types)
        RETURN
          coalesce(edge.edge_type, "unknown") AS edge_type,
          coalesce(edge.to_type, target.entity_type, target.target_type, "unknown") AS target_type,
          coalesce(edge.to_name, target.name, "unknown") AS target_name,
          coalesce(target.source_name, "") AS target_source,
          count(edge) AS edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 1 ELSE 0 END) AS resolved_edge_count,
          sum(CASE WHEN coalesce(edge.resolved, false) THEN 0 ELSE 1 END) AS unresolved_edge_count,
          head(collect(edge.file_path)) AS file_path,
          head(collect(edge.line_number)) AS line_number
        ORDER BY edge_count DESC, edge_type, target_name
        LIMIT $limit
    """


def source_outgoing_cross_source_query() -> str:
    return """
        MATCH ()-[edge]->(target:RepoGraphEntity)
        WHERE edge.edge_id IS NOT NULL
          AND edge.source_name = $source_name
          AND coalesce(edge.resolved, false) = true
          AND coalesce(target.source_name, "") <> ""
          AND target.source_name <> $source_name
        RETURN
          target.source_name AS target_source,
          coalesce(edge.edge_type, "unknown") AS edge_type,
          coalesce(target.entity_type, edge.to_type, "unknown") AS target_type,
          count(edge) AS edge_count
        ORDER BY edge_count DESC, target_source, edge_type, target_type
        LIMIT $limit
    """


def source_incoming_cross_source_query() -> str:
    return """
        MATCH ()-[edge]->(target:RepoGraphEntity)
        WHERE edge.edge_id IS NOT NULL
          AND coalesce(edge.resolved, false) = true
          AND target.source_name = $source_name
          AND coalesce(edge.source_name, "") <> ""
          AND edge.source_name <> $source_name
        RETURN
          edge.source_name AS source_name,
          coalesce(edge.edge_type, "unknown") AS edge_type,
          coalesce(edge.from_type, "unknown") AS source_type,
          count(edge) AS edge_count
        ORDER BY edge_count DESC, source_name, edge_type, source_type
        LIMIT $limit
    """


__all__ = [
    "source_detail_query",
    "source_edge_type_counts_query",
    "source_entity_type_counts_query",
    "source_incoming_cross_source_query",
    "source_outgoing_cross_source_query",
    "source_owned_surface_query",
    "source_summary_query",
    "source_uses_query",
]
