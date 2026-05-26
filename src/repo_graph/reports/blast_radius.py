"""Blast-radius report builder."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import compact_dict, graph_items, mapping_value, string_value, validate_positive_int
from repo_graph.vocabulary import IMPACT_PROFILES

DEFAULT_BLAST_RADIUS_LIMIT = 100
DEFAULT_BLAST_RADIUS_DEPTH = 2
BLAST_RADIUS_GROUP_EXAMPLE_LIMIT = 5


def blast_radius_report_from_graph(
    graph_data: Mapping[str, Any],
    entity_id: str,
    direction: str = "in",
    edge_type: str | None = None,
    depth: int = DEFAULT_BLAST_RADIUS_DEPTH,
    limit: int = DEFAULT_BLAST_RADIUS_LIMIT,
    profile: str = "impact",
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    entities_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in graph_items(graph_data, "entities")
        if string_value(entity.get("entity_id"))
    }
    entity = entities_by_id.get(entity_id)
    if entity is None:
        raise KeyError(entity_id)
    normalized_profile = normalize_blast_radius_profile(profile)
    allowed_edge_types = blast_radius_profile_edge_types(normalized_profile, edge_type)
    items = blast_radius_items_from_graph(
        entities_by_id,
        graph_items(graph_data, "edges"),
        entity_id,
        direction=direction,
        edge_type=edge_type,
        allowed_edge_types=allowed_edge_types,
        depth=depth,
        limit=limit,
    )
    return blast_radius_report_from_items(
        entity,
        items,
        entity_id=entity_id,
        direction=direction,
        edge_type=edge_type,
        depth=depth,
        limit=limit,
        profile=normalized_profile,
        allowed_edge_types=allowed_edge_types,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def blast_radius_report_from_items(
    entity: Mapping[str, Any],
    items: Iterable[Mapping[str, Any]],
    entity_id: str | None = None,
    direction: str = "in",
    edge_type: str | None = None,
    depth: int = DEFAULT_BLAST_RADIUS_DEPTH,
    limit: int | None = DEFAULT_BLAST_RADIUS_LIMIT,
    profile: str = "impact",
    allowed_edge_types: Iterable[str] | None = None,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_profile = normalize_blast_radius_profile(profile)
    normalized_direction = normalize_blast_radius_direction(direction)
    validate_blast_radius_depth(depth)
    if limit is not None:
        validate_positive_int(limit, "limit")
    edge_types = (
        frozenset(allowed_edge_types)
        if allowed_edge_types is not None
        else blast_radius_profile_edge_types(normalized_profile, edge_type)
    )
    item_list = list(items)
    if limit is not None:
        item_list = item_list[:limit]
    affected_sources = blast_radius_sources(item_list)
    path_groups = blast_radius_path_groups(item_list)
    return {
        "scope_name": scope_name,
        "generated_at": generated_at,
        "entity": dict(entity),
        "entity_id": entity_id or string_value(entity.get("entity_id")),
        "direction": normalized_direction,
        "depth": depth,
        "edge_type": edge_type,
        "profile": normalized_profile,
        "allowed_edge_types": sorted(edge_types) if edge_types else None,
        "limit": limit,
        "items": item_list,
        "count": len(item_list),
        "affected_source_count": len(affected_sources),
        "affected_sources": affected_sources,
        "path_groups": path_groups,
        "summary": blast_radius_summary(item_list, affected_sources, path_groups),
    }


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


def blast_radius_report_source_name(item: Mapping[str, Any]) -> str:
    neighbor = mapping_value(item.get("neighbor"))
    neighbor_source = string_value(neighbor.get("source_name"))
    if neighbor_source:
        return neighbor_source
    edge = mapping_value(item.get("edge"))
    return string_value(edge.get("source_name")) or "unknown"


def blast_radius_report_neighbor_type(item: Mapping[str, Any]) -> str:
    neighbor = mapping_value(item.get("neighbor"))
    return string_value(neighbor.get("entity_type")) or string_value(neighbor.get("target_type")) or "unknown"


def blast_radius_sources(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        source_name = blast_radius_report_source_name(item)
        group = grouped.setdefault(
            source_name,
            {
                "source_name": source_name,
                "count": 0,
                "min_depth": item.get("depth"),
                "entity_types": set(),
                "edge_types": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        group["min_depth"] = min_depth_value(group["min_depth"], item.get("depth"))
        add_string_value(group["entity_types"], blast_radius_report_neighbor_type(item))
        add_string_value(group["edge_types"], string_value(mapping_value(item.get("edge")).get("edge_type")))
        if len(group["examples"]) < BLAST_RADIUS_GROUP_EXAMPLE_LIMIT:
            group["examples"].append(item)

    result = [
        {
            "source_name": group["source_name"],
            "count": group["count"],
            "min_depth": group["min_depth"],
            "entity_types": sorted(group["entity_types"]),
            "edge_types": sorted(group["edge_types"]),
            "examples": group["examples"],
        }
        for group in grouped.values()
    ]
    result.sort(key=lambda item: (item["min_depth"] or 0, -item["count"], item["source_name"]))
    return result


def blast_radius_path_groups(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        source_name = blast_radius_report_source_name(item)
        edge_type = string_value(mapping_value(item.get("edge")).get("edge_type")) or "unknown"
        key = (source_name, edge_type)
        group = grouped.setdefault(
            key,
            {
                "source_name": source_name,
                "edge_type": edge_type,
                "count": 0,
                "min_depth": item.get("depth"),
                "examples": [],
            },
        )
        group["count"] += 1
        group["min_depth"] = min_depth_value(group["min_depth"], item.get("depth"))
        if len(group["examples"]) < BLAST_RADIUS_GROUP_EXAMPLE_LIMIT:
            group["examples"].append(item)

    result = list(grouped.values())
    result.sort(key=lambda item: (item["min_depth"] or 0, -item["count"], item["source_name"], item["edge_type"]))
    return result


def blast_radius_summary(
    items: list[Mapping[str, Any]],
    affected_sources: list[Mapping[str, Any]],
    path_groups: list[Mapping[str, Any]],
) -> dict[str, Any]:
    edge_type_counts: Counter[str] = Counter()
    neighbor_type_counts: Counter[str] = Counter()
    depths = [item.get("depth") for item in items if isinstance(item.get("depth"), int)]
    for item in items:
        edge_type_counts[string_value(mapping_value(item.get("edge")).get("edge_type")) or "unknown"] += 1
        neighbor_type_counts[blast_radius_report_neighbor_type(item)] += 1
    return {
        "path_count": len(items),
        "affected_source_count": len(affected_sources),
        "path_group_count": len(path_groups),
        "max_observed_depth": max(depths) if depths else None,
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "neighbor_type_counts": dict(sorted(neighbor_type_counts.items())),
    }


def normalize_blast_radius_profile(value: str) -> str:
    profile = value.strip().lower()
    if profile not in IMPACT_PROFILES:
        raise ValueError("Impact profile must be one of: all, impact, structural.")
    return profile


def blast_radius_profile_edge_types(profile: str, edge_type: str | None) -> frozenset[str] | None:
    if edge_type:
        return None
    return IMPACT_PROFILES[profile]


def normalize_blast_radius_direction(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"in", "out", "both"}:
        raise ValueError("Direction must be one of: in, out, both.")
    return normalized


def validate_blast_radius_depth(value: int) -> None:
    if value < 1:
        raise ValueError("Depth must be at least 1.")
    if value > 3:
        raise ValueError("Depth must be at most 3.")


def blast_radius_node_sort_value(node: Mapping[str, Any]) -> str:
    return (
        string_value(node.get("source_name"))
        or string_value(node.get("entity_id"))
        or string_value(node.get("target_id"))
        or string_value(node.get("name"))
        or ""
    )


def min_depth_value(left: Any, right: Any) -> int | None:
    depths = [value for value in (left, right) if isinstance(value, int)]
    return min(depths) if depths else None


def add_string_value(values: set[str], value: Any) -> None:
    if isinstance(value, str) and value:
        values.add(value)
