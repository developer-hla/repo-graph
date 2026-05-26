"""Database reconciliation report constants."""

from __future__ import annotations

CURRENT_DATABASE_SCHEMA_STATE = "current_database"
HISTORICAL_SCHEMA_STATE = "historical"
SQLSERVER_METADATA_PARSER = "sqlserver_metadata"

DATABASE_RECONCILIATION_ORDER = {
    "code_only_reference": 0,
    "unresolved_database_reference": 1,
    "schema_drift": 2,
    "migration_only_object": 3,
    "database_only_object": 4,
}

DATABASE_RECONCILIATION_ACTIONS = {
    "code_only_reference": "Confirm the object exists in the current database or update the code reference.",
    "unresolved_database_reference": (
        "Inspect the database metadata source scope; the catalog references a target outside the loaded graph."
    ),
    "schema_drift": "Compare source schema evidence with current database metadata before changing dependent code.",
    "migration_only_object": (
        "Treat this as historical evidence unless the object is restored in current database metadata."
    ),
    "database_only_object": (
        "Check whether this current database object is unused, externally used, or missing code/schema evidence."
    ),
}
