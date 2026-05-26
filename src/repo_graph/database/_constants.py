"""Database metadata constants."""

from __future__ import annotations

SQLSERVER_METADATA_PARSER = "sqlserver_metadata"
POSTGRES_METADATA_PARSER = "postgres_metadata"
SQLSERVER_ENGINE = "sqlserver"
POSTGRES_ENGINE = "postgres"
CURRENT_DATABASE_SCHEMA_STATE = "current_database"
DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS = 10
DEFAULT_DATABASE_MAX_METADATA_ROWS = 50_000

SQLSERVER_OBJECT_METADATA_SOURCES = {
    "sql_table": "sys.tables",
    "sql_view": "sys.views",
    "sql_trigger": "sys.triggers",
    "stored_procedure": "sys.procedures",
    "sql_function": "sys.objects",
}

POSTGRES_OBJECT_METADATA_SOURCES = {
    "sql_table": "pg_class",
    "sql_view": "pg_class",
    "sql_trigger": "pg_trigger",
    "stored_procedure": "pg_proc",
    "sql_function": "pg_proc",
}

DATABASE_OBJECT_TYPE_ALIASES = {
    "function": "sql_function",
    "fn": "sql_function",
    "if": "sql_function",
    "matview": "sql_view",
    "materialized_view": "sql_view",
    "p": "stored_procedure",
    "proc": "stored_procedure",
    "procedure": "stored_procedure",
    "sql_function": "sql_function",
    "sql_object": "sql_object",
    "sql_table": "sql_table",
    "sql_trigger": "sql_trigger",
    "sql_view": "sql_view",
    "stored_procedure": "stored_procedure",
    "table": "sql_table",
    "tf": "sql_function",
    "tr": "sql_trigger",
    "trigger": "sql_trigger",
    "u": "sql_table",
    "user_table": "sql_table",
    "v": "sql_view",
    "view": "sql_view",
}

SQLSERVER_OBJECT_TYPE_ALIASES = DATABASE_OBJECT_TYPE_ALIASES

EXECUTE_DEPENDENCY_TYPES = frozenset(
    {
        "call",
        "calls_sql",
        "exec",
        "execute",
        "execution",
        "procedure_execution",
    }
)
SQLSERVER_OBJECT_TYPES_BY_INCLUDE_TYPE = {
    "function": ("FN", "IF", "TF"),
    "stored_procedure": ("P",),
    "table": ("U",),
    "view": ("V",),
}
POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE = {
    "table": ("f", "p", "r"),
    "view": ("m", "v"),
}
POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE = {
    "function": ("f",),
    "stored_procedure": ("p",),
}
POSTGRES_DEFAULT_INCLUDE_OBJECT_TYPES = ("function", "stored_procedure", "table", "trigger", "view")
