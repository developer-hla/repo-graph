"""Cypher queries used by Neo4j storage."""

from __future__ import annotations


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


def relationship_search_query() -> str:
    return """
        MATCH (source:RepoGraphEntity)-[edge]->(target)
        WHERE edge.edge_id IS NOT NULL
          AND ($from_source IS NULL OR coalesce(edge.source_name, source.source_name, "") = $from_source)
          AND ($to_source IS NULL OR coalesce(target.source_name, "") = $to_source)
          AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
          AND ($from_type IS NULL OR coalesce(edge.from_type, source.entity_type, "") = $from_type)
          AND ($to_type IS NULL OR coalesce(edge.to_type, target.entity_type, target.target_type, "") = $to_type)
          AND ($resolved IS NULL OR coalesce(edge.resolved, false) = $resolved)
        WITH source, edge, target
        LIMIT $limit
        RETURN
          source,
          edge,
          target,
          labels(target) AS target_labels
        ORDER BY
          coalesce(edge.source_name, source.source_name, ""),
          coalesce(target.source_name, ""),
          edge.edge_type,
          edge.file_path,
          edge.line_number,
          edge.to_name
    """


def relationship_search_by_edge_types_query() -> str:
    return """
        MATCH (source:RepoGraphEntity)-[edge]->(target)
        WHERE edge.edge_id IS NOT NULL
          AND edge.edge_type IN $edge_types
          AND ($from_source IS NULL OR coalesce(edge.source_name, source.source_name, "") = $from_source)
          AND ($to_source IS NULL OR coalesce(target.source_name, "") = $to_source)
        WITH source, edge, target
        LIMIT $limit
        RETURN
          source,
          edge,
          target,
          labels(target) AS target_labels
        ORDER BY
          coalesce(edge.source_name, source.source_name, ""),
          coalesce(target.source_name, ""),
          edge.edge_type,
          edge.file_path,
          edge.line_number,
          edge.to_name
    """


def outgoing_neighbors_query(depth: int) -> str:
    return f"""
        MATCH path = (:RepoGraphEntity {{entity_id: $entity_id}})-[*1..{depth}]->(neighbor)
        WHERE all(edge IN relationships(path)
          WHERE edge.edge_id IS NOT NULL
            AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
            AND ($edge_types IS NULL OR edge.edge_type IN $edge_types))
        WITH path, last(relationships(path)) AS edge, neighbor
        RETURN
          edge,
          neighbor,
          labels(neighbor) AS labels,
          "out" AS direction,
          length(path) AS depth,
          nodes(path) AS path_nodes,
          [node IN nodes(path) | labels(node)] AS path_node_labels,
          relationships(path) AS path_edges,
          [node IN nodes(path) | coalesce(node.entity_id, node.target_id)] AS node_ids,
          [rel IN relationships(path) | rel.edge_id] AS edge_ids
        ORDER BY depth, edge.edge_type, edge.to_name
        LIMIT $limit
    """


def incoming_neighbors_query(depth: int) -> str:
    return f"""
        MATCH path = (neighbor)-[*1..{depth}]->(:RepoGraphEntity {{entity_id: $entity_id}})
        WHERE all(edge IN relationships(path)
          WHERE edge.edge_id IS NOT NULL
            AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
            AND ($edge_types IS NULL OR edge.edge_type IN $edge_types))
        WITH path, head(relationships(path)) AS edge, neighbor
        RETURN
          edge,
          neighbor,
          labels(neighbor) AS labels,
          "in" AS direction,
          length(path) AS depth,
          nodes(path) AS path_nodes,
          [node IN nodes(path) | labels(node)] AS path_node_labels,
          relationships(path) AS path_edges,
          [node IN nodes(path) | coalesce(node.entity_id, node.target_id)] AS node_ids,
          [rel IN relationships(path) | rel.edge_id] AS edge_ids
        ORDER BY depth, edge.edge_type, edge.from_name
        LIMIT $limit
    """


__all__ = [
    "cross_source_edges_query",
    "edge_type_counts_query",
    "entity_type_counts_query",
    "incoming_neighbors_query",
    "outgoing_neighbors_query",
    "relationship_search_by_edge_types_query",
    "relationship_search_query",
    "source_detail_query",
    "source_edge_counts_query",
    "source_edge_type_counts_query",
    "source_entity_counts_query",
    "source_entity_type_counts_query",
    "source_incoming_cross_source_query",
    "source_metadata_query",
    "source_outgoing_cross_source_query",
    "source_owned_surface_query",
    "source_summary_query",
    "source_uses_query",
]
