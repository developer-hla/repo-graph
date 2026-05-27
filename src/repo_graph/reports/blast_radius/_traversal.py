"""Blast-radius graph traversal."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import mapping_value, string_value, validate_positive_int
from repo_graph.reports.blast_radius._payloads import (
    blast_radius_item,
    blast_radius_next_node_id,
    blast_radius_node_payload,
)
from repo_graph.reports.blast_radius._profiles import (
    normalize_blast_radius_direction,
    validate_blast_radius_depth,
)


def blast_radius_items_from_graph(
    entities_by_id: Mapping[str, Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    entity_id: str,
    direction: str,
    edge_type: str | None,
    allowed_edge_types: Iterable[str] | None,
    depth: int,
    limit: int,
) -> list[dict[str, Any]]:
    normalized_direction = normalize_blast_radius_direction(direction)
    validate_blast_radius_depth(depth)
    validate_positive_int(limit, "limit")
    allowed = frozenset(allowed_edge_types) if allowed_edge_types is not None else None
    edge_items = [edge for edge in edges if blast_radius_edge_matches(edge, edge_type, allowed)]
    outgoing = blast_radius_outgoing_edges(edge_items)
    incoming = blast_radius_incoming_edges(edge_items)
    items: list[dict[str, Any]] = []
    if normalized_direction in {"out", "both"}:
        items.extend(
            traverse_blast_radius_graph(
                entities_by_id,
                outgoing,
                entity_id,
                direction="out",
                depth=depth,
                limit=limit,
            )
        )
    if normalized_direction in {"in", "both"}:
        items.extend(
            traverse_blast_radius_graph(
                entities_by_id,
                incoming,
                entity_id,
                direction="in",
                depth=depth,
                limit=limit,
            )
        )
    items.sort(
        key=lambda item: (
            item.get("depth") or 0,
            item.get("direction") or "",
            string_value(mapping_value(item.get("edge")).get("edge_type")) or "",
            blast_radius_node_sort_value(mapping_value(item.get("neighbor"))),
        )
    )
    return items[:limit]


def blast_radius_outgoing_edges(edges: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        from_entity_id = string_value(edge.get("from_entity_id"))
        if from_entity_id:
            grouped.setdefault(from_entity_id, []).append(edge)
    return {key: sorted_blast_radius_edges(value) for key, value in grouped.items()}


def blast_radius_incoming_edges(edges: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        to_entity_id = string_value(edge.get("to_entity_id"))
        if to_entity_id:
            grouped.setdefault(to_entity_id, []).append(edge)
    return {key: sorted_blast_radius_edges(value) for key, value in grouped.items()}


def sorted_blast_radius_edges(edges: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        edges,
        key=lambda edge: (
            string_value(edge.get("edge_type")) or "",
            string_value(edge.get("source_name")) or "",
            string_value(edge.get("to_name")) or "",
            string_value(edge.get("edge_id")) or "",
        ),
    )


def traverse_blast_radius_graph(
    entities_by_id: Mapping[str, Mapping[str, Any]],
    adjacency: Mapping[str, list[Mapping[str, Any]]],
    entity_id: str,
    direction: str,
    depth: int,
    limit: int,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    queue: list[tuple[str, list[str], list[Mapping[str, Any]]]] = [(entity_id, [entity_id], [])]
    seen = {entity_id}
    target_nodes: dict[str, dict[str, Any]] = {}
    while queue and len(items) < limit:
        current_id, path_node_ids, path_edges = queue.pop(0)
        if len(path_edges) >= depth:
            continue
        for edge in adjacency.get(current_id, []):
            next_id = blast_radius_next_node_id(edge, direction)
            if not next_id or next_id in seen:
                continue
            neighbor = blast_radius_node_payload(edge, next_id, direction, entities_by_id, target_nodes)
            if direction == "out":
                next_path_node_ids = [*path_node_ids, next_id]
                next_path_edges = [*path_edges, edge]
                item_edge = edge
            else:
                next_path_node_ids = [next_id, *path_node_ids]
                next_path_edges = [edge, *path_edges]
                item_edge = next_path_edges[0]
            items.append(
                blast_radius_item(
                    direction,
                    item_edge,
                    neighbor,
                    next_path_node_ids,
                    next_path_edges,
                    entities_by_id,
                    target_nodes,
                )
            )
            seen.add(next_id)
            if next_id in entities_by_id and len(next_path_edges) < depth:
                queue.append((next_id, next_path_node_ids, next_path_edges))
            if len(items) >= limit:
                break
    return items


def blast_radius_edge_matches(
    edge: Mapping[str, Any],
    edge_type: str | None,
    allowed_edge_types: frozenset[str] | None,
) -> bool:
    current_type = string_value(edge.get("edge_type"))
    if not current_type:
        return False
    if edge_type:
        return current_type == edge_type
    return allowed_edge_types is None or current_type in allowed_edge_types


def blast_radius_node_sort_value(node: Mapping[str, Any]) -> str:
    return (
        string_value(node.get("source_name"))
        or string_value(node.get("entity_id"))
        or string_value(node.get("target_id"))
        or string_value(node.get("name"))
        or ""
    )
