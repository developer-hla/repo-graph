"""Neo4j relationship and traversal query text builders."""

from __future__ import annotations


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


def unresolved_edges_query() -> str:
    return """
        MATCH (source:RepoGraphEntity)-[edge]->(target:RepoGraphTarget)
        WHERE edge.edge_id IS NOT NULL
          AND ($source_name IS NULL OR edge.source_name = $source_name)
          AND ($edge_type IS NULL OR edge.edge_type = $edge_type)
        RETURN source, edge, target
        ORDER BY edge.source_name, edge.edge_type, edge.to_name
        LIMIT $limit
    """


__all__ = [
    "incoming_neighbors_query",
    "outgoing_neighbors_query",
    "relationship_search_by_edge_types_query",
    "relationship_search_query",
    "unresolved_edges_query",
]
