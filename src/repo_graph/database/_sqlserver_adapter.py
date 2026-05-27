"""SQL Server metadata fact adapter."""

from __future__ import annotations

from dataclasses import dataclass

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
from repo_graph.database._constants import (
    EXECUTE_DEPENDENCY_TYPES,
    SQLSERVER_ENGINE,
    SQLSERVER_METADATA_PARSER,
    SQLSERVER_OBJECT_METADATA_SOURCES,
)
from repo_graph.database._metadata_edges import (
    database_dependency_metadata_edge,
    database_dependency_target_type,
    database_foreign_key_metadata_edge,
)
from repo_graph.database._models import (
    DatabaseScanResult,
    EdgeBuildResult,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerObjectRow,
    SqlServerTriggerRow,
)
from repo_graph.database._naming import (
    graph_entity_type,
    metadata_identity_key,
    normalize_metadata_value,
    required_text,
    sqlserver_full_name,
)
from repo_graph.extraction.facts import EntityFact, EntityReference


@dataclass(frozen=True)
class SqlServerMetadataAdapter:
    """Pure SQL Server metadata adapter."""

    engine: str = SQLSERVER_ENGINE
    metadata_parser: str = SQLSERVER_METADATA_PARSER

    def scan_metadata(self, source_name: str, metadata: object) -> DatabaseScanResult:
        if not isinstance(metadata, SqlServerMetadata):
            raise TypeError("SQL Server metadata adapter requires SqlServerMetadata.")
        return scan_sqlserver_metadata(source_name, metadata)


def scan_sqlserver_metadata(source_name: str, metadata: SqlServerMetadata) -> DatabaseScanResult:
    """Convert SQL Server catalog metadata rows into typed facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseScanResult()

    entities_by_ref: dict[EntityReference, EntityFact] = {}
    for entity_type, rows in sqlserver_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_ref,
                sqlserver_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=SQLSERVER_OBJECT_METADATA_SOURCES[entity_type],
                ),
            )
    for row in metadata.triggers:
        add_entity(entities_by_ref, sqlserver_trigger_entity(source_name, row))

    result.entities = list(entities_by_ref.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = foreign_key_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.triggers:
        edge_result = sqlserver_trigger_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.dependencies:
        edge_result = dependency_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    return result


def sqlserver_object_groups(
    metadata: SqlServerMetadata,
) -> tuple[tuple[str, tuple[SqlServerObjectRow, ...]], ...]:
    return (
        ("sql_table", metadata.tables),
        ("sql_view", metadata.views),
        ("stored_procedure", metadata.stored_procedures),
        ("sql_function", metadata.functions),
    )


def sqlserver_object_entity(
    source_name: str,
    entity_type: str,
    row: SqlServerObjectRow,
    metadata_source: str,
) -> EntityFact:
    return database_object_entity(
        source_name=source_name,
        database_engine=SQLSERVER_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
    )


def sqlserver_trigger_entity(source_name: str, row: SqlServerTriggerRow) -> EntityFact:
    return database_trigger_entity(
        source_name=source_name,
        database_engine=SQLSERVER_ENGINE,
        schema=row.schema,
        name=row.name,
        table_schema=row.table_schema,
        table=row.table,
        metadata_source="sys.triggers",
        events=row.events,
        is_enabled=None if row.is_disabled is None else not row.is_disabled,
    )


def foreign_key_edge(
    source_name: str,
    row: SqlServerForeignKeyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = sqlserver_full_name(row.schema, row.table)
    target_full_name = sqlserver_full_name(row.referenced_schema, row.referenced_table)
    source_match = find_entity(entity_index, "sql_table", source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="SQL Server",
                source_name=source_name,
                metadata_source="sys.foreign_keys",
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
            metadata_source="sys.foreign_keys",
            identity_key=metadata_identity_key("foreign_key", source_full_name, target_full_name, row.name),
            database_engine=SQLSERVER_ENGINE,
            parser=SQLSERVER_METADATA_PARSER,
            constraint_name=row.name,
        )
    )


def sqlserver_trigger_edge(
    source_name: str,
    row: SqlServerTriggerRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    return trigger_edge(
        engine_label="SQL Server",
        source_name=source_name,
        metadata_source="sys.triggers",
        database_engine=SQLSERVER_ENGINE,
        parser=SQLSERVER_METADATA_PARSER,
        trigger_schema=row.schema,
        trigger_name=row.name,
        table_schema=row.table_schema,
        table_name=row.table,
        events=row.events,
        is_enabled=None if row.is_disabled is None else not row.is_disabled,
        entity_index=entity_index,
    )


def dependency_edge(
    source_name: str,
    row: SqlServerDependencyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = sqlserver_full_name(row.from_schema, row.from_name)
    target_full_name = sqlserver_full_name(row.to_schema, row.to_name)
    source_match = find_entity(entity_index, graph_entity_type(row.from_type, "SQL Server"), source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="SQL Server",
                source_name=source_name,
                metadata_source="sys.sql_expression_dependencies",
                relationship_name="dependency",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    dependency_type = normalize_metadata_value(row.dependency_type)
    is_execute_dependency = dependency_type in EXECUTE_DEPENDENCY_TYPES
    target_type = database_dependency_target_type(graph_entity_type(row.to_type, "SQL Server"), is_execute_dependency)
    return EdgeBuildResult(
        edge=database_dependency_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, target_type, target_full_name),
            target_name=target_full_name,
            target_type=target_type,
            source_name=source_name,
            metadata_source="sys.sql_expression_dependencies",
            identity_key=metadata_identity_key(
                "dependency",
                source_full_name,
                target_full_name,
                row.dependency_type,
                row.name,
            ),
            database_engine=SQLSERVER_ENGINE,
            parser=SQLSERVER_METADATA_PARSER,
            is_execute_dependency=is_execute_dependency,
            reference_operation="MODULE_REFERENCE",
            extra_properties={
                "dependency_name": row.name,
                "dependency_type": row.dependency_type,
            },
        )
    )
