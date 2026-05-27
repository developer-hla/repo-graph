"""Blast-radius item, path, node, and edge payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import compact_dict, mapping_value, string_value


def blast_radius_next_node_id(edge: Mapping[str, Any], direction: str) -> str | None:
    if direction == "out":
        return string_value(edge.get("to_entity_id")) or blast_radius_target_id(edge)
    return string_value(edge.get("from_entity_id"))


def blast_radius_node_payload(
    edge: Mapping[str, Any],
    node_id: str,
    direction: str,
    entities_by_id: Mapping[str, Mapping[str, Any]],
    target_nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entity = entities_by_id.get(node_id)
    if entity is not None:
        return blast_radius_entity_payload(entity)
    if direction == "out":
        return target_nodes.setdefault(node_id, blast_radius_target_payload(edge, node_id))
    return {"entity_id": node_id}


def blast_radius_item(
    direction: str,
    edge: Mapping[str, Any],
    neighbor: Mapping[str, Any],
    path_node_ids: list[str],
    path_edges: list[Mapping[str, Any]],
    entities_by_id: Mapping[str, Mapping[str, Any]],
    target_nodes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "direction": direction,
        "depth": len(path_edges),
        "edge": blast_radius_edge_payload(edge),
        "neighbor": dict(neighbor),
        "path": blast_radius_path_payload(path_node_ids, path_edges, entities_by_id, target_nodes),
    }


def blast_radius_path_payload(
    node_ids: list[str],
    edges: list[Mapping[str, Any]],
    entities_by_id: Mapping[str, Mapping[str, Any]],
    target_nodes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    nodes = [blast_radius_path_node_payload(node_id, entities_by_id, target_nodes) for node_id in node_ids]
    edge_payloads = [blast_radius_edge_payload(edge) for edge in edges]
    return {
        "node_ids": node_ids,
        "edge_ids": [edge.get("edge_id") for edge in edge_payloads],
        "nodes": nodes,
        "edges": edge_payloads,
        "steps": [
            {
                "index": index + 1,
                "from": nodes[index],
                "edge": edge,
                "to": nodes[index + 1],
            }
            for index, edge in enumerate(edge_payloads)
        ],
    }


def blast_radius_path_node_payload(
    node_id: str,
    entities_by_id: Mapping[str, Mapping[str, Any]],
    target_nodes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    entity = entities_by_id.get(node_id)
    if entity is not None:
        return blast_radius_entity_payload(entity)
    target = target_nodes.get(node_id)
    if target is not None:
        return dict(target)
    return {"entity_id": node_id}


def blast_radius_entity_payload(entity: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "entity_id": string_value(entity.get("entity_id")),
            "entity_type": string_value(entity.get("entity_type")),
            "name": string_value(entity.get("name")),
            "source_name": string_value(entity.get("source_name")),
            "file_path": string_value(entity.get("file_path")),
            "line_number": entity.get("line_number"),
            "aliases": entity.get("aliases", []),
            "properties": mapping_value(entity.get("properties")),
        }
    )


def blast_radius_target_payload(edge: Mapping[str, Any], target_id: str) -> dict[str, Any]:
    return compact_dict(
        {
            "target_id": target_id,
            "name": string_value(edge.get("to_name")),
            "target_type": string_value(edge.get("to_type")),
            "source_name": string_value(edge.get("source_name")),
            "resolved": False,
        }
    )


def blast_radius_target_id(edge: Mapping[str, Any]) -> str | None:
    edge_id = string_value(edge.get("edge_id"))
    if edge_id:
        return f"unresolved:{edge_id}"
    source_name = string_value(edge.get("source_name"))
    to_type = string_value(edge.get("to_type"))
    to_name = string_value(edge.get("to_name"))
    if not (source_name and to_type and to_name):
        return None
    return f"unresolved:{source_name}:{to_type}:{to_name}"


def blast_radius_edge_payload(edge: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "edge_id": string_value(edge.get("edge_id")),
            "edge_type": string_value(edge.get("edge_type")),
            "from_entity_id": string_value(edge.get("from_entity_id")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "to_entity_id": string_value(edge.get("to_entity_id")),
            "to_name": string_value(edge.get("to_name")),
            "to_type": string_value(edge.get("to_type")),
            "resolved": edge.get("resolved"),
            "source_name": string_value(edge.get("source_name")),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "confidence": string_value(edge.get("confidence")),
            "parser": string_value(edge.get("parser")),
            "properties": mapping_value(edge.get("properties")),
        }
    )
