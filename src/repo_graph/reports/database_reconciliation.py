"""Database reconciliation report builder."""

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
from repo_graph.vocabulary import SQL_EDGE_TYPES, SQL_ENTITY_TYPES

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
