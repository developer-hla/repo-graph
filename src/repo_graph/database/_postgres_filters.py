"""PostgreSQL metadata reader filter helpers."""

from __future__ import annotations

from repo_graph.database._constants import (
    POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE,
    POSTGRES_DEFAULT_INCLUDE_OBJECT_TYPES,
    POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE,
)


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
