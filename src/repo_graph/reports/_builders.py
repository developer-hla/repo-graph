"""Report builders for graph exports and API payloads."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.vocabulary import (
    CLASSIFICATION_ACTIONS,
    CLASSIFICATION_ORDER,
    IMPACT_PROFILES,
    INTERACTION_EDGE_TYPES,
    LOCAL_EDGE_PREFIXES,
    MISSING_SOURCE_EDGE_TYPES,
    MISSING_SOURCE_TARGET_TYPES,
    PARSER_GAP_EDGE_TYPES,
    PARSER_GAP_TARGET_TYPES,
    SQL_EDGE_TYPES,
    SQL_ENTITY_TYPES,
)

DEFAULT_GROUP_LIMIT = 50
DEFAULT_EXAMPLE_LIMIT = 3
DEFAULT_BLAST_RADIUS_LIMIT = 100
DEFAULT_BLAST_RADIUS_DEPTH = 2
BLAST_RADIUS_GROUP_EXAMPLE_LIMIT = 5
CURRENT_DATABASE_SCHEMA_STATE = "current_database"
HISTORICAL_SCHEMA_STATE = "historical"
SQLSERVER_METADATA_PARSER = "sqlserver_metadata"
DATABASE_RECONCILIATION_ORDER = {
    "code_only_reference": 0,
    "unresolved_database_reference": 1,
    "schema_drift": 2,
    "migration_only_object": 3,
    "database_only_object": 4,
}
DATABASE_RECONCILIATION_ACTIONS = {
    "code_only_reference": "Confirm the object exists in the current database or update the code reference.",
    "unresolved_database_reference": (
        "Inspect the database metadata source scope; the catalog references a target outside the loaded graph."
    ),
    "schema_drift": "Compare source schema evidence with current database metadata before changing dependent code.",
    "migration_only_object": (
        "Treat this as historical evidence unless the object is restored in current database metadata."
    ),
    "database_only_object": (
        "Check whether this current database object is unused, externally used, or missing code/schema evidence."
    ),
}


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


def interactions_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    entities_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in graph_items(graph_data, "entities")
        if string_value(entity.get("entity_id"))
    }
    edges = [
        interaction_edge_with_target_source(edge, entities_by_id)
        for edge in graph_items(graph_data, "edges")
        if edge.get("edge_type") in INTERACTION_EDGE_TYPES
    ]
    return interactions_report(
        edges,
        source_name=source_name,
        target_source=target_source,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def interactions_report_from_items(
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    return interactions_report(
        [interaction_edge_from_item(item) for item in items],
        source_name=source_name,
        target_source=target_source,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def database_reconciliation_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    return database_reconciliation_report(
        graph_items(graph_data, "entities"),
        graph_items(graph_data, "edges"),
        source_name=source_name,
        database_source=database_source,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def database_reconciliation_report_from_items(
    entities: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    item_list = list(items)
    return database_reconciliation_report(
        [*entities, *relationship_sql_entities(item_list)],
        [edge_from_item(item) for item in item_list],
        source_name=source_name,
        database_source=database_source,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def database_reconciliation_report(
    entities: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")
    entity_items = [entity for entity in entities if is_sql_entity(entity)]
    entity_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in entity_items
        if string_value(entity.get("entity_id"))
    }
    current_entities = [
        entity
        for entity in entity_items
        if is_current_database_entity(entity) and source_matches(entity, database_source)
    ]
    historical_entities = [
        entity
        for entity in entity_items
        if schema_state(entity) == HISTORICAL_SCHEMA_STATE and source_matches(entity, source_name)
    ]
    source_schema_entities = [
        entity
        for entity in entity_items
        if schema_state(entity) not in {CURRENT_DATABASE_SCHEMA_STATE, HISTORICAL_SCHEMA_STATE}
        and source_matches(entity, source_name)
    ]
    current_index = entity_index_by_sql_name(current_entities)
    source_schema_index = entity_index_by_sql_name(source_schema_entities)
    historical_index = entity_index_by_sql_name(historical_entities)
    sql_edges = [edge for edge in edges if is_sql_edge(edge)]
    code_edges = [
        edge for edge in sql_edges if not is_database_metadata_edge(edge) and edge_matches(edge, source_name, None)
    ]
    metadata_edges = [
        edge for edge in sql_edges if is_database_metadata_edge(edge) and edge_matches(edge, database_source, None)
    ]

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    database_evidence_present = bool(current_entities)
    if database_evidence_present:
        add_code_only_reference_groups(groups, code_edges, entity_by_id, current_index, examples_per_group)
        add_migration_only_object_groups(groups, historical_index, current_index, examples_per_group)
        add_schema_drift_groups(groups, source_schema_index, current_index, examples_per_group)
        add_database_only_object_groups(
            groups,
            current_entities,
            code_edges,
            entity_by_id,
            source_schema_index,
            examples_per_group,
        )
    add_unresolved_database_reference_groups(groups, metadata_edges, examples_per_group)

    items = [finalize_database_reconciliation_group(group) for group in groups.values()]
    items.sort(
        key=lambda item: (
            database_reconciliation_rank(item["classification"]),
            -item["count"],
            item["target_type"],
            item["target_name"],
        )
    )
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "database_source": database_source}),
            "summary": database_reconciliation_summary(
                items,
                limited_items,
                current_entities,
                code_edges,
                metadata_edges,
                database_evidence_present,
            ),
            "classification_groups": database_reconciliation_classification_groups(items),
            "source_hotspots": database_reconciliation_source_hotspots(items),
            "target_hotspots": database_reconciliation_target_hotspots(items),
            "items": limited_items,
        }
    )


def relationship_sql_entities(items: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    entities: dict[str, Mapping[str, Any]] = {}
    for item in items:
        for key in ("from_entity", "target"):
            value = item.get(key)
            if isinstance(value, Mapping) and is_sql_entity(value):
                entity_id = string_value(value.get("entity_id")) or f"{value.get('source_name')}:{value.get('name')}"
                entities[entity_id] = value
    return list(entities.values())


def add_code_only_reference_groups(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    code_edges: list[Mapping[str, Any]],
    entity_by_id: Mapping[str, Mapping[str, Any]],
    current_index: Mapping[str, list[Mapping[str, Any]]],
    examples_per_group: int,
) -> None:
    for edge in code_edges:
        target_key = edge_sql_target_key(edge, entity_by_id)
        if not target_key or target_key in current_index:
            continue
        group = database_reconciliation_group(
            groups,
            "code_only_reference",
            string_value(edge.get("to_name")) or target_key,
            string_value(edge.get("to_type")) or "sql_object",
        )
        increment_database_reconciliation_group(
            group,
            source_name=string_value(edge.get("source_name")),
            evidence_type=string_value(edge.get("edge_type")),
            example=database_edge_example(edge),
            examples_per_group=examples_per_group,
        )


def add_unresolved_database_reference_groups(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    metadata_edges: list[Mapping[str, Any]],
    examples_per_group: int,
) -> None:
    for edge in metadata_edges:
        if bool(edge.get("resolved")):
            continue
        group = database_reconciliation_group(
            groups,
            "unresolved_database_reference",
            string_value(edge.get("to_name")) or "unknown",
            string_value(edge.get("to_type")) or "sql_object",
        )
        increment_database_reconciliation_group(
            group,
            database_source=string_value(edge.get("source_name")),
            evidence_type=string_value(edge.get("edge_type")),
            example=database_edge_example(edge),
            examples_per_group=examples_per_group,
        )


def add_migration_only_object_groups(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    historical_index: Mapping[str, list[Mapping[str, Any]]],
    current_index: Mapping[str, list[Mapping[str, Any]]],
    examples_per_group: int,
) -> None:
    for target_key, entities in historical_index.items():
        if target_key in current_index:
            continue
        for entity in entities:
            group = database_reconciliation_group(
                groups,
                "migration_only_object",
                entity_sql_name(entity) or target_key,
                string_value(entity.get("entity_type")) or "sql_object",
            )
            increment_database_reconciliation_group(
                group,
                source_name=string_value(entity.get("source_name")),
                evidence_type="historical_schema",
                example=database_entity_example(entity),
                examples_per_group=examples_per_group,
            )


def add_schema_drift_groups(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    source_schema_index: Mapping[str, list[Mapping[str, Any]]],
    current_index: Mapping[str, list[Mapping[str, Any]]],
    examples_per_group: int,
) -> None:
    for target_key, source_entities in source_schema_index.items():
        current_entities = current_index.get(target_key, [])
        if not current_entities:
            continue
        source_types = {string_value(entity.get("entity_type")) for entity in source_entities}
        current_types = {string_value(entity.get("entity_type")) for entity in current_entities}
        if source_types == current_types:
            continue
        target_name = entity_sql_name(current_entities[0]) or entity_sql_name(source_entities[0]) or target_key
        target_type = ",".join(sorted(item for item in current_types if item)) or "sql_object"
        group = database_reconciliation_group(groups, "schema_drift", target_name, target_type)
        for entity in source_entities:
            increment_database_reconciliation_group(
                group,
                source_name=string_value(entity.get("source_name")),
                evidence_type=string_value(entity.get("entity_type")),
                example=database_entity_example(entity),
                examples_per_group=examples_per_group,
            )
        for entity in current_entities:
            add_if_present(group["database_sources"], string_value(entity.get("source_name")))
            add_if_present(group["current_database_types"], string_value(entity.get("entity_type")))


def add_database_only_object_groups(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    current_entities: list[Mapping[str, Any]],
    code_edges: list[Mapping[str, Any]],
    entity_by_id: Mapping[str, Mapping[str, Any]],
    source_schema_index: Mapping[str, list[Mapping[str, Any]]],
    examples_per_group: int,
) -> None:
    code_reference_keys = {target_key for edge in code_edges if (target_key := edge_sql_target_key(edge, entity_by_id))}
    for entity in current_entities:
        target_key = entity_sql_key(entity)
        if not target_key or target_key in code_reference_keys or target_key in source_schema_index:
            continue
        group = database_reconciliation_group(
            groups,
            "database_only_object",
            entity_sql_name(entity) or target_key,
            string_value(entity.get("entity_type")) or "sql_object",
        )
        increment_database_reconciliation_group(
            group,
            database_source=string_value(entity.get("source_name")),
            evidence_type="current_database",
            example=database_entity_example(entity),
            examples_per_group=examples_per_group,
        )
        add_if_present(group["current_database_types"], string_value(entity.get("entity_type")))


def database_reconciliation_group(
    groups: dict[tuple[str, str, str], dict[str, Any]],
    classification: str,
    target_name: str,
    target_type: str,
) -> dict[str, Any]:
    key = (classification, target_type, target_name)
    return groups.setdefault(
        key,
        {
            "classification": classification,
            "target_type": target_type,
            "target_name": target_name,
            "count": 0,
            "source_names": set(),
            "database_sources": set(),
            "evidence_types": set(),
            "current_database_types": set(),
            "examples": [],
        },
    )


def increment_database_reconciliation_group(
    group: dict[str, Any],
    source_name: str | None = None,
    database_source: str | None = None,
    evidence_type: str | None = None,
    example: dict[str, Any] | None = None,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> None:
    group["count"] += 1
    add_if_present(group["source_names"], source_name)
    add_if_present(group["database_sources"], database_source)
    add_if_present(group["evidence_types"], evidence_type)
    if example and len(group["examples"]) < examples_per_group:
        group["examples"].append(example)


def finalize_database_reconciliation_group(group: Mapping[str, Any]) -> dict[str, Any]:
    classification = string_value(group.get("classification")) or "unknown"
    return compact_dict(
        {
            "classification": classification,
            "classification_reason": database_reconciliation_reason(classification),
            "recommended_action": DATABASE_RECONCILIATION_ACTIONS.get(classification),
            "target_type": group.get("target_type"),
            "target_name": group.get("target_name"),
            "count": group.get("count"),
            "source_names": sorted(group.get("source_names", set())),
            "database_sources": sorted(group.get("database_sources", set())),
            "evidence_types": sorted(group.get("evidence_types", set())),
            "current_database_types": sorted(group.get("current_database_types", set())),
            "examples": group.get("examples"),
        }
    )


def database_reconciliation_reason(classification: str) -> str:
    reasons = {
        "code_only_reference": "Code or source SQL references an object not found in current database metadata.",
        "unresolved_database_reference": "Database metadata references an object outside the loaded metadata scope.",
        "schema_drift": "Source schema evidence and current database metadata disagree on the object type.",
        "migration_only_object": (
            "Historical migration evidence exists, but current database metadata does not show the object."
        ),
        "database_only_object": (
            "Current database metadata shows the object, but code and source schema evidence did not reference it."
        ),
    }
    return reasons.get(classification, "No database reconciliation rule matched this item.")


def database_reconciliation_summary(
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
    current_entities: list[Mapping[str, Any]],
    code_edges: list[Mapping[str, Any]],
    metadata_edges: list[Mapping[str, Any]],
    database_evidence_present: bool,
) -> dict[str, Any]:
    classification_counts: Counter[str] = Counter()
    classification_group_counts = Counter(item["classification"] for item in items)
    for item in items:
        classification_counts[item["classification"]] += int(item["count"])
    return {
        "current_database_entity_count": len(current_entities),
        "code_sql_reference_count": len(code_edges),
        "database_metadata_edge_count": len(metadata_edges),
        "database_evidence_present": database_evidence_present,
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "classification_counts": dict(sorted(classification_counts.items())),
        "classification_group_counts": dict(sorted(classification_group_counts.items())),
    }


def database_reconciliation_classification_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        classification = item["classification"]
        group = groups.setdefault(
            classification,
            {
                "classification": classification,
                "recommended_action": DATABASE_RECONCILIATION_ACTIONS.get(classification),
                "count": 0,
                "group_count": 0,
                "source_names": set(),
                "database_sources": set(),
            },
        )
        group["count"] += int(item["count"])
        group["group_count"] += 1
        group["source_names"].update(item.get("source_names", []))
        group["database_sources"].update(item.get("database_sources", []))
    return sorted(
        (
            compact_dict(
                {
                    "classification": group["classification"],
                    "recommended_action": group["recommended_action"],
                    "count": group["count"],
                    "group_count": group["group_count"],
                    "source_names": sorted(group["source_names"]),
                    "database_sources": sorted(group["database_sources"]),
                }
            )
            for group in groups.values()
        ),
        key=lambda group: (database_reconciliation_rank(group["classification"]), -group["count"]),
    )


def database_reconciliation_source_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for item in items:
        for source_name in (*item.get("source_names", []), *item.get("database_sources", [])):
            hotspot = hotspots.setdefault(
                source_name,
                {"source_name": source_name, "count": 0, "classifications": set(), "target_names": set()},
            )
            hotspot["count"] += int(item["count"])
            add_if_present(hotspot["classifications"], item["classification"])
            add_if_present(hotspot["target_names"], item["target_name"])
    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "classifications": sorted(hotspot["classifications"], key=database_reconciliation_rank),
                "target_names": sorted(hotspot["target_names"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def database_reconciliation_target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "target_type": item["target_type"],
                "target_name": item["target_name"],
                "count": item["count"],
                "classifications": [item["classification"]],
            }
            for item in items
        ),
        key=lambda hotspot: (-int(hotspot["count"]), hotspot["target_type"], hotspot["target_name"]),
    )[:limit]


def database_reconciliation_rank(classification: str) -> int:
    return DATABASE_RECONCILIATION_ORDER.get(classification, len(DATABASE_RECONCILIATION_ORDER))


def database_edge_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "kind": "edge",
            "edge_id": string_value(edge.get("edge_id")),
            "source_name": string_value(edge.get("source_name")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "to_name": string_value(edge.get("to_name")),
            "to_type": string_value(edge.get("to_type")),
            "edge_type": string_value(edge.get("edge_type")),
            "resolved": edge.get("resolved"),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
            "sql_operation": string_value(properties.get("sql_operation")),
            "schema_state": string_value(properties.get("schema_state")),
            "metadata_source": string_value(properties.get("metadata_source")),
        }
    )


def database_entity_example(entity: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(entity.get("properties"))
    return compact_dict(
        {
            "kind": "entity",
            "entity_id": string_value(entity.get("entity_id")),
            "entity_type": string_value(entity.get("entity_type")),
            "name": string_value(entity.get("name")),
            "source_name": string_value(entity.get("source_name")),
            "file_path": string_value(entity.get("file_path")),
            "line_number": entity.get("line_number"),
            "schema": string_value(properties.get("schema")),
            "full_name": string_value(properties.get("full_name")),
            "schema_state": string_value(properties.get("schema_state")),
            "metadata_source": string_value(properties.get("metadata_source")),
        }
    )


def interactions_report(
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    target_source: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")
    filtered_edges = [
        edge
        for edge in edges
        if edge.get("edge_type") in INTERACTION_EDGE_TYPES
        and interaction_edge_matches(edge, source_name, target_source, edge_type)
    ]
    groups: dict[tuple[str, str, str, str, str, str, str, str], dict[str, Any]] = {}
    for edge in filtered_edges:
        properties = mapping_value(edge.get("properties"))
        key = (
            string_value(edge.get("source_name")) or "unknown",
            string_value(edge.get("target_source")) or "unresolved",
            string_value(edge.get("to_type")) or "unknown",
            string_value(edge.get("to_name")) or "unknown",
            string_value(edge.get("edge_type")) or "unknown",
            string_value(properties.get("target_boundary")) or "unknown",
            string_value(properties.get("dependency_scope")) or "unknown",
            string_value(properties.get("interaction_kind")) or "unknown",
        )
        group = groups.setdefault(
            key,
            {
                "from_source": key[0],
                "target_source": None if key[1] == "unresolved" else key[1],
                "to_type": key[2],
                "to_name": key[3],
                "edge_type": key[4],
                "target_boundary": key[5],
                "dependency_scope": key[6],
                "interaction_kind": key[7],
                "count": 0,
                "resolved_count": 0,
                "unresolved_count": 0,
                "parsers": set(),
                "protocols": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        if bool(edge.get("resolved")):
            group["resolved_count"] += 1
        else:
            group["unresolved_count"] += 1
        add_if_present(group["parsers"], string_value(edge.get("parser")))
        add_if_present(group["protocols"], string_value(properties.get("protocol")))
        if len(group["examples"]) < examples_per_group:
            group["examples"].append(interaction_example(edge))

    items = [finalize_interaction_group(group) for group in groups.values()]
    items.sort(
        key=lambda item: (
            -item["count"],
            item["from_source"],
            item.get("target_source") or "",
            item["target_boundary"],
            item["dependency_scope"],
            item["to_type"],
            item["to_name"],
        )
    )
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "target_source": target_source, "edge_type": edge_type}),
            "summary": interaction_summary(filtered_edges, items, limited_items),
            "source_hotspots": interaction_source_hotspots(items),
            "target_hotspots": interaction_target_hotspots(items),
            "items": limited_items,
        }
    )


def interaction_edge_with_target_source(
    edge: Mapping[str, Any],
    entities_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    target_entity_id = string_value(edge.get("to_entity_id"))
    target_entity = entities_by_id.get(target_entity_id) if target_entity_id else None
    if not target_entity:
        return edge
    return {**edge, "target_source": string_value(target_entity.get("source_name"))}


def interaction_edge_from_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    edge = edge_from_item(item)
    target_source = string_value(item.get("to_source"))
    target = item.get("target")
    if not target_source and isinstance(target, Mapping):
        target_source = string_value(target.get("source_name"))
    if not target_source:
        return edge
    return {**edge, "target_source": target_source}


def interaction_edge_matches(
    edge: Mapping[str, Any],
    source_name: str | None,
    target_source: str | None,
    edge_type: str | None,
) -> bool:
    if not edge_matches(edge, source_name, edge_type):
        return False
    return not (target_source and edge.get("target_source") != target_source)


def finalize_interaction_group(group: Mapping[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "from_source": group["from_source"],
            "target_source": group["target_source"],
            "to_type": group["to_type"],
            "to_name": group["to_name"],
            "edge_type": group["edge_type"],
            "target_boundary": group["target_boundary"],
            "dependency_scope": group["dependency_scope"],
            "interaction_kind": group["interaction_kind"],
            "count": group["count"],
            "resolved_count": group["resolved_count"],
            "unresolved_count": group["unresolved_count"],
            "parsers": sorted(group["parsers"]),
            "protocols": sorted(group["protocols"]),
            "examples": group["examples"],
        }
    )


def interaction_summary(
    edges: list[Mapping[str, Any]],
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
) -> dict[str, Any]:
    boundary_counts: Counter[str] = Counter()
    scope_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    edge_type_counts: Counter[str] = Counter()
    for edge in edges:
        properties = mapping_value(edge.get("properties"))
        boundary_counts[string_value(properties.get("target_boundary")) or "unknown"] += 1
        scope_counts[string_value(properties.get("dependency_scope")) or "unknown"] += 1
        kind_counts[string_value(properties.get("interaction_kind")) or "unknown"] += 1
        edge_type_counts[string_value(edge.get("edge_type")) or "unknown"] += 1
    return {
        "interaction_edge_count": len(edges),
        "resolved_edge_count": sum(1 for edge in edges if bool(edge.get("resolved"))),
        "unresolved_edge_count": sum(1 for edge in edges if not bool(edge.get("resolved"))),
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "target_boundary_counts": dict(sorted(boundary_counts.items())),
        "dependency_scope_counts": dict(sorted(scope_counts.items())),
        "interaction_kind_counts": dict(sorted(kind_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
    }


def interaction_source_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for item in items:
        source_name = item["from_source"]
        hotspot = hotspots.setdefault(
            source_name,
            {"source_name": source_name, "count": 0, "group_count": 0, "target_sources": set(), "edge_types": set()},
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["target_sources"], string_value(item.get("target_source")))
        add_if_present(hotspot["edge_types"], item["edge_type"])
    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "group_count": hotspot["group_count"],
                "target_sources": sorted(hotspot["target_sources"]),
                "edge_types": sorted(hotspot["edge_types"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def interaction_target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[tuple[str | None, str, str], dict[str, Any]] = {}
    for item in items:
        key = (string_value(item.get("target_source")), item["to_type"], item["to_name"])
        hotspot = hotspots.setdefault(
            key,
            {
                "target_source": key[0],
                "to_type": key[1],
                "to_name": key[2],
                "count": 0,
                "group_count": 0,
                "from_sources": set(),
                "edge_types": set(),
            },
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["from_sources"], item["from_source"])
        add_if_present(hotspot["edge_types"], item["edge_type"])
    return sorted(
        (
            compact_dict(
                {
                    "target_source": hotspot["target_source"],
                    "to_type": hotspot["to_type"],
                    "to_name": hotspot["to_name"],
                    "count": hotspot["count"],
                    "group_count": hotspot["group_count"],
                    "from_sources": sorted(hotspot["from_sources"]),
                    "edge_types": sorted(hotspot["edge_types"]),
                }
            )
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (
            -hotspot["count"],
            hotspot.get("target_source") or "",
            hotspot["to_type"],
            hotspot["to_name"],
        ),
    )[:limit]


def interaction_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "edge_id": string_value(edge.get("edge_id")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "to_name": string_value(edge.get("to_name")),
            "to_type": string_value(edge.get("to_type")),
            "target_source": string_value(edge.get("target_source")),
            "resolved": edge.get("resolved"),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "confidence": string_value(edge.get("confidence")),
            "client": string_value(properties.get("client")),
            "protocol": string_value(properties.get("protocol")),
            "http_method": string_value(properties.get("http_method")),
            "target_path": string_value(properties.get("target_path")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
            "config_key": string_value(properties.get("config_key")),
            "sql_operation": string_value(properties.get("sql_operation")),
            "database_object_type": string_value(properties.get("database_object_type")),
            "schema_state": string_value(properties.get("schema_state")),
            "sql_source_kind": string_value(properties.get("sql_source_kind")),
        }
    )


def unresolved_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    edges = [edge for edge in graph_items(graph_data, "edges") if not bool(edge.get("resolved"))]
    return unresolved_report(
        edges,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def unresolved_report_from_items(
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    edges = [edge_from_item(item) for item in items]
    return unresolved_report(
        edges,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def unresolved_report(
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    edge_type: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    filtered_edges = [edge for edge in edges if edge_matches(edge, source_name, edge_type)]

    for edge in filtered_edges:
        classification, reason = classify_unresolved_edge(edge)
        key = (
            string_value(edge.get("edge_type")) or "unknown",
            string_value(edge.get("to_type")) or "unknown",
            string_value(edge.get("to_name")) or "unknown",
            classification,
        )
        group = groups.setdefault(
            key,
            {
                "edge_type": key[0],
                "to_type": key[1],
                "to_name": key[2],
                "classification": classification,
                "classification_reason": reason,
                "count": 0,
                "source_names": set(),
                "parsers": set(),
                "examples": [],
            },
        )
        group["count"] += 1
        add_if_present(group["source_names"], string_value(edge.get("source_name")))
        add_if_present(group["parsers"], string_value(edge.get("parser")))
        if len(group["examples"]) < examples_per_group:
            group["examples"].append(edge_example(edge))

    items = [finalize_group(group) for group in groups.values()]
    items.sort(key=lambda item: (-item["count"], item["classification"], item["edge_type"], item["to_name"]))
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "edge_type": edge_type}),
            "summary": report_summary(filtered_edges, items, limited_items),
            "classification_groups": classification_group_summaries(items),
            "source_hotspots": source_hotspots_from_edges(filtered_edges),
            "target_hotspots": target_hotspots(items),
            "items": limited_items,
        }
    )


def edge_from_item(item: Mapping[str, Any]) -> Mapping[str, Any]:
    edge = item.get("edge")
    if isinstance(edge, Mapping):
        return edge
    return item


def edge_matches(edge: Mapping[str, Any], source_name: str | None, edge_type: str | None) -> bool:
    if source_name and edge.get("source_name") != source_name:
        return False
    return not (edge_type and edge.get("edge_type") != edge_type)


def classify_unresolved_edge(edge: Mapping[str, Any]) -> tuple[str, str]:
    properties = mapping_value(edge.get("properties"))
    if properties.get("resolution_status") == "ambiguous" or properties.get("resolution_candidates"):
        return (
            "ambiguous_target",
            "Multiple graph entities matched this reference, so Repo Graph left it unresolved.",
        )

    edge_type = string_value(edge.get("edge_type")) or ""
    target_type = string_value(edge.get("to_type")) or ""
    if edge_type.startswith(LOCAL_EDGE_PREFIXES):
        return (
            "likely_parser_gap",
            "This local declaration or topology edge should usually resolve inside the scanned source.",
        )
    if edge_type in MISSING_SOURCE_EDGE_TYPES or target_type in MISSING_SOURCE_TARGET_TYPES:
        return (
            "likely_missing_source",
            "The target usually resolves when the source set includes the referenced repo, package, service, "
            "or database project.",
        )
    if edge_type in PARSER_GAP_EDGE_TYPES or target_type in PARSER_GAP_TARGET_TYPES:
        return (
            "likely_parser_gap",
            "The target may need broader source scope or deeper parser coverage before it can resolve.",
        )
    return (
        "needs_review",
        "No specific unresolved-edge heuristic matched this reference.",
    )


def edge_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "edge_id": string_value(edge.get("edge_id")),
            "source_name": string_value(edge.get("source_name")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "confidence": string_value(edge.get("confidence")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
        }
    )


def finalize_group(group: Mapping[str, Any]) -> dict[str, Any]:
    classification = group["classification"]
    return {
        "edge_type": group["edge_type"],
        "to_type": group["to_type"],
        "to_name": group["to_name"],
        "classification": classification,
        "classification_reason": group["classification_reason"],
        "recommended_action": recommended_action(classification),
        "count": group["count"],
        "source_names": sorted(group["source_names"]),
        "parsers": sorted(group["parsers"]),
        "examples": group["examples"],
    }


def recommended_action(classification: str) -> str:
    return CLASSIFICATION_ACTIONS.get(classification, CLASSIFICATION_ACTIONS["needs_review"])


def classification_group_summaries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        classification = item["classification"]
        group = groups.setdefault(
            classification,
            {
                "classification": classification,
                "recommended_action": recommended_action(classification),
                "count": 0,
                "group_count": 0,
                "source_names": set(),
                "edge_types": set(),
            },
        )
        group["count"] += item["count"]
        group["group_count"] += 1
        group["source_names"].update(item["source_names"])
        add_if_present(group["edge_types"], item["edge_type"])

    summaries = [
        {
            "classification": group["classification"],
            "recommended_action": group["recommended_action"],
            "count": group["count"],
            "group_count": group["group_count"],
            "source_names": sorted(group["source_names"]),
            "edge_types": sorted(group["edge_types"]),
        }
        for group in groups.values()
    ]
    summaries.sort(key=lambda group: (classification_rank(group["classification"]), -group["count"]))
    return summaries


def source_hotspots_from_edges(edges: list[Mapping[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for edge in edges:
        source_name = string_value(edge.get("source_name")) or "unknown"
        classification, _reason = classify_unresolved_edge(edge)
        edge_type = string_value(edge.get("edge_type")) or "unknown"
        target_type = string_value(edge.get("to_type")) or "unknown"
        target_name = string_value(edge.get("to_name")) or "unknown"
        hotspot = hotspots.setdefault(
            source_name,
            {
                "source_name": source_name,
                "count": 0,
                "group_keys": set(),
                "classifications": set(),
                "edge_types": set(),
            },
        )
        hotspot["count"] += 1
        hotspot["group_keys"].add((edge_type, target_type, target_name, classification))
        add_if_present(hotspot["classifications"], classification)
        add_if_present(hotspot["edge_types"], edge_type)

    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "group_count": len(hotspot["group_keys"]),
                "classifications": sorted(hotspot["classifications"], key=classification_rank),
                "edge_types": sorted(hotspot["edge_types"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (item["to_type"], item["to_name"])
        hotspot = hotspots.setdefault(
            key,
            {
                "to_type": item["to_type"],
                "to_name": item["to_name"],
                "count": 0,
                "group_count": 0,
                "classifications": set(),
                "edge_types": set(),
                "source_names": set(),
            },
        )
        hotspot["count"] += item["count"]
        hotspot["group_count"] += 1
        add_if_present(hotspot["classifications"], item["classification"])
        add_if_present(hotspot["edge_types"], item["edge_type"])
        hotspot["source_names"].update(item["source_names"])

    return sorted(
        (
            {
                "to_type": hotspot["to_type"],
                "to_name": hotspot["to_name"],
                "count": hotspot["count"],
                "group_count": hotspot["group_count"],
                "classifications": sorted(hotspot["classifications"], key=classification_rank),
                "edge_types": sorted(hotspot["edge_types"]),
                "source_names": sorted(hotspot["source_names"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["to_type"], hotspot["to_name"]),
    )[:limit]


def classification_rank(classification: str) -> int:
    return CLASSIFICATION_ORDER.get(classification, len(CLASSIFICATION_ORDER))


def report_summary(
    edges: list[Mapping[str, Any]],
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
) -> dict[str, Any]:
    classification_edge_counts: Counter[str] = Counter()
    classification_group_counts = Counter(item["classification"] for item in items)
    for item in items:
        classification_edge_counts[item["classification"]] += item["count"]
    return {
        "unresolved_edge_count": len(edges),
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "classification_edge_counts": dict(sorted(classification_edge_counts.items())),
        "classification_group_counts": dict(sorted(classification_group_counts.items())),
    }


def is_sql_entity(entity: Mapping[str, Any]) -> bool:
    return string_value(entity.get("entity_type")) in SQL_ENTITY_TYPES


def is_sql_edge(edge: Mapping[str, Any]) -> bool:
    return string_value(edge.get("edge_type")) in SQL_EDGE_TYPES


def is_database_metadata_edge(edge: Mapping[str, Any]) -> bool:
    return string_value(edge.get("parser")) == SQLSERVER_METADATA_PARSER


def is_current_database_entity(entity: Mapping[str, Any]) -> bool:
    return schema_state(entity) == CURRENT_DATABASE_SCHEMA_STATE


def source_matches(item: Mapping[str, Any], source_name: str | None) -> bool:
    return not source_name or item.get("source_name") == source_name


def schema_state(entity: Mapping[str, Any]) -> str | None:
    return string_value(mapping_value(entity.get("properties")).get("schema_state"))


def entity_index_by_sql_name(entities: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    index: dict[str, list[Mapping[str, Any]]] = {}
    for entity in entities:
        key = entity_sql_key(entity)
        if key:
            index.setdefault(key, []).append(entity)
    return index


def entity_sql_key(entity: Mapping[str, Any]) -> str | None:
    return normalized_sql_key(entity_sql_name(entity))


def entity_sql_name(entity: Mapping[str, Any]) -> str | None:
    properties = mapping_value(entity.get("properties"))
    return string_value(properties.get("full_name")) or string_value(entity.get("name"))


def edge_sql_target_key(
    edge: Mapping[str, Any],
    entity_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    to_entity_id = string_value(edge.get("to_entity_id"))
    target_entity = entity_by_id.get(to_entity_id) if to_entity_id else None
    if target_entity:
        return entity_sql_key(target_entity)
    properties = mapping_value(edge.get("properties"))
    return normalized_sql_key(
        string_value(properties.get("normalized_target"))
        or string_value(properties.get("raw_target"))
        or string_value(edge.get("to_name"))
    )


def normalized_sql_key(value: str | None) -> str | None:
    if not value:
        return None
    return ".".join(part.strip().strip("[]`\"'").lower() for part in value.split(".") if part.strip())


def graph_items(graph_data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw_items = graph_data.get(key, [])
    if not isinstance(raw_items, list):
        raise ValueError(f"Graph field '{key}' must be a list.")
    return [item for item in raw_items if isinstance(item, Mapping)]


def mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def string_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def add_if_present(values: set[str], value: str | None) -> None:
    if value:
        values.add(value)


def compact_dict(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in (None, {})}


def validate_positive_int(value: int, name: str) -> None:
    if value < 1:
        raise ValueError(f"{name} must be at least 1.")
