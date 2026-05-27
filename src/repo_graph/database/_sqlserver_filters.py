"""SQL Server metadata reader filter helpers."""

from __future__ import annotations

from repo_graph.database._constants import SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE


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
