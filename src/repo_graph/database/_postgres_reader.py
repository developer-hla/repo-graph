"""PostgreSQL catalog metadata reader."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import (
    DEFAULT_DATABASE_MAX_METADATA_ROWS,
    DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS,
)
from repo_graph.database._models import (
    DatabaseSourceRequest,
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresMetadata,
    PostgresMetadataReadResult,
    PostgresObjectRow,
    PostgresTriggerRow,
)
from repo_graph.database._postgres_filters import postgres_class_relkind_filter, postgres_proc_kind_filter
from repo_graph.database._postgres_queries import (
    postgres_class_objects_query,
    postgres_dependencies_query,
    postgres_foreign_keys_query,
    postgres_proc_objects_query,
    postgres_triggers_query,
)
from repo_graph.database._postgres_row_mapping import (
    postgres_class_object_groups,
    postgres_dependency_row,
    postgres_foreign_key_row,
    postgres_proc_object_groups,
    postgres_trigger_row,
)
from repo_graph.database._reader_common import (
    MetadataReadBudget,
    fetch_postgres_rows,
    include_database_object_type,
    include_database_object_type_or_dependency,
    set_postgres_statement_timeout,
)


def read_postgres_metadata(connection: Any, request: DatabaseSourceRequest) -> PostgresMetadataReadResult:
    """Read bounded PostgreSQL catalog metadata from an open connection."""

    budget = MetadataReadBudget(
        limit=request.max_metadata_rows or DEFAULT_DATABASE_MAX_METADATA_ROWS,
        engine_label="PostgreSQL",
    )
    cursor = connection.cursor()
    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    set_postgres_statement_timeout(cursor, timeout)

    tables: list[PostgresObjectRow] = []
    views: list[PostgresObjectRow] = []
    materialized_views: list[PostgresObjectRow] = []
    class_relkinds = postgres_class_relkind_filter(request.include_object_types)
    if class_relkinds and budget.has_remaining:
        rows = fetch_postgres_rows(
            cursor,
            postgres_class_objects_query(budget.remaining, request.schemas, class_relkinds),
            (*class_relkinds, *request.schemas),
            budget,
            "pg_class",
        )
        object_groups = postgres_class_object_groups(rows)
        tables.extend(object_groups.tables)
        views.extend(object_groups.views)
        materialized_views.extend(object_groups.materialized_views)

    functions: list[PostgresObjectRow] = []
    procedures: list[PostgresObjectRow] = []
    proc_kinds = postgres_proc_kind_filter(request.include_object_types)
    if proc_kinds and budget.has_remaining:
        rows = fetch_postgres_rows(
            cursor,
            postgres_proc_objects_query(budget.remaining, request.schemas, proc_kinds),
            (*proc_kinds, *request.schemas),
            budget,
            "pg_proc",
        )
        object_groups = postgres_proc_object_groups(rows)
        functions.extend(object_groups.functions)
        procedures.extend(object_groups.procedures)

    foreign_keys: list[PostgresForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            postgres_foreign_key_row(row)
            for row in fetch_postgres_rows(
                cursor,
                postgres_foreign_keys_query(budget.remaining, request.schemas),
                request.schemas,
                budget,
                "pg_constraint",
            )
        )

    triggers: list[PostgresTriggerRow] = []
    if include_database_object_type_or_dependency(request.include_object_types, "trigger") and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_triggers_query(budget.remaining, request.schemas),
            request.schemas,
            budget,
            "pg_trigger",
        ):
            triggers.append(postgres_trigger_row(row))

    dependencies: list[PostgresDependencyRow] = []
    if include_database_object_type(request.include_object_types, "dependency") and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_dependencies_query(budget.remaining, request.schemas),
            (*request.schemas, *request.schemas),
            budget,
            "pg_depend",
        ):
            dependencies.append(postgres_dependency_row(row))

    return PostgresMetadataReadResult(
        metadata=PostgresMetadata(
            tables=tuple(tables),
            views=tuple(views),
            materialized_views=tuple(materialized_views),
            functions=tuple(functions),
            procedures=tuple(procedures),
            triggers=tuple(triggers),
            foreign_keys=tuple(foreign_keys),
            dependencies=tuple(dependencies),
        ),
        errors=budget.errors,
    )
