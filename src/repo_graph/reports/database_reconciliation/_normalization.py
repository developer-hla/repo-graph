"""SQL item normalization helpers for database reconciliation reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import compact_dict, mapping_value, string_value
from repo_graph.reports.database_reconciliation._constants import (
    CURRENT_DATABASE_SCHEMA_STATE,
    SQLSERVER_METADATA_PARSER,
)
from repo_graph.vocabulary import SQL_EDGE_TYPES, SQL_ENTITY_TYPES


def relationship_sql_entities(items: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    entities: dict[str, Mapping[str, Any]] = {}
    for item in items:
        for key in ("from_entity", "target"):
            value = item.get(key)
            if isinstance(value, Mapping) and is_sql_entity(value):
                entity_id = string_value(value.get("entity_id")) or f"{value.get('source_name')}:{value.get('name')}"
                entities[entity_id] = value
    return list(entities.values())


def database_edge_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "kind": "edge",
            "edge_id": string_value(edge.get("edge_id")),
            "source_name": string_value(edge.get("source_name")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "to_name": string_value(edge.get("to_name")),
            "to_type": string_value(edge.get("to_type")),
            "edge_type": string_value(edge.get("edge_type")),
            "resolved": edge.get("resolved"),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
            "sql_operation": string_value(properties.get("sql_operation")),
            "schema_state": string_value(properties.get("schema_state")),
            "metadata_source": string_value(properties.get("metadata_source")),
        }
    )


def database_entity_example(entity: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(entity.get("properties"))
    return compact_dict(
        {
            "kind": "entity",
            "entity_id": string_value(entity.get("entity_id")),
            "entity_type": string_value(entity.get("entity_type")),
            "name": string_value(entity.get("name")),
            "source_name": string_value(entity.get("source_name")),
            "file_path": string_value(entity.get("file_path")),
            "line_number": entity.get("line_number"),
            "schema": string_value(properties.get("schema")),
            "full_name": string_value(properties.get("full_name")),
            "schema_state": string_value(properties.get("schema_state")),
            "metadata_source": string_value(properties.get("metadata_source")),
        }
    )


def is_sql_entity(entity: Mapping[str, Any]) -> bool:
    return string_value(entity.get("entity_type")) in SQL_ENTITY_TYPES


def is_sql_edge(edge: Mapping[str, Any]) -> bool:
    return string_value(edge.get("edge_type")) in SQL_EDGE_TYPES


def is_database_metadata_edge(edge: Mapping[str, Any]) -> bool:
    return string_value(edge.get("parser")) == SQLSERVER_METADATA_PARSER


def is_current_database_entity(entity: Mapping[str, Any]) -> bool:
    return schema_state(entity) == CURRENT_DATABASE_SCHEMA_STATE


def source_matches(item: Mapping[str, Any], source_name: str | None) -> bool:
    return not source_name or item.get("source_name") == source_name


def schema_state(entity: Mapping[str, Any]) -> str | None:
    return string_value(mapping_value(entity.get("properties")).get("schema_state"))


def entity_index_by_sql_name(entities: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    index: dict[str, list[Mapping[str, Any]]] = {}
    for entity in entities:
        key = entity_sql_key(entity)
        if key:
            index.setdefault(key, []).append(entity)
    return index


def entity_sql_key(entity: Mapping[str, Any]) -> str | None:
    return normalized_sql_key(entity_sql_name(entity))


def entity_sql_name(entity: Mapping[str, Any]) -> str | None:
    properties = mapping_value(entity.get("properties"))
    return string_value(properties.get("full_name")) or string_value(entity.get("name"))


def edge_sql_target_key(
    edge: Mapping[str, Any],
    entity_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    to_entity_id = string_value(edge.get("to_entity_id"))
    target_entity = entity_by_id.get(to_entity_id) if to_entity_id else None
    if target_entity:
        return entity_sql_key(target_entity)
    properties = mapping_value(edge.get("properties"))
    return normalized_sql_key(
        string_value(properties.get("normalized_target"))
        or string_value(properties.get("raw_target"))
        or string_value(edge.get("to_name"))
    )


def normalized_sql_key(value: str | None) -> str | None:
    if not value:
        return None
    return ".".join(part.strip().strip("[]`\"'").lower() for part in value.split(".") if part.strip())
