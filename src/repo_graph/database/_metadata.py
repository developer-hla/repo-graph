"""Database metadata compatibility facade.

Public callers should import from `repo_graph.database`. This module re-exports
implementation pieces for older internal imports while focused modules own the
actual behavior.
"""

from __future__ import annotations

from repo_graph.database._adapters import (
    database_connector_unavailable_message,
    database_metadata_adapter,
    scan_database_metadata,
    supported_database_engines,
)
from repo_graph.database._connectors import (
    postgres_driver_available,
    scan_database_source,
    scan_postgres_source,
    scan_sqlserver_source,
    sqlserver_driver_available,
)
from repo_graph.database._constants import (
    CURRENT_DATABASE_SCHEMA_STATE,
    POSTGRES_ENGINE,
    POSTGRES_METADATA_PARSER,
    SQLSERVER_ENGINE,
    SQLSERVER_METADATA_PARSER,
)
from repo_graph.database._models import (
    DatabaseScanResult,
    DatabaseSourceRequest,
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresMetadata,
    PostgresObjectRow,
    PostgresTriggerRow,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerObjectRow,
    SqlServerTriggerRow,
)
from repo_graph.database._naming import normalize_database_engine
from repo_graph.database._postgres_adapter import scan_postgres_metadata
from repo_graph.database._sqlserver_adapter import scan_sqlserver_metadata

__all__ = [
    "CURRENT_DATABASE_SCHEMA_STATE",
    "POSTGRES_ENGINE",
    "POSTGRES_METADATA_PARSER",
    "SQLSERVER_ENGINE",
    "SQLSERVER_METADATA_PARSER",
    "DatabaseScanResult",
    "DatabaseSourceRequest",
    "PostgresDependencyRow",
    "PostgresForeignKeyRow",
    "PostgresMetadata",
    "PostgresObjectRow",
    "PostgresTriggerRow",
    "SqlServerDependencyRow",
    "SqlServerForeignKeyRow",
    "SqlServerMetadata",
    "SqlServerObjectRow",
    "SqlServerTriggerRow",
    "database_connector_unavailable_message",
    "database_metadata_adapter",
    "normalize_database_engine",
    "postgres_driver_available",
    "scan_database_metadata",
    "scan_database_source",
    "scan_postgres_metadata",
    "scan_postgres_source",
    "scan_sqlserver_metadata",
    "scan_sqlserver_source",
    "sqlserver_driver_available",
    "supported_database_engines",
]
