"""SQL Server catalog metadata reader."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import (
    DEFAULT_DATABASE_MAX_METADATA_ROWS,
    DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS,
    SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE,
)
from repo_graph.database._models import (
    DatabaseSourceRequest,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerMetadataReadResult,
    SqlServerObjectRow,
    SqlServerTriggerRow,
)
from repo_graph.database._reader_common import (
    MetadataReadBudget,
    fetch_sqlserver_rows,
    include_database_object_type,
    include_database_object_type_or_dependency,
    normalize_trigger_event,
    optional_row_text,
    row_bool,
    row_text,
    safe_sql_limit,
    set_cursor_timeout,
    sqlserver_catalog_object_type,
)


def read_sqlserver_metadata(connection: Any, request: DatabaseSourceRequest) -> SqlServerMetadataReadResult:
    """Read bounded SQL Server catalog metadata from an open connection."""

    budget = MetadataReadBudget(
        limit=request.max_metadata_rows or DEFAULT_DATABASE_MAX_METADATA_ROWS,
        engine_label="SQL Server",
    )
    cursor = connection.cursor()
    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    set_cursor_timeout(cursor, timeout)

    tables: list[SqlServerObjectRow] = []
    views: list[SqlServerObjectRow] = []
    stored_procedures: list[SqlServerObjectRow] = []
    functions: list[SqlServerObjectRow] = []
    object_types = sqlserver_object_type_filter(request.include_object_types)
    if object_types and budget.has_remaining:
        for row in fetch_sqlserver_rows(
            cursor,
            sqlserver_objects_query(budget.remaining, request.schemas, object_types),
            (*object_types, *request.schemas),
            budget,
            "sys.objects",
        ):
            object_row = SqlServerObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match sqlserver_catalog_object_type(row_text(row, "object_type")):
                case "sql_table":
                    tables.append(object_row)
                case "sql_view":
                    views.append(object_row)
                case "stored_procedure":
                    stored_procedures.append(object_row)
                case "sql_function":
                    functions.append(object_row)

    foreign_keys: list[SqlServerForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            SqlServerForeignKeyRow(
                schema=row_text(row, "schema_name"),
                table=row_text(row, "table_name"),
                referenced_schema=row_text(row, "referenced_schema_name"),
                referenced_table=row_text(row, "referenced_table_name"),
                name=optional_row_text(row, "constraint_name"),
            )
            for row in fetch_sqlserver_rows(
                cursor,
                sqlserver_foreign_keys_query(budget.remaining, request.schemas),
                request.schemas,
                budget,
                "sys.foreign_keys",
            )
        )

    triggers: list[SqlServerTriggerRow] = []
    if include_database_object_type_or_dependency(request.include_object_types, "trigger") and budget.has_remaining:
        triggers.extend(
            sqlserver_trigger_rows(
                fetch_sqlserver_rows(
                    cursor,
                    sqlserver_triggers_query(budget.remaining, request.schemas),
                    request.schemas,
                    budget,
                    "sys.triggers",
                )
            )
        )

    dependencies: list[SqlServerDependencyRow] = []
    if include_database_object_type(request.include_object_types, "dependency") and budget.has_remaining:
        for row in fetch_sqlserver_rows(
            cursor,
            sqlserver_dependencies_query(budget.remaining, request.schemas),
            request.schemas,
            budget,
            "sys.sql_expression_dependencies",
        ):
            from_schema = row_text(row, "from_schema_name")
            dependencies.append(
                SqlServerDependencyRow(
                    from_schema=from_schema,
                    from_name=row_text(row, "from_object_name"),
                    from_type=sqlserver_catalog_object_type(row_text(row, "from_object_type")),
                    to_schema=optional_row_text(row, "to_schema_name") or from_schema,
                    to_name=row_text(row, "to_object_name"),
                    to_type=sqlserver_catalog_object_type(optional_row_text(row, "to_object_type")),
                    dependency_type="module_reference",
                    name=optional_row_text(row, "dependency_name"),
                )
            )

    return SqlServerMetadataReadResult(
        metadata=SqlServerMetadata(
            tables=tuple(tables),
            views=tuple(views),
            stored_procedures=tuple(stored_procedures),
            functions=tuple(functions),
            triggers=tuple(triggers),
            foreign_keys=tuple(foreign_keys),
            dependencies=tuple(dependencies),
        ),
        errors=budget.errors,
    )


def sqlserver_trigger_rows(rows: list[Any]) -> list[SqlServerTriggerRow]:
    triggers: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            row_text(row, "schema_name"),
            row_text(row, "trigger_name"),
            row_text(row, "table_schema_name"),
            row_text(row, "table_name"),
        )
        trigger = triggers.setdefault(
            key,
            {
                "events": set(),
                "is_disabled": row_bool(row, "is_disabled"),
            },
        )
        event_name = optional_row_text(row, "event_name")
        if event_name:
            trigger["events"].add(normalize_trigger_event(event_name))

    return [
        SqlServerTriggerRow(
            schema=schema,
            name=name,
            table_schema=table_schema,
            table=table,
            events=tuple(sorted(trigger["events"])),
            is_disabled=bool(trigger["is_disabled"]),
        )
        for (schema, name, table_schema, table), trigger in triggers.items()
    ]


def sqlserver_objects_query(limit: int, schemas: tuple[str, ...], object_types: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("s", schemas)
    object_type_filter = sqlserver_in_filter("o.type", len(object_types))
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  s.name AS schema_name,
  o.name AS object_name,
  o.type AS object_type
FROM sys.objects AS o
JOIN sys.schemas AS s ON o.schema_id = s.schema_id
WHERE o.is_ms_shipped = 0
  AND {object_type_filter}
  {schema_filter}
ORDER BY s.name, o.name
"""


