"""Interaction report builder."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import (
    DEFAULT_EXAMPLE_LIMIT,
    DEFAULT_GROUP_LIMIT,
    add_if_present,
    compact_dict,
    edge_from_item,
    edge_matches,
    graph_items,
    mapping_value,
    string_value,
    validate_positive_int,
)
from repo_graph.vocabulary import INTERACTION_EDGE_TYPES


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
