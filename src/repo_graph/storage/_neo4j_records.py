"""Graph export records prepared for Neo4j writes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.graph import stable_id
from repo_graph.storage._neo4j_common import (
    graph_items,
    mapping_value,
    neo4j_properties,
    required_string,
    safe_property_key,
    sanitize_relationship_type,
    string_or_none,
)
from repo_graph.storage._neo4j_models import LoadSummary, PreparedGraphRecords


def prepare_graph_records(graph_data: Mapping[str, Any]) -> PreparedGraphRecords:
    source_records = [
        source_record(source, graph_data, index) for index, source in enumerate(graph_items(graph_data, "sources"))
    ]
    entity_records = [entity_record(entity) for entity in graph_items(graph_data, "entities")]
    edge_records = [edge_record(edge) for edge in graph_items(graph_data, "edges")]
    target_records = unresolved_target_records(edge_records)
    return PreparedGraphRecords(
        source_records=source_records,
        entity_records=entity_records,
        edge_records=edge_records,
        target_records=target_records,
    )


def normalize_source_names(source_names: Iterable[str] | None) -> tuple[str, ...]:
    if source_names is None:
        return ()
    return tuple(sorted({source_name.strip() for source_name in source_names if source_name.strip()}))


def validate_replace_sources(graph_data: Mapping[str, Any], source_names: tuple[str, ...]) -> None:
    if not source_names:
        return
    graph_sources = {source.get("name") for source in graph_items(graph_data, "sources")}
    missing = [source_name for source_name in source_names if source_name not in graph_sources]
    if missing:
        raise ValueError(f"Replace source is not present in graph: {', '.join(missing)}")


def graph_record(graph_data: Mapping[str, Any]) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    summary = mapping_value(graph_data.get("summary"))
    sources = graph_items(graph_data, "sources")
    record = {
        "graph_id": "current",
        "tool": metadata.get("tool"),
        "schema_version": metadata.get("schema_version"),
        "scope_name": metadata.get("scope_name"),
        "generated_at": metadata.get("generated_at"),
        "source_count": len(sources),
        "summary_json": json.dumps(summary, sort_keys=True),
        "sources_json": json.dumps(sources, sort_keys=True),
    }
    for key, value in summary.items():
        record[f"summary_{safe_property_key(key)}"] = value
    return neo4j_properties(record)


def source_record(source: Mapping[str, Any], graph_data: Mapping[str, Any], index: int) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    name = required_string(source, "name")
    source_id = stable_id("source", str(metadata.get("scope_name") or ""), name)
    properties = neo4j_properties(
        {
            "source_id": source_id,
            "index": index,
            "name": name,
            "type": source.get("type"),
            "path": source.get("path"),
            "url": source.get("url"),
            "ref": source.get("ref"),
            "commit": source.get("commit"),
        }
    )
    return {
        "source_id": source_id,
        "properties": properties,
    }


def entity_record(entity: Mapping[str, Any]) -> dict[str, Any]:
    properties = neo4j_properties(
        {
            "entity_id": required_string(entity, "entity_id"),
            "entity_type": entity.get("entity_type"),
            "name": entity.get("name"),
            "source_name": entity.get("source_name"),
            "file_path": entity.get("file_path"),
            "line_number": entity.get("line_number"),
            "aliases": entity.get("aliases", []),
            "properties": mapping_value(entity.get("properties")),
        }
    )
    return {
        "entity_id": properties["entity_id"],
        "properties": properties,
    }


def edge_record(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = neo4j_properties(
        {
            "edge_id": required_string(edge, "edge_id"),
            "from_entity_id": edge.get("from_entity_id"),
            "from_name": edge.get("from_name"),
            "from_type": edge.get("from_type"),
            "to_name": edge.get("to_name"),
            "to_type": edge.get("to_type"),
            "to_entity_id": edge.get("to_entity_id"),
            "edge_type": edge.get("edge_type"),
            "resolved": edge.get("resolved", False),
            "source_name": edge.get("source_name"),
            "file_path": edge.get("file_path"),
            "line_number": edge.get("line_number"),
            "identity_key": edge.get("identity_key"),
            "confidence": edge.get("confidence"),
            "parser": edge.get("parser"),
            "properties": mapping_value(edge.get("properties")),
        }
    )
    return {
        "edge_id": properties["edge_id"],
        "from_entity_id": properties.get("from_entity_id"),
        "to_entity_id": properties.get("to_entity_id"),
        "target_id": unresolved_target_id(edge),
        "relationship_type": sanitize_relationship_type(str(edge.get("edge_type") or "")),
        "resolved": bool(edge.get("resolved") and edge.get("to_entity_id")),
        "properties": properties,
    }


def unresolved_target_records(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for edge in unresolved_edges(edge_records):
        properties = edge["properties"]
        target_id = edge["target_id"]
        targets[target_id] = neo4j_properties(
            {
                "target_id": target_id,
                "name": properties.get("to_name"),
                "target_type": properties.get("to_type"),
                "source_name": properties.get("source_name"),
                "resolved": False,
            }
        )
    return [{"target_id": target_id, "properties": properties} for target_id, properties in sorted(targets.items())]


def unresolved_target_id(edge: Mapping[str, Any]) -> str:
    return stable_id(
        "unresolved",
        str(edge.get("source_name") or ""),
        str(edge.get("to_type") or ""),
        str(edge.get("to_name") or ""),
    )


def load_summary(
    graph_data: Mapping[str, Any],
    source_records: list[dict[str, Any]],
    edge_records: list[dict[str, Any]],
    target_records: list[dict[str, Any]],
    clear_existing: bool,
) -> LoadSummary:
    metadata = mapping_value(graph_data.get("metadata"))
    resolved_count = len(resolved_edges(edge_records))
    unresolved_count = len(edge_records) - resolved_count
    return LoadSummary(
        scope_name=string_or_none(metadata.get("scope_name")),
        schema_version=string_or_none(metadata.get("schema_version")),
        source_count=len(source_records),
        entity_count=len(graph_items(graph_data, "entities")),
        edge_count=len(edge_records),
        resolved_edge_count=resolved_count,
        unresolved_edge_count=unresolved_count,
        unresolved_target_count=len(target_records),
        clear_existing=clear_existing,
    )


def grouped_relationships(edge_records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in edge_records:
        groups.setdefault(record["relationship_type"], []).append(record)
    return groups


def resolved_edges(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in edge_records if record["resolved"]]


def unresolved_edges(edge_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in edge_records if not record["resolved"]]


__all__ = [
    "edge_record",
    "entity_record",
    "graph_record",
    "grouped_relationships",
    "load_summary",
    "normalize_source_names",
    "prepare_graph_records",
    "resolved_edges",
    "source_record",
    "unresolved_edges",
    "unresolved_target_id",
    "unresolved_target_records",
    "validate_replace_sources",
]
