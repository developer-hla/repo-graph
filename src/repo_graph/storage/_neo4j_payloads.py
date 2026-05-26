"""Neo4j record to API payload mapping."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.storage._neo4j_common import compact_dict, json_object


def entity_payload(entity: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "entity_id": entity.get("entity_id"),
            "entity_type": entity.get("entity_type"),
            "name": entity.get("name"),
            "source_name": entity.get("source_name"),
            "file_path": entity.get("file_path"),
            "line_number": entity.get("line_number"),
            "aliases": entity.get("aliases", []),
            "properties": json_object(entity.get("properties_json")),
        }
    )


def target_payload(target: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "target_id": target.get("target_id"),
            "name": target.get("name"),
            "target_type": target.get("target_type"),
            "source_name": target.get("source_name"),
            "resolved": target.get("resolved", False),
        }
    )


def edge_payload(edge: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "edge_id": edge.get("edge_id"),
            "edge_type": edge.get("edge_type"),
            "from_entity_id": edge.get("from_entity_id"),
            "from_name": edge.get("from_name"),
            "from_type": edge.get("from_type"),
            "to_entity_id": edge.get("to_entity_id"),
            "to_name": edge.get("to_name"),
            "to_type": edge.get("to_type"),
            "resolved": edge.get("resolved", False),
            "source_name": edge.get("source_name"),
            "file_path": edge.get("file_path"),
            "line_number": edge.get("line_number"),
            "confidence": edge.get("confidence"),
            "parser": edge.get("parser"),
            "properties": json_object(edge.get("properties_json")),
        }
    )


def neighbor_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "direction": record["direction"],
        "edge": edge_payload(record["edge"]),
        "neighbor": graph_node_payload(record["neighbor"], record.get("labels", [])),
    }
    depth = record.get("depth")
    if isinstance(depth, int):
        payload["depth"] = depth
    path = path_payload(record)
    if path:
        payload["path"] = path
    return payload


def path_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    node_ids = record.get("node_ids")
    edge_ids = record.get("edge_ids")
    payload = compact_dict(
        {
            "node_ids": node_ids if isinstance(node_ids, list) else None,
            "edge_ids": edge_ids if isinstance(edge_ids, list) else None,
        }
    )
    path_nodes = record.get("path_nodes")
    path_node_labels = record.get("path_node_labels")
    path_edges = record.get("path_edges")
    if not (
        isinstance(path_nodes, list)
        and isinstance(path_node_labels, list)
        and isinstance(path_edges, list)
        and len(path_nodes) == len(path_node_labels)
        and len(path_nodes) == len(path_edges) + 1
    ):
        return payload
    nodes = [
        graph_node_payload(node, labels if isinstance(labels, list) else [])
        for node, labels in zip(path_nodes, path_node_labels, strict=True)
    ]
    edges = [edge_payload(edge) for edge in path_edges]
    payload["nodes"] = nodes
    payload["edges"] = edges
    payload["steps"] = [
        {
            "index": index + 1,
            "from": nodes[index],
            "edge": edge,
            "to": nodes[index + 1],
        }
        for index, edge in enumerate(edges)
    ]
    return payload


def unresolved_edge_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": entity_payload(record["source"]),
        "edge": edge_payload(record["edge"]),
        "target": target_payload(record["target"]),
    }


def relationship_evidence_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    source = entity_payload(record["source"])
    edge = edge_payload(record["edge"])
    target = graph_node_payload(record["target"], record.get("target_labels", []))
    return {
        "from_entity": source,
        "edge": edge,
        "target": target,
        "from_source": edge.get("source_name") or source.get("source_name"),
        "to_source": target.get("source_name"),
        "from_type": edge.get("from_type") or source.get("entity_type"),
        "to_type": edge.get("to_type") or target.get("entity_type") or target.get("target_type"),
    }


def graph_node_payload(node: Mapping[str, Any], labels: Iterable[str]) -> dict[str, Any]:
    if "RepoGraphTarget" in labels:
        return target_payload(node)
    return entity_payload(node)


def source_payload(source: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "source_id": source.get("source_id"),
            "index": source.get("index"),
            "name": source.get("name"),
            "type": source.get("type"),
            "path": source.get("path"),
            "url": source.get("url"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
        }
    )


def scope_payload(graph: Mapping[str, Any], sources: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    source_items = [source_payload(source) for source in sources]
    return {
        "loaded": True,
        "scope_name": graph.get("scope_name"),
        "schema_version": graph.get("schema_version"),
        "generated_at": graph.get("generated_at"),
        "tool": graph.get("tool"),
        "summary": json_object(graph.get("summary_json")),
        "source_count": len(source_items),
        "sources": source_items,
    }


def unloaded_scope_payload() -> dict[str, Any]:
    return {
        "loaded": False,
        "source_count": 0,
        "sources": [],
    }


__all__ = [
    "edge_payload",
    "entity_payload",
    "graph_node_payload",
    "neighbor_payload",
    "path_payload",
    "relationship_evidence_payload",
    "scope_payload",
    "source_payload",
    "target_payload",
    "unloaded_scope_payload",
    "unresolved_edge_payload",
]
