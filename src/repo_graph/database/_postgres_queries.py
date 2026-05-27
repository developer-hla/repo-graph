"""PostgreSQL catalog query builders."""

from __future__ import annotations

from repo_graph.database._postgres_filters import (
    postgres_in_filter,
    postgres_schema_filter,
    postgres_user_schema_filter,
)
from repo_graph.database._reader_common import safe_sql_limit


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
