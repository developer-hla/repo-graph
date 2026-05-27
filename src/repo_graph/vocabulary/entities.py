"""Graph entity vocabulary."""

from __future__ import annotations

ENTITY_TYPES = (
    "api_route",
    "build_config",
    "cache_key",
    "cache_store",
    "class",
    "config_file",
    "config_value",
    "container",
    "deployment",
    "file",
    "function",
    "ingress",
    "interface",
    "message_contract",
    "message_queue",
    "message_topic",
    "module",
    "package",
    "project",
    "repository",
    "service",
    "solution",
    "storage_location",
    "scheduled_job",
    "sql_function",
    "sql_table",
    "sql_trigger",
    "sql_view",
    "stored_procedure",
    "workspace",
)
EDGE_TARGET_TYPES = tuple(sorted({*ENTITY_TYPES, "sql_object"}))
SQL_ENTITY_TYPES = frozenset({"sql_function", "sql_table", "sql_trigger", "sql_view", "stored_procedure"})
MESSAGE_ENTITY_TYPES = frozenset({"message_contract", "message_queue", "message_topic"})
STORAGE_ENTITY_TYPES = frozenset({"storage_location"})
CACHE_ENTITY_TYPES = frozenset({"cache_key", "cache_store"})
