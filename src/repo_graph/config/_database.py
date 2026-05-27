"""Database source config parsing."""

from __future__ import annotations

from typing import Any

from repo_graph.config._defaults import DATABASE_ENGINES, DATABASE_OBJECT_TYPES, DEFAULT_DATABASE_OBJECT_TYPES
from repo_graph.config._models import Source
from repo_graph.config._values import optional_positive_int, required_string, string_tuple


def parse_database_source(raw_source: dict[str, Any], name: str, ref: str) -> Source:
    if "connection_string" in raw_source:
        raise ValueError(f"Database source '{name}' must use 'connection_env', not 'connection_string'.")
    engine = required_string(raw_source.get("engine"), f"Database source '{name}' engine")
    if engine not in DATABASE_ENGINES:
        raise ValueError(f"Database source '{name}' has unsupported engine '{engine}'.")
    connection_env = required_string(raw_source.get("connection_env"), f"Database source '{name}' connection_env")
    schemas = string_tuple(raw_source.get("schemas"), field_name=f"Database source '{name}' schemas")
    include_object_types = string_tuple(
        raw_source.get("include_object_types", DEFAULT_DATABASE_OBJECT_TYPES),
        field_name=f"Database source '{name}' include_object_types",
    )
    unsupported_object_types = sorted(set(include_object_types) - DATABASE_OBJECT_TYPES)
    if unsupported_object_types:
        raise ValueError(
            f"Database source '{name}' has unsupported include_object_types: {', '.join(unsupported_object_types)}"
        )
    return Source(
        name=name,
        source_type="database",
        ref=ref,
        engine=engine,
        connection_env=connection_env,
        schemas=schemas,
        include_object_types=include_object_types,
        query_timeout_seconds=optional_positive_int(
            raw_source.get("query_timeout_seconds"),
            f"Database source '{name}' query_timeout_seconds",
        ),
        max_metadata_rows=optional_positive_int(
            raw_source.get("max_metadata_rows"),
            f"Database source '{name}' max_metadata_rows",
        ),
    )
