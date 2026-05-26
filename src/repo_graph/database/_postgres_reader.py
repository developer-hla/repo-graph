"""PostgreSQL catalog metadata reader."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import (
    DEFAULT_DATABASE_MAX_METADATA_ROWS,
    DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS,
    POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE,
    POSTGRES_DEFAULT_INCLUDE_OBJECT_TYPES,
    POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE,
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
from repo_graph.database._naming import normalize_metadata_value
from repo_graph.database._reader_common import (
    MetadataReadBudget,
    fetch_postgres_rows,
    include_database_object_type,
    include_database_object_type_or_dependency,
    optional_row_text,
    postgres_catalog_object_type,
    postgres_trigger_events,
    row_bool,
    row_text,
    safe_sql_limit,
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
        for row in fetch_postgres_rows(
            cursor,
            postgres_class_objects_query(budget.remaining, request.schemas, class_relkinds),
            (*class_relkinds, *request.schemas),
            budget,
            "pg_class",
        ):
            object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match normalize_metadata_value(row_text(row, "object_type")):
                case "table":
                    tables.append(object_row)
                case "view":
                    views.append(object_row)
                case "materialized_view":
                    materialized_views.append(object_row)

    functions: list[PostgresObjectRow] = []
    procedures: list[PostgresObjectRow] = []
    proc_kinds = postgres_proc_kind_filter(request.include_object_types)
    if proc_kinds and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_proc_objects_query(budget.remaining, request.schemas, proc_kinds),
            (*proc_kinds, *request.schemas),
            budget,
            "pg_proc",
        ):
            object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match normalize_metadata_value(row_text(row, "object_type")):
                case "function":
                    functions.append(object_row)
                case "procedure":
                    procedures.append(object_row)

    foreign_keys: list[PostgresForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            PostgresForeignKeyRow(
                schema=row_text(row, "schema_name"),
                table=row_text(row, "table_name"),
                referenced_schema=row_text(row, "referenced_schema_name"),
                referenced_table=row_text(row, "referenced_table_name"),
                name=optional_row_text(row, "constraint_name"),
            )
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
            trigger = PostgresTriggerRow(
                schema=row_text(row, "schema_name"),
                name=row_text(row, "trigger_name"),
                table_schema=row_text(row, "table_schema_name"),
                table=row_text(row, "table_name"),
                events=postgres_trigger_events(row),
                is_enabled=not row_bool(row, "is_disabled"),
                function_schema=optional_row_text(row, "function_schema_name"),
                function_name=optional_row_text(row, "function_name"),
            )
            triggers.append(trigger)

    dependencies: list[PostgresDependencyRow] = []
    if include_database_object_type(request.include_object_types, "dependency") and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_dependencies_query(budget.remaining, request.schemas),
            (*request.schemas, *request.schemas),
            budget,
            "pg_depend",
        ):
            dependencies.append(
                PostgresDependencyRow(
                    from_schema=row_text(row, "from_schema_name"),
                    from_name=row_text(row, "from_object_name"),
                    from_type=postgres_catalog_object_type(row_text(row, "from_object_type")),
                    to_schema=row_text(row, "to_schema_name"),
                    to_name=row_text(row, "to_object_name"),
                    to_type=postgres_catalog_object_type(row_text(row, "to_object_type")),
                    dependency_type=optional_row_text(row, "dependency_type") or "object_dependency",
                    name=optional_row_text(row, "dependency_name"),
                )
            )

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


def postgres_class_objects_query(limit: int, schemas: tuple[str, ...], relkinds: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    relkind_filter = postgres_in_filter("c.relkind", len(relkinds))
    return f"""
SELECT
  n.nspname AS schema_name,
  c.relname AS object_name,
  CASE c.relkind
    WHEN 'm' THEN 'materialized_view'
    WHEN 'v' THEN 'view'
    ELSE 'table'
  END AS object_type
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE {relkind_filter}
  {schema_filter}
