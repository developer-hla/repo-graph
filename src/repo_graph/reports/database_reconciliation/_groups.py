"""Database reconciliation group classification helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import DEFAULT_EXAMPLE_LIMIT, add_if_present, string_value
from repo_graph.reports.database_reconciliation._normalization import (
    database_edge_example,
    database_entity_example,
    edge_sql_target_key,
    entity_sql_key,
    entity_sql_name,
)

GroupMap = dict[tuple[str, str, str], dict[str, Any]]


def add_code_only_reference_groups(
    groups: GroupMap,
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
    groups: GroupMap,
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
    groups: GroupMap,
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
    groups: GroupMap,
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
    groups: GroupMap,
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
    groups: GroupMap,
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
