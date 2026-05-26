"""Pure database metadata adapters for RepoGraph."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from repo_graph.extraction.facts import EntityFact, EntityReference, Evidence, FactBatch, RelationshipFact, ScanIssue

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


class DatabaseMetadataAdapter(Protocol):
    """Converts engine-specific metadata rows into typed facts."""

    engine: str
    metadata_parser: str

    def scan_metadata(self, source_name: str, metadata: object) -> DatabaseScanResult:
        """Convert engine metadata rows into RepoGraph facts."""
        ...


class DatabaseConnectorUnavailable(RuntimeError):
    """Raised when a database engine has no live connector enabled."""


@dataclass(frozen=True)
class SqlServerObjectRow:
    """One object row from SQL Server catalog metadata."""

    schema: str
    name: str


@dataclass(frozen=True)
class SqlServerForeignKeyRow:
    """One foreign key relationship from SQL Server catalog metadata."""

    schema: str
    table: str
    referenced_schema: str
    referenced_table: str
    name: str | None = None


@dataclass(frozen=True)
class SqlServerDependencyRow:
    """One module dependency from SQL Server catalog metadata."""

    from_schema: str
    from_name: str
    to_schema: str
    to_name: str
    from_type: str = "sql_object"
    to_type: str = "sql_object"
    dependency_type: str = "module_reference"
    name: str | None = None


@dataclass(frozen=True)
class SqlServerTriggerRow:
    """One DML trigger relationship from SQL Server catalog metadata."""

    schema: str
    name: str
    table_schema: str
    table: str
    events: tuple[str, ...] = ()
    is_disabled: bool | None = None


@dataclass(frozen=True)
class SqlServerMetadata:
    """Typed SQL Server metadata rows used by the pure adapter."""

    tables: tuple[SqlServerObjectRow, ...] = ()
    views: tuple[SqlServerObjectRow, ...] = ()
    stored_procedures: tuple[SqlServerObjectRow, ...] = ()
    functions: tuple[SqlServerObjectRow, ...] = ()
    triggers: tuple[SqlServerTriggerRow, ...] = ()
    foreign_keys: tuple[SqlServerForeignKeyRow, ...] = ()
    dependencies: tuple[SqlServerDependencyRow, ...] = ()


@dataclass(frozen=True)
class PostgresObjectRow:
    """One object row from PostgreSQL catalog metadata."""

    schema: str
    name: str


@dataclass(frozen=True)
class PostgresForeignKeyRow:
    """One foreign key relationship from PostgreSQL catalog metadata."""

    schema: str
    table: str
    referenced_schema: str
    referenced_table: str
    name: str | None = None


@dataclass(frozen=True)
class PostgresDependencyRow:
    """One object dependency from PostgreSQL catalog metadata."""

    from_schema: str
    from_name: str
    to_schema: str
    to_name: str
    from_type: str = "sql_object"
    to_type: str = "sql_object"
    dependency_type: str = "object_dependency"
    name: str | None = None


@dataclass(frozen=True)
class PostgresTriggerRow:
    """One trigger relationship from PostgreSQL catalog metadata."""

    schema: str
    name: str
    table_schema: str
    table: str
    events: tuple[str, ...] = ()
    is_enabled: bool | None = None
    function_schema: str | None = None
    function_name: str | None = None


@dataclass(frozen=True)
class PostgresMetadata:
    """Typed PostgreSQL metadata rows used by the pure adapter."""

    tables: tuple[PostgresObjectRow, ...] = ()
    views: tuple[PostgresObjectRow, ...] = ()
    materialized_views: tuple[PostgresObjectRow, ...] = ()
    functions: tuple[PostgresObjectRow, ...] = ()
    procedures: tuple[PostgresObjectRow, ...] = ()
    triggers: tuple[PostgresTriggerRow, ...] = ()
    foreign_keys: tuple[PostgresForeignKeyRow, ...] = ()
    dependencies: tuple[PostgresDependencyRow, ...] = ()


class DatabaseScanResult:
    """Typed facts emitted from a database metadata source."""

    def __init__(
        self,
        facts: FactBatch | None = None,
        entities: list[EntityFact] | None = None,
        edges: list[RelationshipFact] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.facts = facts or FactBatch()
        if entities:
            self.facts.entities.extend(entities)
        if edges:
            self.facts.relationships.extend(edges)
        if errors:
            self.extend_errors(errors)

    @property
    def entities(self) -> list[EntityFact]:
        return self.facts.entities

    @entities.setter
    def entities(self, value: list[EntityFact]) -> None:
        self.facts.entities = value

    @property
    def edges(self) -> list[RelationshipFact]:
        return self.facts.relationships

    @edges.setter
    def edges(self, value: list[RelationshipFact]) -> None:
        self.facts.relationships = value

    @property
    def errors(self) -> list[str]:
        return [issue.message for issue in self.facts.issues]

    def add_error(
        self,
        message: str,
        source_name: str = "database",
        parser: str = "database_metadata",
        metadata_source: str | None = None,
    ) -> None:
        self.facts.issues.append(
            ScanIssue(
                message=message,
                evidence=Evidence(
                    source_name=source_name,
                    parser=parser,
                    file_path=metadata_source,
                    confidence="high",
                ),
            )
        )

    def extend_errors(
        self,
        errors: list[str],
        source_name: str = "database",
        parser: str = "database_metadata",
        metadata_source: str | None = None,
    ) -> None:
        for error in errors:
            self.add_error(error, source_name=source_name, parser=parser, metadata_source=metadata_source)


@dataclass(frozen=True)
class DatabaseSourceRequest:
    """Database source settings needed by a live metadata connector."""

    source_name: str
    engine: str
    connection_env: str
    schemas: tuple[str, ...] = ()
    include_object_types: tuple[str, ...] = ()
    query_timeout_seconds: int | None = None
    max_metadata_rows: int | None = None


@dataclass(frozen=True)
class SqlServerMetadataReadResult:
    """SQL Server metadata rows plus bounded-read warnings."""

    metadata: SqlServerMetadata
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PostgresMetadataReadResult:
    """PostgreSQL metadata rows plus bounded-read warnings."""

    metadata: PostgresMetadata
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DatabaseGraphError:
    """Structured database metadata adapter error."""

    code: str
    message: str
    source_name: str
    metadata_source: str
    source_object: str | None = None
    target_object: str | None = None

    def to_message(self) -> str:
        return self.message


@dataclass(frozen=True)
class EdgeBuildResult:
    """One attempted metadata relationship conversion."""

    edge: RelationshipFact | None = None
    error: DatabaseGraphError | None = None


@dataclass(frozen=True)
class EntityMatch:
    """Entity resolution result for metadata rows."""

    entity: EntityFact | None = None
    candidates: tuple[EntityFact, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return len(self.candidates) > 1


@dataclass(frozen=True)
class SqlServerMetadataAdapter:
    """Pure SQL Server metadata adapter."""

    engine: str = SQLSERVER_ENGINE
    metadata_parser: str = SQLSERVER_METADATA_PARSER

    def scan_metadata(self, source_name: str, metadata: object) -> DatabaseScanResult:
        if not isinstance(metadata, SqlServerMetadata):
            raise TypeError("SQL Server metadata adapter requires SqlServerMetadata.")
        return scan_sqlserver_metadata(source_name, metadata)


@dataclass(frozen=True)
class PostgresMetadataAdapter:
    """Pure PostgreSQL metadata adapter."""

    engine: str = POSTGRES_ENGINE
    metadata_parser: str = POSTGRES_METADATA_PARSER

    def scan_metadata(self, source_name: str, metadata: object) -> DatabaseScanResult:
        if not isinstance(metadata, PostgresMetadata):
            raise TypeError("PostgreSQL metadata adapter requires PostgresMetadata.")
        return scan_postgres_metadata(source_name, metadata)


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


def read_sqlserver_metadata(connection: Any, request: DatabaseSourceRequest) -> SqlServerMetadataReadResult:
    """Read bounded SQL Server catalog metadata from an open connection."""

    budget = MetadataReadBudget(
        limit=request.max_metadata_rows or DEFAULT_DATABASE_MAX_METADATA_ROWS,
        engine_label="SQL Server",
    )
    cursor = connection.cursor()
    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    set_cursor_timeout(cursor, timeout)

    tables: list[SqlServerObjectRow] = []
    views: list[SqlServerObjectRow] = []
    stored_procedures: list[SqlServerObjectRow] = []
    functions: list[SqlServerObjectRow] = []
    object_types = sqlserver_object_type_filter(request.include_object_types)
    if object_types and budget.has_remaining:
        for row in fetch_sqlserver_rows(
            cursor,
            sqlserver_objects_query(budget.remaining, request.schemas, object_types),
            (*object_types, *request.schemas),
            budget,
            "sys.objects",
        ):
            object_row = SqlServerObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match sqlserver_catalog_object_type(row_text(row, "object_type")):
                case "sql_table":
                    tables.append(object_row)
                case "sql_view":
                    views.append(object_row)
                case "stored_procedure":
                    stored_procedures.append(object_row)
                case "sql_function":
                    functions.append(object_row)

    foreign_keys: list[SqlServerForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            SqlServerForeignKeyRow(
                schema=row_text(row, "schema_name"),
                table=row_text(row, "table_name"),
                referenced_schema=row_text(row, "referenced_schema_name"),
                referenced_table=row_text(row, "referenced_table_name"),
                name=optional_row_text(row, "constraint_name"),
            )
            for row in fetch_sqlserver_rows(
                cursor,
                sqlserver_foreign_keys_query(budget.remaining, request.schemas),
                request.schemas,
                budget,
                "sys.foreign_keys",
            )
        )

    triggers: list[SqlServerTriggerRow] = []
    if include_database_object_type_or_dependency(request.include_object_types, "trigger") and budget.has_remaining:
        triggers.extend(
            sqlserver_trigger_rows(
                fetch_sqlserver_rows(
                    cursor,
                    sqlserver_triggers_query(budget.remaining, request.schemas),
                    request.schemas,
                    budget,
                    "sys.triggers",
                )
            )
        )

    dependencies: list[SqlServerDependencyRow] = []
    if include_database_object_type(request.include_object_types, "dependency") and budget.has_remaining:
        for row in fetch_sqlserver_rows(
            cursor,
            sqlserver_dependencies_query(budget.remaining, request.schemas),
            request.schemas,
            budget,
            "sys.sql_expression_dependencies",
        ):
            from_schema = row_text(row, "from_schema_name")
            dependencies.append(
                SqlServerDependencyRow(
                    from_schema=from_schema,
                    from_name=row_text(row, "from_object_name"),
                    from_type=sqlserver_catalog_object_type(row_text(row, "from_object_type")),
                    to_schema=optional_row_text(row, "to_schema_name") or from_schema,
                    to_name=row_text(row, "to_object_name"),
                    to_type=sqlserver_catalog_object_type(optional_row_text(row, "to_object_type")),
                    dependency_type="module_reference",
                    name=optional_row_text(row, "dependency_name"),
                )
            )

    return SqlServerMetadataReadResult(
        metadata=SqlServerMetadata(
            tables=tuple(tables),
            views=tuple(views),
            stored_procedures=tuple(stored_procedures),
            functions=tuple(functions),
            triggers=tuple(triggers),
            foreign_keys=tuple(foreign_keys),
            dependencies=tuple(dependencies),
        ),
        errors=budget.errors,
    )


def read_postgres_metadata(connection: Any, request: DatabaseSourceRequest) -> PostgresMetadataReadResult:
    """Read bounded PostgreSQL catalog metadata from an open connection."""

    budget = MetadataReadBudget(
        limit=request.max_metadata_rows or DEFAULT_DATABASE_MAX_METADATA_ROWS,
        engine_label="PostgreSQL",
    )
    cursor = connection.cursor()
    timeout = request.query_timeout_seconds or DEFAULT_DATABASE_QUERY_TIMEOUT_SECONDS
    set_postgres_statement_timeout(cursor, timeout)

    tables: list[PostgresObjectRow] = []
    views: list[PostgresObjectRow] = []
    materialized_views: list[PostgresObjectRow] = []
    class_relkinds = postgres_class_relkind_filter(request.include_object_types)
    if class_relkinds and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_class_objects_query(budget.remaining, request.schemas, class_relkinds),
            (*class_relkinds, *request.schemas),
            budget,
            "pg_class",
        ):
            object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match normalize_metadata_value(row_text(row, "object_type")):
                case "table":
                    tables.append(object_row)
                case "view":
                    views.append(object_row)
                case "materialized_view":
                    materialized_views.append(object_row)

    functions: list[PostgresObjectRow] = []
    procedures: list[PostgresObjectRow] = []
    proc_kinds = postgres_proc_kind_filter(request.include_object_types)
    if proc_kinds and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_proc_objects_query(budget.remaining, request.schemas, proc_kinds),
            (*proc_kinds, *request.schemas),
            budget,
            "pg_proc",
        ):
            object_row = PostgresObjectRow(row_text(row, "schema_name"), row_text(row, "object_name"))
            match normalize_metadata_value(row_text(row, "object_type")):
                case "function":
                    functions.append(object_row)
                case "procedure":
                    procedures.append(object_row)

    foreign_keys: list[PostgresForeignKeyRow] = []
    if include_database_object_type(request.include_object_types, "foreign_key") and budget.has_remaining:
        foreign_keys.extend(
            PostgresForeignKeyRow(
                schema=row_text(row, "schema_name"),
                table=row_text(row, "table_name"),
                referenced_schema=row_text(row, "referenced_schema_name"),
                referenced_table=row_text(row, "referenced_table_name"),
                name=optional_row_text(row, "constraint_name"),
            )
            for row in fetch_postgres_rows(
                cursor,
                postgres_foreign_keys_query(budget.remaining, request.schemas),
                request.schemas,
                budget,
                "pg_constraint",
            )
        )

    triggers: list[PostgresTriggerRow] = []
    if include_database_object_type_or_dependency(request.include_object_types, "trigger") and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_triggers_query(budget.remaining, request.schemas),
            request.schemas,
            budget,
            "pg_trigger",
        ):
            trigger = PostgresTriggerRow(
                schema=row_text(row, "schema_name"),
                name=row_text(row, "trigger_name"),
                table_schema=row_text(row, "table_schema_name"),
                table=row_text(row, "table_name"),
                events=postgres_trigger_events(row),
                is_enabled=not row_bool(row, "is_disabled"),
                function_schema=optional_row_text(row, "function_schema_name"),
                function_name=optional_row_text(row, "function_name"),
            )
            triggers.append(trigger)

    dependencies: list[PostgresDependencyRow] = []
    if include_database_object_type(request.include_object_types, "dependency") and budget.has_remaining:
        for row in fetch_postgres_rows(
            cursor,
            postgres_dependencies_query(budget.remaining, request.schemas),
            (*request.schemas, *request.schemas),
            budget,
            "pg_depend",
        ):
            dependencies.append(
                PostgresDependencyRow(
                    from_schema=row_text(row, "from_schema_name"),
                    from_name=row_text(row, "from_object_name"),
                    from_type=postgres_catalog_object_type(row_text(row, "from_object_type")),
                    to_schema=row_text(row, "to_schema_name"),
                    to_name=row_text(row, "to_object_name"),
                    to_type=postgres_catalog_object_type(row_text(row, "to_object_type")),
                    dependency_type=optional_row_text(row, "dependency_type") or "object_dependency",
                    name=optional_row_text(row, "dependency_name"),
                )
            )

    return PostgresMetadataReadResult(
        metadata=PostgresMetadata(
            tables=tuple(tables),
            views=tuple(views),
            materialized_views=tuple(materialized_views),
            functions=tuple(functions),
            procedures=tuple(procedures),
            triggers=tuple(triggers),
            foreign_keys=tuple(foreign_keys),
            dependencies=tuple(dependencies),
        ),
        errors=budget.errors,
    )


@dataclass
class MetadataReadBudget:
    """Tracks the configured metadata row cap across catalog queries."""

    limit: int
    engine_label: str
    consumed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(self.limit - self.consumed, 0)

    @property
    def has_remaining(self) -> bool:
        return self.remaining > 0

    def record(self, row_count: int, metadata_source: str) -> None:
        remaining_before = self.remaining
        self.consumed += row_count
        if row_count >= remaining_before:
            self.errors.append(
                f"{self.engine_label} metadata row limit reached while reading {metadata_source}; "
                "increase max_metadata_rows to inspect more metadata."
            )


def fetch_sqlserver_rows(
    cursor: Any,
    query: str,
    params: tuple[str, ...],
    budget: MetadataReadBudget,
    metadata_source: str,
) -> list[Any]:
    rows = list(cursor.execute(query, *params).fetchall())
    budget.record(len(rows), metadata_source)
    return rows


def fetch_postgres_rows(
    cursor: Any,
    query: str,
    params: tuple[Any, ...],
    budget: MetadataReadBudget,
    metadata_source: str,
) -> list[Any]:
    cursor.execute(query, params)
    rows = list(cursor.fetchall())
    budget.record(len(rows), metadata_source)
    return rows


def sqlserver_trigger_rows(rows: list[Any]) -> list[SqlServerTriggerRow]:
    triggers: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            row_text(row, "schema_name"),
            row_text(row, "trigger_name"),
            row_text(row, "table_schema_name"),
            row_text(row, "table_name"),
        )
        trigger = triggers.setdefault(
            key,
            {
                "events": set(),
                "is_disabled": row_bool(row, "is_disabled"),
            },
        )
        event_name = optional_row_text(row, "event_name")
        if event_name:
            trigger["events"].add(normalize_trigger_event(event_name))

    return [
        SqlServerTriggerRow(
            schema=schema,
            name=name,
            table_schema=table_schema,
            table=table,
            events=tuple(sorted(trigger["events"])),
            is_disabled=bool(trigger["is_disabled"]),
        )
        for (schema, name, table_schema, table), trigger in triggers.items()
    ]


def sqlserver_objects_query(limit: int, schemas: tuple[str, ...], object_types: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("s", schemas)
    object_type_filter = sqlserver_in_filter("o.type", len(object_types))
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  s.name AS schema_name,
  o.name AS object_name,
  o.type AS object_type
FROM sys.objects AS o
JOIN sys.schemas AS s ON o.schema_id = s.schema_id
WHERE o.is_ms_shipped = 0
  AND {object_type_filter}
  {schema_filter}
ORDER BY s.name, o.name
"""