ORDER BY n.nspname, c.relname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_proc_objects_query(limit: int, schemas: tuple[str, ...], prokinds: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    prokind_filter = postgres_in_filter("p.prokind", len(prokinds))
    return f"""
SELECT
  n.nspname AS schema_name,
  p.proname AS object_name,
  CASE p.prokind
    WHEN 'p' THEN 'procedure'
    ELSE 'function'
  END AS object_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
WHERE {prokind_filter}
  {schema_filter}
ORDER BY n.nspname, p.proname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_foreign_keys_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    return f"""
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  rn.nspname AS referenced_schema_name,
  rc.relname AS referenced_table_name,
  con.conname AS constraint_name
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_class AS rc ON rc.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace
WHERE con.contype = 'f'
  {schema_filter}
ORDER BY n.nspname, c.relname, con.conname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_triggers_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("table_schema", schemas)
    return f"""
SELECT
  table_schema.nspname AS schema_name,
  trigger_definition.tgname AS trigger_name,
  table_schema.nspname AS table_schema_name,
  parent_table.relname AS table_name,
  ((trigger_definition.tgtype::int & 4) <> 0) AS fires_insert,
  ((trigger_definition.tgtype::int & 8) <> 0) AS fires_delete,
  ((trigger_definition.tgtype::int & 16) <> 0) AS fires_update,
  ((trigger_definition.tgtype::int & 32) <> 0) AS fires_truncate,
  trigger_definition.tgenabled = 'D' AS is_disabled,
  function_schema.nspname AS function_schema_name,
  trigger_function.proname AS function_name
FROM pg_catalog.pg_trigger AS trigger_definition
JOIN pg_catalog.pg_class AS parent_table ON parent_table.oid = trigger_definition.tgrelid
JOIN pg_catalog.pg_namespace AS table_schema ON table_schema.oid = parent_table.relnamespace
JOIN pg_catalog.pg_proc AS trigger_function ON trigger_function.oid = trigger_definition.tgfoid
JOIN pg_catalog.pg_namespace AS function_schema ON function_schema.oid = trigger_function.pronamespace
WHERE NOT trigger_definition.tgisinternal
  {schema_filter}
ORDER BY table_schema.nspname, parent_table.relname, trigger_definition.tgname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_dependencies_query(limit: int, schemas: tuple[str, ...]) -> str:
    view_schema_filter = postgres_schema_filter("n", schemas)
    routine_schema_filter = postgres_schema_filter("pn", schemas)
    return f"""
SELECT *
FROM (
  SELECT
    n.nspname AS from_schema_name,
    v.relname AS from_object_name,
    CASE v.relkind
      WHEN 'm' THEN 'materialized_view'
      ELSE 'view'
    END AS from_object_type,
    rn.nspname AS to_schema_name,
    rc.relname AS to_object_name,
    CASE rc.relkind
      WHEN 'm' THEN 'materialized_view'
      WHEN 'v' THEN 'view'
      ELSE 'table'
    END AS to_object_type,
    dep.deptype::text AS dependency_name,
    'object_dependency' AS dependency_type
  FROM pg_catalog.pg_rewrite AS rw
  JOIN pg_catalog.pg_class AS v ON v.oid = rw.ev_class
  JOIN pg_catalog.pg_namespace AS n ON n.oid = v.relnamespace
  JOIN pg_catalog.pg_depend AS dep ON dep.objid = rw.oid
  JOIN pg_catalog.pg_class AS rc ON rc.oid = dep.refobjid
  JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace
  WHERE v.relkind IN ('m', 'v')
    AND dep.classid = 'pg_rewrite'::regclass
    AND dep.refclassid = 'pg_class'::regclass
    AND dep.deptype IN ('a', 'n')
    AND rc.oid <> v.oid
    {view_schema_filter}
    {postgres_user_schema_filter("rn")}

  UNION ALL

  SELECT
    pn.nspname AS from_schema_name,
    p.proname AS from_object_name,
    CASE p.prokind
      WHEN 'p' THEN 'procedure'
      ELSE 'function'
    END AS from_object_type,
    rpn.nspname AS to_schema_name,
    rp.proname AS to_object_name,
    CASE rp.prokind
      WHEN 'p' THEN 'procedure'
      ELSE 'function'
    END AS to_object_type,
    dep.deptype::text AS dependency_name,
    'object_dependency' AS dependency_type
  FROM pg_catalog.pg_depend AS dep
  JOIN pg_catalog.pg_proc AS p ON p.oid = dep.objid
  JOIN pg_catalog.pg_namespace AS pn ON pn.oid = p.pronamespace
  JOIN pg_catalog.pg_proc AS rp ON rp.oid = dep.refobjid
  JOIN pg_catalog.pg_namespace AS rpn ON rpn.oid = rp.pronamespace
  WHERE dep.classid = 'pg_proc'::regclass
    AND dep.refclassid = 'pg_proc'::regclass
    AND dep.deptype IN ('a', 'n')
    AND rp.oid <> p.oid
    {routine_schema_filter}
    {postgres_user_schema_filter("rpn")}
) AS dependencies
ORDER BY from_schema_name, from_object_name, to_schema_name, to_object_name
LIMIT {safe_sql_limit(limit)}
"""


def postgres_schema_filter(schema_alias: str, schemas: tuple[str, ...]) -> str:
    if schemas:
        return f"AND {schema_alias}.nspname IN ({', '.join('%s' for _schema in schemas)})"
    return postgres_user_schema_filter(schema_alias)


def postgres_user_schema_filter(schema_alias: str) -> str:
    return (
        f"AND {schema_alias}.nspname NOT IN ('information_schema', 'pg_catalog') "
        f"AND {schema_alias}.nspname NOT LIKE 'pg_toast%'"
    )


def postgres_in_filter(column_name: str, count: int) -> str:
    return f"{column_name} IN ({', '.join('%s' for _index in range(count))})"


def postgres_class_relkind_filter(include_object_types: tuple[str, ...]) -> tuple[str, ...]:
    requested = postgres_requested_object_types(include_object_types)
    relkinds: list[str] = []
    for include_type in requested:
        relkinds.extend(POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE.get(include_type, ()))
    return tuple(dict.fromkeys(relkinds))


def postgres_proc_kind_filter(include_object_types: tuple[str, ...]) -> tuple[str, ...]:
    requested = postgres_requested_object_types(include_object_types)
    prokinds: list[str] = []
    for include_type in requested:
        prokinds.extend(POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE.get(include_type, ()))
    return tuple(dict.fromkeys(prokinds))


def postgres_requested_object_types(include_object_types: tuple[str, ...]) -> list[str]:
    requested = list(include_object_types or POSTGRES_DEFAULT_INCLUDE_OBJECT_TYPES)
    if "foreign_key" in requested and "table" not in requested:
        requested.append("table")
    if "dependency" in requested:
        requested.extend(
            object_type
            for object_type in (*POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE, *POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE)
            if object_type not in requested
        )
    return requested
