"""Database metadata adapter registry."""

from __future__ import annotations

from repo_graph.database._constants import POSTGRES_ENGINE, SQLSERVER_ENGINE
from repo_graph.database._models import DatabaseMetadataAdapter, DatabaseScanResult
from repo_graph.database._naming import normalize_database_engine, required_text
from repo_graph.database._postgres_adapter import PostgresMetadataAdapter
from repo_graph.database._sqlserver_adapter import SqlServerMetadataAdapter

DATABASE_METADATA_ADAPTERS: dict[str, DatabaseMetadataAdapter] = {
    SQLSERVER_ENGINE: SqlServerMetadataAdapter(),
    POSTGRES_ENGINE: PostgresMetadataAdapter(),
}


def supported_database_engines() -> frozenset[str]:
    """Return database engines with a metadata adapter contract."""

    return frozenset(DATABASE_METADATA_ADAPTERS)


def database_metadata_adapter(engine: str) -> DatabaseMetadataAdapter:
    """Return the metadata adapter for a supported database engine."""

    normalized = normalize_database_engine(engine)
    adapter = DATABASE_METADATA_ADAPTERS.get(normalized)
    if adapter is None:
        raise ValueError(f"Unsupported database engine: {engine}")
    return adapter


def scan_database_metadata(source_name: str, engine: str, metadata: object) -> DatabaseScanResult:
    """Convert metadata rows for any supported database engine into typed facts."""

    return database_metadata_adapter(engine).scan_metadata(source_name, metadata)


def database_connector_unavailable_message(source_name: str, engine: str | None) -> str:
    """Return the standard safe error for a database source without a live connector."""

    source_name = required_text(source_name, "source_name")
    if engine:
        normalized = normalize_database_engine(engine)
        database_metadata_adapter(normalized)
        return (
            f"Database source '{source_name}' uses engine '{normalized}', which has a metadata adapter "
            "but no live connector enabled yet."
        )
    return f"Database source '{source_name}' is missing a database engine."
