"""PostgreSQL metadata row mapping helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from repo_graph.database._models import (
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresObjectRow,
    PostgresTriggerRow,
)
from repo_graph.database._naming import normalize_metadata_value
from repo_graph.database._reader_common import (
    optional_row_text,
    postgres_catalog_object_type,
    postgres_trigger_events,
    row_bool,
    row_text,
)


@dataclass
class PostgresClassObjectGroups:
    tables: list[PostgresObjectRow] = field(default_factory=list)
    views: list[PostgresObjectRow] = field(default_factory=list)
    materialized_views: list[PostgresObjectRow] = field(default_factory=list)


@dataclass
class PostgresProcObjectGroups:
    functions: list[PostgresObjectRow] = field(default_factory=list)
    procedures: list[PostgresObjectRow] = field(default_factory=list)


def postgres_class_object_groups(rows: Iterable[Any]) -> PostgresClassObjectGroups:
    groups = PostgresClassObjectGroups()
    for row in rows:
        object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
        match normalize_metadata_value(row_text(row, "object_type")):
            case "table":
                groups.tables.append(object_row)
            case "view":
                groups.views.append(object_row)
            case "materialized_view":
                groups.materialized_views.append(object_row)
    return groups


def postgres_proc_object_groups(rows: Iterable[Any]) -> PostgresProcObjectGroups:
    groups = PostgresProcObjectGroups()
    for row in rows:
        object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
        match normalize_metadata_value(row_text(row, "object_type")):
            case "function":
                groups.functions.append(object_row)
            case "procedure":
                groups.procedures.append(object_row)
    return groups


def postgres_foreign_key_row(row: Any) -> PostgresForeignKeyRow:
    return PostgresForeignKeyRow(
        schema=row_text(row, "schema_name"),
        table=row_text(row, "table_name"),
        referenced_schema=row_text(row, "referenced_schema_name"),
        referenced_table=row_text(row, "referenced_table_name"),
        name=optional_row_text(row, "constraint_name"),
    )


def postgres_trigger_row(row: Any) -> PostgresTriggerRow:
    return PostgresTriggerRow(
        schema=row_text(row, "schema_name"),
        name=row_text(row, "trigger_name"),
        table_schema=row_text(row, "table_schema_name"),
        table=row_text(row, "table_name"),
        events=postgres_trigger_events(row),
        is_enabled=not row_bool(row, "is_disabled"),
        function_schema=optional_row_text(row, "function_schema_name"),
        function_name=optional_row_text(row, "function_name"),
    )


def postgres_dependency_row(row: Any) -> PostgresDependencyRow:
    return PostgresDependencyRow(
        from_schema=row_text(row, "from_schema_name"),
        from_name=row_text(row, "from_object_name"),
        from_type=postgres_catalog_object_type(row_text(row, "from_object_type")),
        to_schema=row_text(row, "to_schema_name"),
        to_name=row_text(row, "to_object_name"),
        to_type=postgres_catalog_object_type(row_text(row, "to_object_type")),
        dependency_type=optional_row_text(row, "dependency_type") or "object_dependency",
        name=optional_row_text(row, "dependency_name"),
    )
