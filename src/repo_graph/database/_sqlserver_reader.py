"""SQL Server catalog metadata reader."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import (
    DEFAULT_DATABASE_MAX_METADATA_ROWS,
    DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS,
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
    set_cursor_timeout,
)
from repo_graph.database._sqlserver_filters import sqlserver_object_type_filter
from repo_graph.database._sqlserver_queries import (
    sqlserver_dependencies_query,
    sqlserver_foreign_keys_query,
    sqlserver_objects_query,
    sqlserver_triggers_query,
)
from repo_graph.database._sqlserver_row_mapping import (
    sqlserver_dependency_row,
    sqlserver_foreign_key_row,
    sqlserver_object_groups,
    sqlserver_trigger_rows,
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
        rows = fetch_sqlserver_rows(
            cursor,
            sqlserver_objects_query(budget.remaining, request.schemas, object_types),
            (*object_types, *request.schemas),
            budget,
            "sys.objects",
        )
        object_groups = sqlserver_object_groups(rows)
        tables.extend(object_groups.tables)
        views.extend(object_groups.views)
        stored_procedures.extend(object_groups.stored_procedures)
        functions.extend(object_groups.functions)

    foreign_keys: list[SqlServerForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            sqlserver_foreign_key_row(row)
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
            dependencies.append(sqlserver_dependency_row(row))

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
