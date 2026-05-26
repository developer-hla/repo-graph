"""Database metadata naming and normalization helpers."""

from __future__ import annotations

from repo_graph.database._constants import DATABASE_OBJECT_TYPE_ALIASES


def normalize_database_engine(engine: str) -> str:
    return required_text(engine, "database engine").lower()


def trigger_source_name(table: str, trigger_name: str) -> str:
    return f"{normalize_sql_identifier(table)}.{normalize_sql_identifier(trigger_name)}"


def trigger_source_schema(schema: str, table: str) -> str:
    return f"{normalize_sql_identifier(schema)}.{normalize_sql_identifier(table)}"


def metadata_identity_key(*parts: str | None) -> str:
    return "|".join(required_text(part, "metadata identity value") for part in parts if part is not None)


def graph_entity_type(value: str | None, engine_label: str = "database") -> str | None:
    if value is None:
        return None
    normalized = normalize_metadata_value(value)
    entity_type = DATABASE_OBJECT_TYPE_ALIASES.get(normalized)
    if entity_type is None:
        raise ValueError(f"Unsupported {engine_label} object type: {value}")
    return entity_type


def sqlserver_full_name(schema: str, name: str) -> str:
    return database_full_name(schema, name)


def postgres_full_name(schema: str, name: str) -> str:
    return database_full_name(schema, name)


def database_trigger_full_name(schema: str, table: str, trigger_name: str) -> str:
    return ".".join(
        (
            normalize_sql_identifier(schema),
            normalize_sql_identifier(table),
            normalize_sql_identifier(trigger_name),
        )
    )


def database_full_name(schema: str, name: str) -> str:
    normalized_name = normalize_sql_identifier(name)
    parts = tuple(part for part in normalized_name.split(".") if part)
    if len(parts) >= 2:
        return f"{parts[-2]}.{parts[-1]}"
    return f"{normalize_sql_identifier(schema)}.{normalized_name}"


def split_sql_name(value: str) -> tuple[str | None, str]:
    parts = tuple(part for part in value.split(".") if part)
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, value


def normalize_sql_identifier(value: str) -> str:
    return ".".join(strip_sql_identifier_part(part) for part in required_text(value, "SQL identifier").split("."))


def strip_sql_identifier_part(value: str) -> str:
    return value.strip().strip("[]`\"'")


def normalize_metadata_value(value: str) -> str:
    return required_text(value, "metadata value").lower().replace(" ", "_").replace("-", "_")


def required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()
