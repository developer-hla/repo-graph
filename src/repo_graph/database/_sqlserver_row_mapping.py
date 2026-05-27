"""SQL Server metadata row mapping helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from repo_graph.database._models import (
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerObjectRow,
    SqlServerTriggerRow,
)
from repo_graph.database._reader_common import (
    normalize_trigger_event,
    optional_row_text,
    row_bool,
    row_text,
    sqlserver_catalog_object_type,
)


@dataclass
class SqlServerObjectGroups:
    tables: list[SqlServerObjectRow] = field(default_factory=list)
    views: list[SqlServerObjectRow] = field(default_factory=list)
    stored_procedures: list[SqlServerObjectRow] = field(default_factory=list)
    functions: list[SqlServerObjectRow] = field(default_factory=list)


def sqlserver_object_groups(rows: Iterable[Any]) -> SqlServerObjectGroups:
    groups = SqlServerObjectGroups()
    for row in rows:
        object_row = SqlServerObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
        match sqlserver_catalog_object_type(row_text(row, "object_type")):
            case "sql_table":
                groups.tables.append(object_row)
            case "sql_view":
                groups.views.append(object_row)
            case "stored_procedure":
                groups.stored_procedures.append(object_row)
            case "sql_function":
                groups.functions.append(object_row)
    return groups


def sqlserver_foreign_key_row(row: Any) -> SqlServerForeignKeyRow:
    return SqlServerForeignKeyRow(
        schema=row_text(row, "schema_name"),
        table=row_text(row, "table_name"),
        referenced_schema=row_text(row, "referenced_schema_name"),
        referenced_table=row_text(row, "referenced_table_name"),
        name=optional_row_text(row, "constraint_name"),
    )


def sqlserver_trigger_rows(rows: Iterable[Any]) -> list[SqlServerTriggerRow]:
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


def sqlserver_dependency_row(row: Any) -> SqlServerDependencyRow:
    from_schema = row_text(row, "from_schema_name")
    return SqlServerDependencyRow(
        from_schema=from_schema,
        from_name=row_text(row, "from_object_name"),
        from_type=sqlserver_catalog_object_type(row_text(row, "from_object_type")),
        to_schema=optional_row_text(row, "to_schema_name") or from_schema,
        to_name=row_text(row, "to_object_name"),
        to_type=sqlserver_catalog_object_type(optional_row_text(row, "to_object_type")),
        dependency_type="module_reference",
        name=optional_row_text(row, "dependency_name"),
    )