def sqlserver_foreign_keys_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("ps", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  ps.name AS schema_name,
  pt.name AS table_name,
  rs.name AS referenced_schema_name,
  rt.name AS referenced_table_name,
  fk.name AS constraint_name
FROM sys.foreign_keys AS fk
JOIN sys.tables AS pt ON fk.parent_object_id = pt.object_id
JOIN sys.schemas AS ps ON pt.schema_id = ps.schema_id
JOIN sys.tables AS rt ON fk.referenced_object_id = rt.object_id
JOIN sys.schemas AS rs ON rt.schema_id = rs.schema_id
WHERE pt.is_ms_shipped = 0
  AND rt.is_ms_shipped = 0
  {schema_filter}
ORDER BY ps.name, pt.name, fk.name
"""


def sqlserver_triggers_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("parent_schema", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  trigger_schema.name AS schema_name,
  trigger_object.name AS trigger_name,
  parent_schema.name AS table_schema_name,
  parent_table.name AS table_name,
  trigger_event.type_desc AS event_name,
  trigger_definition.is_disabled AS is_disabled
FROM sys.triggers AS trigger_definition
JOIN sys.objects AS trigger_object ON trigger_definition.object_id = trigger_object.object_id
JOIN sys.schemas AS trigger_schema ON trigger_object.schema_id = trigger_schema.schema_id
JOIN sys.tables AS parent_table ON trigger_definition.parent_id = parent_table.object_id
JOIN sys.schemas AS parent_schema ON parent_table.schema_id = parent_schema.schema_id
LEFT JOIN sys.trigger_events AS trigger_event ON trigger_definition.object_id = trigger_event.object_id
WHERE trigger_definition.parent_class = 1
  AND trigger_definition.is_ms_shipped = 0
  AND parent_table.is_ms_shipped = 0
  {schema_filter}
ORDER BY trigger_schema.name, trigger_object.name, trigger_event.type_desc
"""


def sqlserver_dependencies_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("referencing_schema", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  referencing_schema.name AS from_schema_name,
  referencing_object.name AS from_object_name,
  referencing_object.type AS from_object_type,
  COALESCE(referenced_schema.name, d.referenced_schema_name) AS to_schema_name,
  COALESCE(referenced_object.name, d.referenced_entity_name) AS to_object_name,
  referenced_object.type AS to_object_type,
  d.referenced_class_desc AS dependency_name
FROM sys.sql_expression_dependencies AS d
JOIN sys.objects AS referencing_object ON d.referencing_id = referencing_object.object_id
JOIN sys.schemas AS referencing_schema ON referencing_object.schema_id = referencing_schema.schema_id
LEFT JOIN sys.objects AS referenced_object ON d.referenced_id = referenced_object.object_id
LEFT JOIN sys.schemas AS referenced_schema ON referenced_object.schema_id = referenced_schema.schema_id
WHERE referencing_object.is_ms_shipped = 0
  AND d.referenced_entity_name IS NOT NULL
  {schema_filter}
ORDER BY referencing_schema.name, referencing_object.name, d.referenced_entity_name
"""


def sqlserver_schema_filter(schema_alias: str, schemas: tuple[str, ...]) -> str:
    if not schemas:
        return ""
    return f"AND {schema_alias}.name IN ({', '.join('?' for _schema in schemas)})"


def sqlserver_in_filter(column_name: str, count: int) -> str:
    return f"{column_name} IN ({', '.join('?' for _index in range(count))})"


def sqlserver_object_type_filter(include_object_types: tuple[str, ...]) -> tuple[str, ...]:
    requested = list(include_object_types or tuple(SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE))
    if "foreign_key" in requested and "table" not in requested:
        requested.append("table")
    if "dependency" in requested:
        requested.extend(
            object_type for object_type in SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE if object_type not in requested
        )
    object_types: list[str] = []
    for include_type in requested:
        object_types.extend(SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE.get(include_type, ()))
    return tuple(dict.fromkeys(object_types))
