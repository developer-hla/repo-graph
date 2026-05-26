"""Shared live metadata reader helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from repo_graph.database._constants import DATABASE_OBJECT_TYPE_ALIASES
from repo_graph.database._naming import normalize_metadata_value, normalize_sql_identifier, required_text


@dataclass
class MetadataReadBudget:
    """Tracks the configured metadata row cap across catalog queries."""

    limit: int
    engine_label: str
    consumed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(self.limit - self.consumed, 0)

    @property
    def has_remaining(self) -> bool:
        return self.remaining > 0

    def record(self, row_count: int, metadata_source: str) -> None:
        remaining_before = self.remaining
        self.consumed += row_count
        if row_count >= remaining_before:
            self.errors.append(
                f"{self.engine_label} metadata row limit reached while reading {metadata_source}; "
                "increase max_metadata_rows to inspect more metadata."
            )


def fetch_sqlserver_rows(
    cursor: Any,
    query: str,
    params: tuple[str, ...],
    budget: MetadataReadBudget,
    metadata_source: str,
) -> list[Any]:
    rows = list(cursor.execute(query, *params).fetchall())
    budget.record(len(rows), metadata_source)
    return rows


def fetch_postgres_rows(
    cursor: Any,
    query: str,
    params: tuple[Any, ...],
    budget: MetadataReadBudget,
    metadata_source: str,
) -> list[Any]:
    cursor.execute(query, params)
    rows = list(cursor.fetchall())
    budget.record(len(rows), metadata_source)
    return rows


def include_database_object_type(include_object_types: tuple[str, ...], object_type: str) -> bool:
    return not include_object_types or object_type in include_object_types


def include_database_object_type_or_dependency(include_object_types: tuple[str, ...], object_type: str) -> bool:
    return include_database_object_type(include_object_types, object_type) or "dependency" in include_object_types


def sqlserver_catalog_object_type(value: str | None) -> str:
    if not value:
        return "sql_object"
    return DATABASE_OBJECT_TYPE_ALIASES.get(normalize_metadata_value(value), "sql_object")


def postgres_catalog_object_type(value: str | None) -> str:
    if not value:
        return "sql_object"
    return DATABASE_OBJECT_TYPE_ALIASES.get(normalize_metadata_value(value), "sql_object")


def safe_sql_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("SQL metadata query limit must be a positive integer.")
    return value


def row_text(row: Any, field_name: str) -> str:
    value = optional_row_text(row, field_name)
    if value is None:
        raise ValueError(f"Database metadata row is missing {field_name}.")
    return value


def optional_row_text(row: Any, field_name: str) -> str | None:
    value = row_value(row, field_name)
    if value is None:
        return None
    return required_text(str(value), field_name)


def row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(field_name)
    return getattr(row, field_name, None)


def row_bool(row: Any, field_name: str) -> bool:
    value = row_value(row, field_name)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return normalize_metadata_value(value) in {"1", "true", "t", "yes", "y"}
    return False


def postgres_trigger_events(row: Any) -> tuple[str, ...]:
    events = [
        event_name
        for field_name, event_name in (
            ("fires_insert", "INSERT"),
            ("fires_update", "UPDATE"),
            ("fires_delete", "DELETE"),
            ("fires_truncate", "TRUNCATE"),
        )
        if row_bool(row, field_name)
    ]
    return tuple(events)


def normalize_trigger_event(value: str) -> str:
    return normalize_metadata_value(value).upper()


def trigger_source_name(table: str, trigger_name: str) -> str:
    return f"{normalize_sql_identifier(table)}.{normalize_sql_identifier(trigger_name)}"


def trigger_source_schema(schema: str, table: str) -> str:
    return f"{normalize_sql_identifier(schema)}.{normalize_sql_identifier(table)}"


def set_cursor_timeout(cursor: Any, timeout: int) -> None:
    try:
        cursor.timeout = timeout
    except Exception:
        return


def set_postgres_statement_timeout(cursor: Any, timeout: int) -> None:
    cursor.execute("SET statement_timeout = %s", (timeout * 1000,))


def close_database_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()
