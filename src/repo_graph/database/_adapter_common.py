"""Shared database metadata fact adapter helpers."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import CURRENT_DATABASE_SCHEMA_STATE
from repo_graph.database._metadata_edges import database_trigger_metadata_edge
from repo_graph.database._models import DatabaseGraphError, DatabaseScanResult, EdgeBuildResult, EntityMatch
from repo_graph.database._naming import (
    database_full_name,
    database_trigger_full_name,
    metadata_identity_key,
    normalize_sql_identifier,
    split_sql_name,
    trigger_source_name,
)
from repo_graph.extraction.facts import EntityFact, EntityReference


def database_trigger_entity(
    source_name: str,
    database_engine: str,
    schema: str,
    name: str,
    table_schema: str,
    table: str,
    metadata_source: str,
    events: tuple[str, ...],
    is_enabled: bool | None,
    extra_properties: dict[str, Any] | None = None,
) -> EntityFact:
    trigger_name = normalize_sql_identifier(name)
    table_full_name = database_full_name(table_schema, table)
    full_name = database_trigger_full_name(table_schema, table, trigger_name)
    trigger_properties = {
        "schema": normalize_sql_identifier(schema),
        "object_name": trigger_name,
        "full_name": full_name,
        "schema_state": CURRENT_DATABASE_SCHEMA_STATE,
        "database_engine": database_engine,
        "metadata_source": metadata_source,
        "trigger_table": table_full_name,
        "trigger_events": list(events),
        "trigger_enabled": is_enabled,
        **(extra_properties or {}),
    }
    return EntityFact(
        entity_type="sql_trigger",
        name=full_name,
        source_name=source_name,
        aliases=frozenset(
            {
                trigger_name,
                database_full_name(schema, trigger_name),
                trigger_source_name(table, trigger_name),
            }
        ),
        properties={key: value for key, value in trigger_properties.items() if value is not None},
    )


def database_object_entity(
    source_name: str,
    database_engine: str,
    entity_type: str,
    schema: str,
    name: str,
    metadata_source: str,
    extra_properties: dict[str, Any] | None = None,
) -> EntityFact:
    full_name = database_full_name(schema, name)
    schema, short_name = split_sql_name(full_name)
    return EntityFact(
        entity_type=entity_type,
        name=full_name,
        source_name=source_name,
        aliases=frozenset({short_name}),
        properties={
            "schema": schema,
            "object_name": short_name,
            "full_name": full_name,
            "schema_state": CURRENT_DATABASE_SCHEMA_STATE,
            "database_engine": database_engine,
            "metadata_source": metadata_source,
            **(extra_properties or {}),
        },
    )


def trigger_edge(
    engine_label: str,
    source_name: str,
    metadata_source: str,
    database_engine: str,
    parser: str,
    trigger_schema: str,
    trigger_name: str,
    table_schema: str,
    table_name: str,
    events: tuple[str, ...],
    is_enabled: bool | None,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    trigger_full_name = database_trigger_full_name(table_schema, table_name, trigger_name)
    table_full_name = database_full_name(table_schema, table_name)
    source_match = find_entity(entity_index, "sql_trigger", trigger_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label=engine_label,
                source_name=source_name,
                metadata_source=metadata_source,
                relationship_name="trigger",
                source_object=database_full_name(trigger_schema, trigger_name),
                target_object=table_full_name,
                candidates=source_match.candidates,
            )
        )

    return EdgeBuildResult(
        edge=database_trigger_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, "sql_table", table_full_name),
            target_name=table_full_name,
            source_name=source_name,
            metadata_source=metadata_source,
            identity_key=metadata_identity_key("trigger", trigger_full_name, table_full_name),
            database_engine=database_engine,
            parser=parser,
            trigger_name=trigger_name,
            events=events,
            is_enabled=is_enabled,
        )
    )


def missing_source_error(
    engine_label: str,
    source_name: str,
    metadata_source: str,
    relationship_name: str,
    source_object: str,
    target_object: str,
    candidates: tuple[EntityFact, ...],
) -> DatabaseGraphError:
    if candidates:
        message = f"Ambiguous source entity for {engine_label} {relationship_name}: {source_object}"
        code = "ambiguous_source_entity"
    else:
        message = f"Missing source entity for {engine_label} {relationship_name}: {source_object}"
        code = "missing_source_entity"
    return DatabaseGraphError(
        code=code,
        message=message,
        source_name=source_name,
        metadata_source=metadata_source,
        source_object=source_object,
        target_object=target_object,
    )


def add_entity(entities_by_ref: dict[EntityReference, EntityFact], entity: EntityFact) -> None:
    existing = entities_by_ref.get(entity.reference)
    if existing is None:
        entities_by_ref[entity.reference] = entity
        return
    entities_by_ref[entity.reference] = EntityFact(
        entity_type=existing.entity_type,
        name=existing.name,
        source_name=existing.source_name,
        file_path=existing.file_path,
        line_number=existing.line_number,
        aliases=existing.aliases | entity.aliases,
        properties={
            **existing.properties,
            **{key: value for key, value in entity.properties.items() if value is not None},
        },
    )


def append_edge_result(result: DatabaseScanResult, edge_result: EdgeBuildResult) -> None:
    if edge_result.edge is not None:
        result.edges.append(edge_result.edge)
    if edge_result.error is not None:
        result.add_error(
            edge_result.error.to_message(),
            source_name=edge_result.error.source_name,
            metadata_source=edge_result.error.metadata_source,
        )


def build_entity_index(entities: list[EntityFact]) -> dict[tuple[str | None, str], list[EntityFact]]:
    lookup: dict[tuple[str | None, str], list[EntityFact]] = {}
    for entity in entities:
        keys = {entity.name, *entity.aliases}
        full_name = entity.properties.get("full_name")
        if isinstance(full_name, str):
            keys.add(full_name)
        schema = entity.properties.get("schema")
        if isinstance(schema, str) and schema:
            keys.add(f"{schema}.{entity.name}")
        for key in keys:
            normalized = normalize_resolution_key(key)
            lookup.setdefault((entity.entity_type, normalized), []).append(entity)
            lookup.setdefault((None, normalized), []).append(entity)
    return lookup


def find_entity(
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
    target_type: str | None,
    target_name: str,
) -> EntityMatch:
    normalized_target = normalize_resolution_key(target_name)
    candidates: dict[EntityReference, EntityFact] = {}
    for entity_type in database_resolution_entity_types(target_type):
        for candidate in entity_index.get((entity_type, normalized_target), []):
            candidates[candidate.reference] = candidate
    if not candidates:
        for candidate in entity_index.get((None, normalized_target), []):
            candidates[candidate.reference] = candidate
    if len(candidates) == 1:
        return EntityMatch(entity=next(iter(candidates.values())))
    return EntityMatch(candidates=tuple(candidates.values()))


def normalize_resolution_key(value: str) -> str:
    return value.strip().strip("[]`\"'").lower()


def database_resolution_entity_types(target_type: str | None) -> list[str | None]:
    if target_type == "sql_object":
        return ["sql_table", "sql_view", "sql_function", "sql_trigger", "stored_procedure"]
    if target_type:
        return [target_type]
    return [None]
