"""Live database metadata connector entry points."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from typing import Any

from repo_graph.database._adapters import (
    database_connector_unavailable_message,
)
from repo_graph.database._constants import (
    DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS,
    POSTGRES_ENGINE,
    POSTGRES_METADATA_PARSER,
    SQLSERVER_ENGINE,
    SQLSERVER_METADATA_PARSER,
)
from repo_graph.database._models import DatabaseScanResult, DatabaseSourceRequest
from repo_graph.database._naming import normalize_database_engine
from repo_graph.database._postgres_adapter import scan_postgres_metadata
from repo_graph.database._readers import close_database_connection, read_postgres_metadata, read_sqlserver_metadata
from repo_graph.database._sqlserver_adapter import scan_sqlserver_metadata


def scan_database_source(_request: DatabaseSourceRequest) -> DatabaseScanResult:
    """Live database connector entry point."""

    engine = normalize_database_engine(_request.engine)
    if engine == SQLSERVER_ENGINE:
        return scan_sqlserver_source(_request)
    if engine == POSTGRES_ENGINE:
        return scan_postgres_source(_request)
    return DatabaseScanResult(errors=[database_connector_unavailable_message(_request.source_name, engine)])


def scan_sqlserver_source(
    request: DatabaseSourceRequest,
    connect: Callable[[str, int], Any] | None = None,
) -> DatabaseScanResult:
    """Read SQL Server catalog metadata and convert it into typed facts."""

    connection_string, connection_error = database_connection_string(request)
    if connection_error is not None:
        return connection_error
    assert connection_string is not None
    if connect is None and not sqlserver_driver_available():
        return DatabaseScanResult(
            errors=[
                "SQL Server connector requires optional dependency 'pyodbc' and a SQL Server ODBC driver "
                f"for database source '{request.source_name}'."
            ]
        )

    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    try:
        connection = (
            connect(connection_string, timeout)
            if connect is not None
            else connect_to_sqlserver(connection_string, timeout)
        )
    except Exception as exc:
        return DatabaseScanResult(
            errors=[
                f"SQL Server metadata connection failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )

    try:
        metadata_result = read_sqlserver_metadata(connection, request)
    except Exception as exc:
        return DatabaseScanResult(
            errors=[
                f"SQL Server metadata read failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )
    finally:
        close_database_connection(connection)

    facts = scan_sqlserver_metadata(request.source_name, metadata_result.metadata)
    facts.extend_errors(metadata_result.errors, source_name=request.source_name, parser=SQLSERVER_METADATA_PARSER)
    return facts


def scan_postgres_source(
    request: DatabaseSourceRequest,
    connect: Callable[[str, int], Any] | None = None,
) -> DatabaseScanResult:
    """Read PostgreSQL catalog metadata and convert it into typed facts."""

    connection_string, connection_error = database_connection_string(request)
    if connection_error is not None:
        return connection_error
    assert connection_string is not None
    if connect is None and not postgres_driver_available():
        return DatabaseScanResult(
            errors=[
                "PostgreSQL connector requires optional dependency 'psycopg' "
                f"for database source '{request.source_name}'."
            ]
        )

    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    try:
        connection = (
            connect(connection_string, timeout)
            if connect is not None
            else connect_to_postgres(connection_string, timeout)
        )
    except Exception as exc:
        return DatabaseScanResult(
            errors=[
                f"PostgreSQL metadata connection failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )

    try:
        metadata_result = read_postgres_metadata(connection, request)
    except Exception as exc:
        return DatabaseScanResult(
            errors=[
                f"PostgreSQL metadata read failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )
    finally:
        close_database_connection(connection)

    facts = scan_postgres_metadata(request.source_name, metadata_result.metadata)
    facts.extend_errors(metadata_result.errors, source_name=request.source_name, parser=POSTGRES_METADATA_PARSER)
    return facts


def database_connection_string(request: DatabaseSourceRequest) -> tuple[str | None, DatabaseScanResult | None]:
    connection_env = request.connection_env.strip()
    if not connection_env:
        return None, DatabaseScanResult(
            errors=[f"Database source '{request.source_name}' connection_env is not configured."]
        )
    connection_string = os.environ.get(connection_env)
    if not connection_string:
        return None, DatabaseScanResult(
            errors=[f"Database source '{request.source_name}' connection_env is not set in the runtime environment."]
        )
    return connection_string, None


def sqlserver_driver_available() -> bool:
    return importlib.util.find_spec("pyodbc") is not None


def postgres_driver_available() -> bool:
    return importlib.util.find_spec("psycopg") is not None


def connect_to_sqlserver(connection_string: str, timeout: int) -> Any:
    pyodbc = __import__("pyodbc")
    return pyodbc.connect(connection_string, timeout=timeout, autocommit=True)


def connect_to_postgres(connection_string: str, timeout: int) -> Any:
    psycopg = __import__("psycopg")
    rows = __import__("psycopg.rows", fromlist=["dict_row"])
    return psycopg.connect(
        connection_string,
        connect_timeout=timeout,
        autocommit=True,
        row_factory=rows.dict_row,
    )


def safe_database_error_text(exc: Exception, connection_string: str) -> str:
    return f"{type(exc).__name__}: {str(exc).replace(connection_string, '[redacted]')}"
