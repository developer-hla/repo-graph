"""PostgreSQL metadata fact adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repo_graph.database._adapter_common import (
    add_entity,
    append_edge_result,
    build_entity_index,
    database_object_entity,
    database_trigger_entity,
    find_entity,
    missing_source_error,
    trigger_edge,
)
from repo_graph.database._constants import EXECUTE_DEPENDENCY_TYPES, POSTGRES_ENGINE, POSTGRES_METADATA_PARSER
from repo_graph.database._metadata_edges import (
    database_dependency_metadata_edge,
    database_dependency_target_type,
    database_foreign_key_metadata_edge,
)
from repo_graph.database._models import (
    DatabaseScanResult,
    EdgeBuildResult,
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresMetadata,
    PostgresObjectRow,
    PostgresTriggerRow,
)
from repo_graph.database._naming import (
    database_full_name,
    graph_entity_type,
    metadata_identity_key,
    normalize_metadata_value,
    postgres_full_name,
    required_text,
    trigger_source_schema,
)
from repo_graph.extraction.facts import EntityFact, EntityReference


@dataclass(frozen=True)
class PostgresMetadataAdapter:
    """Pure PostgreSQL metadata adapter."""

    engine: str = POSTGRES_ENGINE
    metadata_parser: str = POSTGRES_METADATA_PARSER

    def scan_metadata(self, source_name: str, metadata: object) -> DatabaseScanResult:
        if not isinstance(metadata, PostgresMetadata):
            raise TypeError("PostgreSQL metadata adapter requires PostgresMetadata.")
        return scan_postgres_metadata(source_name, metadata)


def scan_postgres_metadata(source_name: str, metadata: PostgresMetadata) -> DatabaseScanResult:
    """Convert PostgreSQL catalog metadata rows into typed facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseScanResult()

    entities_by_ref: dict[EntityReference, EntityFact] = {}
    for entity_type, rows, metadata_source, extra_properties in postgres_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_ref,
                postgres_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=metadata_source,
                    extra_properties=extra_properties,
                ),
            )
    for row in metadata.triggers:
        add_entity(entities_by_ref, postgres_trigger_entity(source_name, row))

    result.entities = list(entities_by_ref.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = postgres_foreign_key_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.triggers:
        edge_result = postgres_trigger_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)
        trigger_function_dependency = postgres_trigger_function_dependency(row)
        if trigger_function_dependency is not None:
            append_edge_result(result, postgres_dependency_edge(source_name, trigger_function_dependency, entity_index))

    for row in metadata.dependencies:
        edge_result = postgres_dependency_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    return result


def postgres_object_groups(
    metadata: PostgresMetadata,
) -> tuple[tuple[str, tuple[PostgresObjectRow, ...], str, dict[str, Any]], ...]:
    return (
        ("sql_table", metadata.tables, "pg_class", {}),
        ("sql_view", metadata.views, "pg_class", {"postgres_relkind": "view"}),
        ("sql_view", metadata.materialized_views, "pg_class", {"postgres_relkind": "materialized_view"}),
        ("stored_procedure", metadata.procedures, "pg_proc", {}),
        ("sql_function", metadata.functions, "pg_proc", {}),
    )


def postgres_object_entity(
    source_name: str,
    entity_type: str,
    row: PostgresObjectRow,
    metadata_source: str,
    extra_properties: dict[str, Any],
) -> EntityFact:
    return database_object_entity(
        source_name=source_name,
        database_engine=POSTGRES_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
        extra_properties=extra_properties,
    )


def postgres_trigger_entity(source_name: str, row: PostgresTriggerRow) -> EntityFact:
    return database_trigger_entity(
        source_name=source_name,
        database_engine=POSTGRES_ENGINE,
        schema=row.schema,
        name=row.name,
        table_schema=row.table_schema,
        table=row.table,
        metadata_source="pg_trigger",
        events=row.events,
        is_enabled=row.is_enabled,
        extra_properties={
            "trigger_function": (
                database_full_name(row.function_schema, row.function_name)
                if row.function_schema and row.function_name
                else None
            )
        },
    )


def postgres_trigger_edge(
    source_name: str,
    row: PostgresTriggerRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    return trigger_edge(
        engine_label="PostgreSQL",
        source_name=source_name,
        metadata_source="pg_trigger",
        database_engine=POSTGRES_ENGINE,
        parser=POSTGRES_METADATA_PARSER,
        trigger_schema=row.schema,
        trigger_name=row.name,
        table_schema=row.table_schema,
        table_name=row.table,
        events=row.events,
        is_enabled=row.is_enabled,
        entity_index=entity_index,
    )


def postgres_trigger_function_dependency(row: PostgresTriggerRow) -> PostgresDependencyRow | None:
    if not row.function_schema or not row.function_name:
        return None
    return PostgresDependencyRow(
        from_schema=trigger_source_schema(row.table_schema, row.table),
        from_name=row.name,
        from_type="trigger",
        to_schema=row.function_schema,
        to_name=row.function_name,
        to_type="function",
        dependency_type="execute",
        name=row.name,
    )


def postgres_foreign_key_edge(
    source_name: str,
    row: PostgresForeignKeyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = postgres_full_name(row.schema, row.table)
    target_full_name = postgres_full_name(row.referenced_schema, row.referenced_table)
    source_match = find_entity(entity_index, "sql_table", source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="PostgreSQL",
                source_name=source_name,
                metadata_source="pg_constraint",
                relationship_name="foreign key",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    return EdgeBuildResult(
        edge=database_foreign_key_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, "sql_table", target_full_name),
            target_name=target_full_name,
            source_name=source_name,
            metadata_source="pg_constraint",
            identity_key=metadata_identity_key("foreign_key", source_full_name, target_full_name, row.name),
            database_engine=POSTGRES_ENGINE,
            parser=POSTGRES_METADATA_PARSER,
            constraint_name=row.name,
        )
    )


def postgres_dependency_edge(
    source_name: str,
    row: PostgresDependencyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = postgres_full_name(row.from_schema, row.from_name)
    target_full_name = postgres_full_name(row.to_schema, row.to_name)
    source_match = find_entity(entity_index, graph_entity_type(row.from_type, "PostgreSQL"), source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="PostgreSQL",
                source_name=source_name,
                metadata_source="pg_depend",
                relationship_name="dependency",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    dependency_type = normalize_metadata_value(row.dependency_type)
    is_execute_dependency = dependency_type in EXECUTE_DEPENDENCY_TYPES
    target_type = database_dependency_target_type(graph_entity_type(row.to_type, "PostgreSQL"), is_execute_dependency)
    return EdgeBuildResult(
        edge=database_dependency_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, target_type, target_full_name),
            target_name=target_full_name,
            target_type=target_type,
            source_name=source_name,
            metadata_source="pg_depend",
            identity_key=metadata_identity_key(
                "dependency",
                source_full_name,
                target_full_name,
                row.dependency_type,
                row.name,
            ),
            database_engine=POSTGRES_ENGINE,
            parser=POSTGRES_METADATA_PARSER,
            is_execute_dependency=is_execute_dependency,
            reference_operation="OBJECT_DEPENDENCY",
            extra_properties={
                "dependency_name": row.name,
                "dependency_type": row.dependency_type,
            },
        )
    )
