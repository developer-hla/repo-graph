"""SQL Server catalog query builders."""

from __future__ import annotations

from repo_graph.database._reader_common import safe_sql_limit
from repo_graph.database._sqlserver_filters import sqlserver_in_filter, sqlserver_schema_filter


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
