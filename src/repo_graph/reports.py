"""Report builders for graph exports and API payloads."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.vocabulary import (
    CLASSIFICATION_ACTIONS,
    CLASSIFICATION_ORDER,
    LOCAL_EDGE_PREFIXES,
    MISSING_SOURCE_EDGE_TYPES,
    MISSING_SOURCE_TARGET_TYPES,
    PARSER_GAP_EDGE_TYPES,
    PARSER_GAP_TARGET_TYPES,
)

DEFAULT_GROUP_LIMIT = 50
DEFAULT_EXAMPLE_LIMIT = 3


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