def sqlserver_foreign_keys_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("ps", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  ps.name AS schema_name,
  pt.name AS table_name,
  rs.name AS referenced_schema_name,
  rt.name AS referenced_table_name,
  fk.name AS constraint_name
FROM sys.foreign_keys AS fk
JOIN sys.tables AS pt ON fk.parent_object_id = pt.object_id
JOIN sys.schemas AS ps ON pt.schema_id = ps.schema_id
JOIN sys.tables AS rt ON fk.referenced_object_id = rt.object_id
JOIN sys.schemas AS rs ON rt.schema_id = rs.schema_id
WHERE pt.is_ms_shipped = 0
  AND rt.is_ms_shipped = 0
  {schema_filter}
ORDER BY ps.name, pt.name, fk.name
"""


def sqlserver_triggers_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("parent_schema", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  trigger_schema.name AS schema_name,
  trigger_object.name AS trigger_name,
  parent_schema.name AS table_schema_name,
  parent_table.name AS table_name,
  trigger_event.type_desc AS event_name,
  trigger_definition.is_disabled AS is_disabled
FROM sys.triggers AS trigger_definition
JOIN sys.objects AS trigger_object ON trigger_definition.object_id = trigger_object.object_id
JOIN sys.schemas AS trigger_schema ON trigger_object.schema_id = trigger_schema.schema_id
JOIN sys.tables AS parent_table ON trigger_definition.parent_id = parent_table.object_id
JOIN sys.schemas AS parent_schema ON parent_table.schema_id = parent_schema.schema_id
LEFT JOIN sys.trigger_events AS trigger_event ON trigger_definition.object_id = trigger_event.object_id
WHERE trigger_definition.parent_class = 1
  AND trigger_definition.is_ms_shipped = 0
  AND parent_table.is_ms_shipped = 0
  {schema_filter}
ORDER BY trigger_schema.name, trigger_object.name, trigger_event.type_desc
"""


def sqlserver_dependencies_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = sqlserver_schema_filter("referencing_schema", schemas)
    return f"""
SELECT TOP ({safe_sql_limit(limit)})
  referencing_schema.name AS from_schema_name,
  referencing_object.name AS from_object_name,
  referencing_object.type AS from_object_type,
  COALESCE(referenced_schema.name, d.referenced_schema_name) AS to_schema_name,
  COALESCE(referenced_object.name, d.referenced_entity_name) AS to_object_name,
  referenced_object.type AS to_object_type,
  d.referenced_class_desc AS dependency_name
FROM sys.sql_expression_dependencies AS d
JOIN sys.objects AS referencing_object ON d.referencing_id = referencing_object.object_id
JOIN sys.schemas AS referencing_schema ON referencing_object.schema_id = referencing_schema.schema_id
LEFT JOIN sys.objects AS referenced_object ON d.referenced_id = referenced_object.object_id
LEFT JOIN sys.schemas AS referenced_schema ON referenced_object.schema_id = referenced_schema.schema_id
WHERE referencing_object.is_ms_shipped = 0
  AND d.referenced_entity_name IS NOT NULL
  {schema_filter}
ORDER BY referencing_schema.name, referencing_object.name, d.referenced_entity_name
"""


def postgres_class_objects_query(limit: int, schemas: tuple[str, ...], relkinds: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    relkind_filter = postgres_in_filter("c.relkind", len(relkinds))
    return f"""
SELECT
  n.nspname AS schema_name,
  c.relname AS object_name,
  CASE c.relkind
    WHEN 'm' THEN 'materialized_view'
    WHEN 'v' THEN 'view'
    ELSE 'table'
  END AS object_type
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE {relkind_filter}
  {schema_filter}
ORDER BY n.nspname, c.relname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_proc_objects_query(limit: int, schemas: tuple[str, ...], prokinds: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    prokind_filter = postgres_in_filter("p.prokind", len(prokinds))
    return f"""
SELECT
  n.nspname AS schema_name,
  p.proname AS object_name,
  CASE p.prokind
    WHEN 'p' THEN 'procedure'
    ELSE 'function'
  END AS object_type
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
WHERE {prokind_filter}
  {schema_filter}
ORDER BY n.nspname, p.proname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_foreign_keys_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("n", schemas)
    return f"""
SELECT
  n.nspname AS schema_name,
  c.relname AS table_name,
  rn.nspname AS referenced_schema_name,
  rc.relname AS referenced_table_name,
  con.conname AS constraint_name
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_class AS rc ON rc.oid = con.confrelid
JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace
WHERE con.contype = 'f'
  {schema_filter}
ORDER BY n.nspname, c.relname, con.conname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_triggers_query(limit: int, schemas: tuple[str, ...]) -> str:
    schema_filter = postgres_schema_filter("table_schema", schemas)
    return f"""
SELECT
  table_schema.nspname AS schema_name,
  trigger_definition.tgname AS trigger_name,
  table_schema.nspname AS table_schema_name,
  parent_table.relname AS table_name,
  ((trigger_definition.tgtype::int & 4) <> 0) AS fires_insert,
  ((trigger_definition.tgtype::int & 8) <> 0) AS fires_delete,
  ((trigger_definition.tgtype::int & 16) <> 0) AS fires_update,
  ((trigger_definition.tgtype::int & 32) <> 0) AS fires_truncate,
  trigger_definition.tgenabled = 'D' AS is_disabled,
  function_schema.nspname AS function_schema_name,
  trigger_function.proname AS function_name
FROM pg_catalog.pg_trigger AS trigger_definition
JOIN pg_catalog.pg_class AS parent_table ON parent_table.oid = trigger_definition.tgrelid
JOIN pg_catalog.pg_namespace AS table_schema ON table_schema.oid = parent_table.relnamespace
JOIN pg_catalog.pg_proc AS trigger_function ON trigger_function.oid = trigger_definition.tgfoid
JOIN pg_catalog.pg_namespace AS function_schema ON function_schema.oid = trigger_function.pronamespace
WHERE NOT trigger_definition.tgisinternal
  {schema_filter}
ORDER BY table_schema.nspname, parent_table.relname, trigger_definition.tgname
LIMIT {safe_sql_limit(limit)}
"""


def postgres_dependencies_query(limit: int, schemas: tuple[str, ...]) -> str:
    view_schema_filter = postgres_schema_filter("n", schemas)
    routine_schema_filter = postgres_schema_filter("pn", schemas)
    return f"""
SELECT *
FROM (
  SELECT
    n.nspname AS from_schema_name,
    v.relname AS from_object_name,
    CASE v.relkind
      WHEN 'm' THEN 'materialized_view'
      ELSE 'view'
    END AS from_object_type,
    rn.nspname AS to_schema_name,
    rc.relname AS to_object_name,
    CASE rc.relkind
      WHEN 'm' THEN 'materialized_view'
      WHEN 'v' THEN 'view'
      ELSE 'table'
    END AS to_object_type,
    dep.deptype::text AS dependency_name,
    'object_dependency' AS dependency_type
  FROM pg_catalog.pg_rewrite AS rw
  JOIN pg_catalog.pg_class AS v ON v.oid = rw.ev_class
  JOIN pg_catalog.pg_namespace AS n ON n.oid = v.relnamespace
  JOIN pg_catalog.pg_depend AS dep ON dep.objid = rw.oid
  JOIN pg_catalog.pg_class AS rc ON rc.oid = dep.refobjid
  JOIN pg_catalog.pg_namespace AS rn ON rn.oid = rc.relnamespace
  WHERE v.relkind IN ('m', 'v')
    AND dep.classid = 'pg_rewrite'::regclass
    AND dep.refclassid = 'pg_class'::regclass
    AND dep.deptype IN ('a', 'n')
    AND rc.oid <> v.oid
    {view_schema_filter}
    {postgres_user_schema_filter("rn")}

  UNION ALL

  SELECT
    pn.nspname AS from_schema_name,
    p.proname AS from_object_name,
    CASE p.prokind
      WHEN 'p' THEN 'procedure'
      ELSE 'function'
    END AS from_object_type,
    rpn.nspname AS to_schema_name,
    rp.proname AS to_object_name,
    CASE rp.prokind
      WHEN 'p' THEN 'procedure'
      ELSE 'function'
    END AS to_object_type,
    dep.deptype::text AS dependency_name,
    'object_dependency' AS dependency_type
  FROM pg_catalog.pg_depend AS dep
  JOIN pg_catalog.pg_proc AS p ON p.oid = dep.objid
  JOIN pg_catalog.pg_namespace AS pn ON pn.oid = p.pronamespace
  JOIN pg_catalog.pg_proc AS rp ON rp.oid = dep.refobjid
  JOIN pg_catalog.pg_namespace AS rpn ON rpn.oid = rp.pronamespace
  WHERE dep.classid = 'pg_proc'::regclass
    AND dep.refclassid = 'pg_proc'::regclass
    AND dep.deptype IN ('a', 'n')
    AND rp.oid <> p.oid
    {routine_schema_filter}
    {postgres_user_schema_filter("rpn")}
) AS dependencies
ORDER BY from_schema_name, from_object_name, to_schema_name, to_object_name
LIMIT {safe_sql_limit(limit)}
"""


def sqlserver_schema_filter(schema_alias: str, schemas: tuple[str, ...]) -> str:
    if not schemas:
        return ""
    return f"AND {schema_alias}.name IN ({', '.join('?' for _schema in schemas)})"


def sqlserver_in_filter(column_name: str, count: int) -> str:
    return f"{column_name} IN ({', '.join('?' for _index in range(count))})"


def postgres_schema_filter(schema_alias: str, schemas: tuple[str, ...]) -> str:
    if schemas:
        return f"AND {schema_alias}.nspname IN ({', '.join('%s' for _schema in schemas)})"
    return postgres_user_schema_filter(schema_alias)


def postgres_user_schema_filter(schema_alias: str) -> str:
    return (
        f"AND {schema_alias}.nspname NOT IN ('information_schema', 'pg_catalog') "
        f"AND {schema_alias}.nspname NOT LIKE 'pg_toast%'"
    )


def postgres_in_filter(column_name: str, count: int) -> str:
    return f"{column_name} IN ({', '.join('%s' for _index in range(count))})"


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


def postgres_class_relkind_filter(include_object_types: tuple[str, ...]) -> tuple[str, ...]:
    requested = postgres_requested_object_types(include_object_types)
    relkinds: list[str] = []
    for include_type in requested:
        relkinds.extend(POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE.get(include_type, ()))
    return tuple(dict.fromkeys(relkinds))


def postgres_proc_kind_filter(include_object_types: tuple[str, ...]) -> tuple[str, ...]:
    requested = postgres_requested_object_types(include_object_types)
    prokinds: list[str] = []
    for include_type in requested:
        prokinds.extend(POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE.get(include_type, ()))
    return tuple(dict.fromkeys(prokinds))


def postgres_requested_object_types(include_object_types: tuple[str, ...]) -> list[str]:
    requested = list(include_object_types or POSTGRES_DEFAULT_INCLUDE_OBJECT_TYPES)
    if "foreign_key" in requested and "table" not in requested:
        requested.append("table")
    if "dependency" in requested:
        requested.extend(
            object_type
            for object_type in (*POSTGRES_CLASS_RELKINDS_BY_INCLUDE_TYPE, *POSTGRES_PROC_KINDS_BY_INCLUDE_TYPE)
            if object_type not in requested
        )
    return requested


def include_database_object_type(include_object_types: tuple[str, ...], object_type: str) -> bool:
    return not include_object_types or object_type in include_object_types


def include_database_object_type_or_dependency(include_object_types: tuple[str, ...], object_type: str) -> bool:
    return include_database_object_type(include_object_types, object_type) or "dependency" in include_object_types


def sqlserver_catalog_object_type(value: str | None) -> str:
    if not value:
        return "sql_object"
    return DATABASE_OBJECT_TYPE_ALIASES.get(normalize_metadata_value(value), "sql_object")


def postgres_catalog_object_type(value: str | None) -> str:
    if not value:
        return "sql_object"
    return DATABASE_OBJECT_TYPE_ALIASES.get(normalize_metadata_value(value), "sql_object")


def safe_sql_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("SQL metadata query limit must be a positive integer.")
    return value


def row_text(row: Any, field_name: str) -> str:
    value = optional_row_text(row, field_name)
    if value is None:
        raise ValueError(f"Database metadata row is missing {field_name}.")
    return value


def optional_row_text(row: Any, field_name: str) -> str | None:
    value = row_value(row, field_name)
    if value is None:
        return None
    return required_text(str(value), field_name)


def row_value(row: Any, field_name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(field_name)
    return getattr(row, field_name, None)


def row_bool(row: Any, field_name: str) -> bool:
    value = row_value(row, field_name)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return normalize_metadata_value(value) in {"1", "true", "t", "yes", "y"}
    return False


def postgres_trigger_events(row: Any) -> tuple[str, ...]:
    events = [
        event_name
        for field_name, event_name in (
            ("fires_insert", "INSERT"),
            ("fires_update", "UPDATE"),
            ("fires_delete", "DELETE"),
            ("fires_truncate", "TRUNCATE"),
        )
        if row_bool(row, field_name)
    ]
    return tuple(events)


def normalize_trigger_event(value: str) -> str:
    return normalize_metadata_value(value).upper()


def trigger_source_name(table: str, trigger_name: str) -> str:
    return f"{normalize_sql_identifier(table)}.{normalize_sql_identifier(trigger_name)}"


def trigger_source_schema(schema: str, table: str) -> str:
    return f"{normalize_sql_identifier(schema)}.{normalize_sql_identifier(table)}"


def set_cursor_timeout(cursor: Any, timeout: int) -> None:
    try:
        cursor.timeout = timeout
    except Exception:
        return


def set_postgres_statement_timeout(cursor: Any, timeout: int) -> None:
    cursor.execute("SET statement_timeout = %s", (timeout * 1000,))


def close_database_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def normalize_database_engine(engine: str) -> str:
    return required_text(engine, "database engine").lower()


def scan_sqlserver_metadata(source_name: str, metadata: SqlServerMetadata) -> DatabaseScanResult:
    """Convert SQL Server catalog metadata rows into typed facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseScanResult()

    entities_by_ref: dict[EntityReference, EntityFact] = {}
    for entity_type, rows in sqlserver_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_ref,
                sqlserver_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=SQLSERVER_OBJECT_METADATA_SOURCES[entity_type],
                ),
            )
    for row in metadata.triggers:
        add_entity(entities_by_ref, sqlserver_trigger_entity(source_name, row))

    result.entities = list(entities_by_ref.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = foreign_key_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.triggers:
        edge_result = sqlserver_trigger_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.dependencies:
        edge_result = dependency_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    return result


def sqlserver_object_groups(
    metadata: SqlServerMetadata,
) -> tuple[tuple[str, tuple[SqlServerObjectRow, ...]], ...]:
    return (
        ("sql_table", metadata.tables),
        ("sql_view", metadata.views),
        ("stored_procedure", metadata.stored_procedures),
        ("sql_function", metadata.functions),
    )


def sqlserver_object_entity(
    source_name: str,
    entity_type: str,
    row: SqlServerObjectRow,
    metadata_source: str,
) -> EntityFact:
    return database_object_entity(
        source_name=source_name,
        database_engine=SQLSERVER_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
    )


def scan_postgres_metadata(source_name: str, metadata: PostgresMetadata) -> DatabaseScanResult:
    """Convert PostgreSQL catalog metadata rows into typed facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseScanResult()

    entities_by_ref: dict[EntityReference, EntityFact] = {}
    for entity_type, rows, metadata_source, extra_properties in postgres_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_ref,
                postgres_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=metadata_source,
                    extra_properties=extra_properties,
                ),
            )
    for row in metadata.triggers:
        add_entity(entities_by_ref, postgres_trigger_entity(source_name, row))

    result.entities = list(entities_by_ref.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = postgres_foreign_key_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    for row in metadata.triggers:
        edge_result = postgres_trigger_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)
        trigger_function_dependency = postgres_trigger_function_dependency(row)
        if trigger_function_dependency is not None:
            append_edge_result(result, postgres_dependency_edge(source_name, trigger_function_dependency, entity_index))

    for row in metadata.dependencies:
        edge_result = postgres_dependency_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

    return result


def postgres_object_groups(
    metadata: PostgresMetadata,
) -> tuple[tuple[str, tuple[PostgresObjectRow, ...], str, dict[str, Any]], ...]:
    return (
        ("sql_table", metadata.tables, "pg_class", {}),
        ("sql_view", metadata.views, "pg_class", {"postgres_relkind": "view"}),
        ("sql_view", metadata.materialized_views, "pg_class", {"postgres_relkind": "materialized_view"}),
        ("stored_procedure", metadata.procedures, "pg_proc", {}),
        ("sql_function", metadata.functions, "pg_proc", {}),
    )


def postgres_object_entity(
    source_name: str,
    entity_type: str,
    row: PostgresObjectRow,
    metadata_source: str,
    extra_properties: dict[str, Any],
) -> EntityFact:
    return database_object_entity(
        source_name=source_name,
        database_engine=POSTGRES_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
        extra_properties=extra_properties,
    )


def sqlserver_trigger_entity(source_name: str, row: SqlServerTriggerRow) -> EntityFact:
    return database_trigger_entity(
        source_name=source_name,
        database_engine=SQLSERVER_ENGINE,
        schema=row.schema,
        name=row.name,
        table_schema=row.table_schema,
        table=row.table,
        metadata_source="sys.triggers",
        events=row.events,
        is_enabled=None if row.is_disabled is None else not row.is_disabled,
    )


def postgres_trigger_entity(source_name: str, row: PostgresTriggerRow) -> EntityFact:
    return database_trigger_entity(
        source_name=source_name,
        database_engine=POSTGRES_ENGINE,
        schema=row.schema,
        name=row.name,
        table_schema=row.table_schema,
        table=row.table,
        metadata_source="pg_trigger",
        events=row.events,
        is_enabled=row.is_enabled,
        extra_properties={
            "trigger_function": (
                database_full_name(row.function_schema, row.function_name)
                if row.function_schema and row.function_name
                else None
            )
        },
    )


def database_trigger_entity(
    source_name: str,
    database_engine: str,
    schema: str,
    name: str,
    table_schema: str,
    table: str,
    metadata_source: str,
    events: tuple[str, ...],
    is_enabled: bool | None,
    extra_properties: dict[str, Any] | None = None,
) -> EntityFact:
    trigger_name = normalize_sql_identifier(name)
    table_full_name = database_full_name(table_schema, table)
    full_name = database_trigger_full_name(table_schema, table, trigger_name)
    trigger_properties = {
        "schema": normalize_sql_identifier(schema),
        "object_name": trigger_name,
        "full_name": full_name,
        "schema_state": CURRENT_DATABASE_SCHEMA_STATE,
        "database_engine": database_engine,
        "metadata_source": metadata_source,
        "trigger_table": table_full_name,
        "trigger_events": list(events),
        "trigger_enabled": is_enabled,
        **(extra_properties or {}),
    }
    return EntityFact(
        entity_type="sql_trigger",
        name=full_name,
        source_name=source_name,
        aliases=frozenset(
            {
                trigger_name,
                database_full_name(schema, trigger_name),
                trigger_source_name(table, trigger_name),
            }
        ),
        properties={key: value for key, value in trigger_properties.items() if value is not None},
    )


def database_object_entity(
    source_name: str,
    database_engine: str,
    entity_type: str,
    schema: str,
    name: str,
    metadata_source: str,
    extra_properties: dict[str, Any] | None = None,
) -> EntityFact:
    full_name = database_full_name(schema, name)
    schema, short_name = split_sql_name(full_name)
    return EntityFact(
        entity_type=entity_type,
        name=full_name,
        source_name=source_name,
        aliases=frozenset({short_name}),
        properties={
            "schema": schema,
            "object_name": short_name,
            "full_name": full_name,
            "schema_state": CURRENT_DATABASE_SCHEMA_STATE,
            "database_engine": database_engine,
            "metadata_source": metadata_source,
            **(extra_properties or {}),
        },
    )


def foreign_key_edge(
    source_name: str,
    row: SqlServerForeignKeyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = sqlserver_full_name(row.schema, row.table)
    target_full_name = sqlserver_full_name(row.referenced_schema, row.referenced_table)
    source_match = find_entity(entity_index, "sql_table", source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="SQL Server",
                source_name=source_name,
                metadata_source="sys.foreign_keys",
                relationship_name="foreign key",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    return EdgeBuildResult(
        edge=sqlserver_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, "sql_table", target_full_name),
            target_name=target_full_name,
            target_type="sql_table",
            edge_type="REFERENCES_SQL_OBJECT",
            source_name=source_name,
            operation="FOREIGN_KEY",
            database_object_type="sql_object",
            dependency_scope="schema",
            interaction_kind="sql_schema_reference",
            metadata_source="sys.foreign_keys",
            identity_key=metadata_identity_key("foreign_key", source_full_name, target_full_name, row.name),
            extra_properties={"constraint_name": row.name},
        )
    )


def sqlserver_trigger_edge(
    source_name: str,
    row: SqlServerTriggerRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    return trigger_edge(
        engine_label="SQL Server",
        source_name=source_name,
        metadata_source="sys.triggers",
        database_engine=SQLSERVER_ENGINE,
        parser=SQLSERVER_METADATA_PARSER,
        trigger_schema=row.schema,
        trigger_name=row.name,
        table_schema=row.table_schema,
        table_name=row.table,
        events=row.events,
        is_enabled=None if row.is_disabled is None else not row.is_disabled,
        entity_index=entity_index,
    )


def postgres_trigger_edge(
    source_name: str,
    row: PostgresTriggerRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    return trigger_edge(
        engine_label="PostgreSQL",
        source_name=source_name,
        metadata_source="pg_trigger",
        database_engine=POSTGRES_ENGINE,
        parser=POSTGRES_METADATA_PARSER,
        trigger_schema=row.schema,
        trigger_name=row.name,
        table_schema=row.table_schema,
        table_name=row.table,
        events=row.events,
        is_enabled=row.is_enabled,
        entity_index=entity_index,
    )


def postgres_trigger_function_dependency(row: PostgresTriggerRow) -> PostgresDependencyRow | None:
    if not row.function_schema or not row.function_name:
        return None
    return PostgresDependencyRow(
        from_schema=trigger_source_schema(row.table_schema, row.table),
        from_name=row.name,
        from_type="trigger",
        to_schema=row.function_schema,
        to_name=row.function_name,
        to_type="function",
        dependency_type="execute",
        name=row.name,
    )


def trigger_edge(
    engine_label: str,
    source_name: str,
    metadata_source: str,
    database_engine: str,
    parser: str,
    trigger_schema: str,
    trigger_name: str,
    table_schema: str,
    table_name: str,
    events: tuple[str, ...],
    is_enabled: bool | None,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    trigger_full_name = database_trigger_full_name(table_schema, table_name, trigger_name)
    table_full_name = database_full_name(table_schema, table_name)
    source_match = find_entity(entity_index, "sql_trigger", trigger_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label=engine_label,
                source_name=source_name,
                metadata_source=metadata_source,
                relationship_name="trigger",
                source_object=database_full_name(trigger_schema, trigger_name),
                target_object=table_full_name,
                candidates=source_match.candidates,
            )
        )

    return EdgeBuildResult(
        edge=database_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, "sql_table", table_full_name),
            target_name=table_full_name,
            target_type="sql_table",
            edge_type="TRIGGERS_ON_SQL_OBJECT",
            source_name=source_name,
            operation="TRIGGER_ON",
            database_object_type="sql_table",
            dependency_scope="runtime",
            interaction_kind="sql_trigger",
            metadata_source=metadata_source,
            identity_key=metadata_identity_key("trigger", trigger_full_name, table_full_name),
            database_engine=database_engine,
            parser=parser,
            extra_properties={
                "trigger_events": list(events),
                "trigger_enabled": is_enabled,
                "trigger_name": trigger_name,
            },
        )
    )


def missing_source_error(
    engine_label: str,
    source_name: str,
    metadata_source: str,
    relationship_name: str,
    source_object: str,
    target_object: str,
    candidates: tuple[EntityFact, ...],
) -> DatabaseGraphError:
    if candidates:
        message = f"Ambiguous source entity for {engine_label} {relationship_name}: {source_object}"
        code = "ambiguous_source_entity"
    else:
        message = f"Missing source entity for {engine_label} {relationship_name}: {source_object}"
        code = "missing_source_entity"
    return DatabaseGraphError(
        code=code,
        message=message,
        source_name=source_name,
        metadata_source=metadata_source,
        source_object=source_object,
        target_object=target_object,
    )


def dependency_edge(
    source_name: str,
    row: SqlServerDependencyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = sqlserver_full_name(row.from_schema, row.from_name)
    target_full_name = sqlserver_full_name(row.to_schema, row.to_name)
    source_match = find_entity(entity_index, graph_entity_type(row.from_type, "SQL Server"), source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="SQL Server",
                source_name=source_name,
                metadata_source="sys.sql_expression_dependencies",
                relationship_name="dependency",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    dependency_type = normalize_metadata_value(row.dependency_type)
    edge_type = "CALLS_SQL" if dependency_type in EXECUTE_DEPENDENCY_TYPES else "REFERENCES_SQL_OBJECT"
    target_type = graph_entity_type(row.to_type, "SQL Server")
    if edge_type == "CALLS_SQL" and target_type == "sql_object":
        target_type = "stored_procedure"
    return EdgeBuildResult(
        edge=sqlserver_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, target_type, target_full_name),
            target_name=target_full_name,
            target_type=target_type,
            edge_type=edge_type,
            source_name=source_name,
            operation="EXECUTE" if edge_type == "CALLS_SQL" else "MODULE_REFERENCE",
            database_object_type=target_type,
            dependency_scope="runtime" if edge_type == "CALLS_SQL" else "schema",
            interaction_kind="sql_reference" if edge_type == "CALLS_SQL" else "sql_schema_reference",
            metadata_source="sys.sql_expression_dependencies",
            identity_key=metadata_identity_key(
                "dependency",
                source_full_name,
                target_full_name,
                row.dependency_type,
                row.name,
            ),
            extra_properties={
                "dependency_name": row.name,
                "dependency_type": row.dependency_type,
            },
        )
    )


def postgres_foreign_key_edge(
    source_name: str,
    row: PostgresForeignKeyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = postgres_full_name(row.schema, row.table)
    target_full_name = postgres_full_name(row.referenced_schema, row.referenced_table)
    source_match = find_entity(entity_index, "sql_table", source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="PostgreSQL",
                source_name=source_name,
                metadata_source="pg_constraint",
                relationship_name="foreign key",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    return EdgeBuildResult(
        edge=database_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, "sql_table", target_full_name),
            target_name=target_full_name,
            target_type="sql_table",
            edge_type="REFERENCES_SQL_OBJECT",
            source_name=source_name,
            operation="FOREIGN_KEY",
            database_object_type="sql_object",
            dependency_scope="schema",
            interaction_kind="sql_schema_reference",
            metadata_source="pg_constraint",
            identity_key=metadata_identity_key("foreign_key", source_full_name, target_full_name, row.name),
            database_engine=POSTGRES_ENGINE,
            parser=POSTGRES_METADATA_PARSER,
            extra_properties={"constraint_name": row.name},
        )
    )


def postgres_dependency_edge(
    source_name: str,
    row: PostgresDependencyRow,
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
) -> EdgeBuildResult:
    source_full_name = postgres_full_name(row.from_schema, row.from_name)
    target_full_name = postgres_full_name(row.to_schema, row.to_name)
    source_match = find_entity(entity_index, graph_entity_type(row.from_type, "PostgreSQL"), source_full_name)
    if source_match.entity is None:
        return EdgeBuildResult(
            error=missing_source_error(
                engine_label="PostgreSQL",
                source_name=source_name,
                metadata_source="pg_depend",
                relationship_name="dependency",
                source_object=source_full_name,
                target_object=target_full_name,
                candidates=source_match.candidates,
            )
        )

    dependency_type = normalize_metadata_value(row.dependency_type)
    edge_type = "CALLS_SQL" if dependency_type in EXECUTE_DEPENDENCY_TYPES else "REFERENCES_SQL_OBJECT"
    target_type = graph_entity_type(row.to_type, "PostgreSQL")
    if edge_type == "CALLS_SQL" and target_type == "sql_object":
        target_type = "stored_procedure"
    return EdgeBuildResult(
        edge=database_metadata_edge(
            source_entity=source_match.entity,
            target_match=find_entity(entity_index, target_type, target_full_name),
            target_name=target_full_name,
            target_type=target_type,
            edge_type=edge_type,
            source_name=source_name,
            operation="EXECUTE" if edge_type == "CALLS_SQL" else "OBJECT_DEPENDENCY",
            database_object_type=target_type,
            dependency_scope="runtime" if edge_type == "CALLS_SQL" else "schema",
            interaction_kind="sql_reference" if edge_type == "CALLS_SQL" else "sql_schema_reference",
            metadata_source="pg_depend",
            identity_key=metadata_identity_key(
                "dependency",
                source_full_name,
                target_full_name,
                row.dependency_type,
                row.name,
            ),
            database_engine=POSTGRES_ENGINE,
            parser=POSTGRES_METADATA_PARSER,
            extra_properties={
                "dependency_name": row.name,
                "dependency_type": row.dependency_type,
            },
        )
    )


def sqlserver_metadata_edge(
    source_entity: EntityFact,
    target_match: EntityMatch,
    target_name: str,
    target_type: str,
    edge_type: str,
    source_name: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str,
    interaction_kind: str,
    metadata_source: str,
    identity_key: str,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return database_metadata_edge(
        source_entity=source_entity,
        target_match=target_match,
        target_name=target_name,
        target_type=target_type,
        edge_type=edge_type,
        source_name=source_name,
        operation=operation,
        database_object_type=database_object_type,
        dependency_scope=dependency_scope,
        interaction_kind=interaction_kind,
        metadata_source=metadata_source,
        identity_key=identity_key,
        database_engine=SQLSERVER_ENGINE,
        parser=SQLSERVER_METADATA_PARSER,
        extra_properties=extra_properties,
    )


def database_metadata_edge(
    source_entity: EntityFact,
    target_match: EntityMatch,
    target_name: str,
    target_type: str,
    edge_type: str,
    source_name: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str,
    interaction_kind: str,
    metadata_source: str,
    identity_key: str,
    database_engine: str,
    parser: str,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = database_interaction_properties(
        raw_target=target_name,
        operation=operation,
        database_object_type=database_object_type,
        dependency_scope=dependency_scope,
        interaction_kind=interaction_kind,
        metadata_source=metadata_source,
        database_engine=database_engine,
        extra_properties=extra_properties or {},
    )
    if target_match.is_ambiguous:
        properties["resolution_status"] = "ambiguous"
        properties["resolution_candidates"] = resolution_candidate_properties(target_match.candidates)
    target_entity = target_match.entity
    return RelationshipFact(
        from_ref=source_entity.reference,
        to_ref=target_entity.reference if target_entity else EntityReference(entity_type=target_type, name=target_name),
        edge_type=edge_type,
        evidence=Evidence(source_name=source_name, parser=parser, confidence="high"),
        identity_key=identity_key,
        properties=properties,
        resolved=target_entity is not None,
    )


def sqlserver_interaction_properties(
    raw_target: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str,
    interaction_kind: str,
    metadata_source: str,
    extra_properties: dict[str, Any],
) -> dict[str, Any]:
    return database_interaction_properties(
        raw_target=raw_target,
        operation=operation,
        database_object_type=database_object_type,
        dependency_scope=dependency_scope,
        interaction_kind=interaction_kind,
        metadata_source=metadata_source,
        database_engine=SQLSERVER_ENGINE,
        extra_properties=extra_properties,
    )


def database_interaction_properties(
    raw_target: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str,
    interaction_kind: str,
    metadata_source: str,
    database_engine: str,
    extra_properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "target_boundary": "database",
        "dependency_scope": dependency_scope,
        "interaction_kind": interaction_kind,
        "protocol": "sql",
        "raw_target": raw_target,
        "normalized_target": normalize_sql_identifier(raw_target),
        "sql_operation": operation.upper(),
        "database_object_type": database_object_type,
        "schema_state": CURRENT_DATABASE_SCHEMA_STATE,
        "database_engine": database_engine,
        "metadata_source": metadata_source,
        **{key: value for key, value in extra_properties.items() if value is not None},
    }


def add_entity(entities_by_ref: dict[EntityReference, EntityFact], entity: EntityFact) -> None:
    existing = entities_by_ref.get(entity.reference)
    if existing is None:
        entities_by_ref[entity.reference] = entity
        return
    entities_by_ref[entity.reference] = EntityFact(
        entity_type=existing.entity_type,
        name=existing.name,
        source_name=existing.source_name,
        file_path=existing.file_path,
        line_number=existing.line_number,
        aliases=existing.aliases | entity.aliases,
        properties={
            **existing.properties,
            **{key: value for key, value in entity.properties.items() if value is not None},
        },
    )


def append_edge_result(result: DatabaseScanResult, edge_result: EdgeBuildResult) -> None:
    if edge_result.edge is not None:
        result.edges.append(edge_result.edge)
    if edge_result.error is not None:
        result.add_error(
            edge_result.error.to_message(),
            source_name=edge_result.error.source_name,
            metadata_source=edge_result.error.metadata_source,
        )


def build_entity_index(entities: list[EntityFact]) -> dict[tuple[str | None, str], list[EntityFact]]:
    lookup: dict[tuple[str | None, str], list[EntityFact]] = {}
    for entity in entities:
        keys = {entity.name, *entity.aliases}
        full_name = entity.properties.get("full_name")
        if isinstance(full_name, str):
            keys.add(full_name)
        schema = entity.properties.get("schema")
        if isinstance(schema, str) and schema:
            keys.add(f"{schema}.{entity.name}")
        for key in keys:
            normalized = normalize_resolution_key(key)
            lookup.setdefault((entity.entity_type, normalized), []).append(entity)
            lookup.setdefault((None, normalized), []).append(entity)
    return lookup


def find_entity(
    entity_index: dict[tuple[str | None, str], list[EntityFact]],
    target_type: str | None,
    target_name: str,
) -> EntityMatch:
    normalized_target = normalize_resolution_key(target_name)
    candidates: dict[EntityReference, EntityFact] = {}
    for entity_type in database_resolution_entity_types(target_type):
        for candidate in entity_index.get((entity_type, normalized_target), []):
            candidates[candidate.reference] = candidate
    if not candidates:
        for candidate in entity_index.get((None, normalized_target), []):
            candidates[candidate.reference] = candidate
    if len(candidates) == 1:
        return EntityMatch(entity=next(iter(candidates.values())))
    return EntityMatch(candidates=tuple(candidates.values()))


def resolution_candidate_properties(candidates: tuple[EntityFact, ...]) -> list[dict[str, str]]:
    return [
        {
            "entity_type": candidate.entity_type,
            "name": candidate.name,
            "source_name": candidate.source_name,
        }
        for candidate in candidates[:25]
    ]


def normalize_resolution_key(value: str) -> str:
    return value.strip().strip("[]`\"'").lower()


def database_resolution_entity_types(target_type: str | None) -> list[str | None]:
    if target_type == "sql_object":
        return ["sql_table", "sql_view", "sql_function", "sql_trigger", "stored_procedure"]
    if target_type:
        return [target_type]
    return [None]


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
