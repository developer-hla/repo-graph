"""Pure database metadata adapters for RepoGraph."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from repo_graph.graph import Edge, Entity, normalize_key, resolution_entity_types

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
    "stored_procedure": "sys.procedures",
    "sql_function": "sys.objects",
}

POSTGRES_OBJECT_METADATA_SOURCES = {
    "sql_table": "pg_class",
    "sql_view": "pg_class",
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
    "sql_view": "sql_view",
    "stored_procedure": "stored_procedure",
    "table": "sql_table",
    "tf": "sql_function",
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


class DatabaseMetadataAdapter(Protocol):
    """Converts engine-specific metadata rows into graph facts."""

    engine: str
    metadata_parser: str

    def graph_from_metadata(self, source_name: str, metadata: object) -> DatabaseGraphFacts:
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
class SqlServerMetadata:
    """Typed SQL Server metadata rows used by the pure adapter."""

    tables: tuple[SqlServerObjectRow, ...] = ()
    views: tuple[SqlServerObjectRow, ...] = ()
    stored_procedures: tuple[SqlServerObjectRow, ...] = ()
    functions: tuple[SqlServerObjectRow, ...] = ()
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
class PostgresMetadata:
    """Typed PostgreSQL metadata rows used by the pure adapter."""

    tables: tuple[PostgresObjectRow, ...] = ()
    views: tuple[PostgresObjectRow, ...] = ()
    materialized_views: tuple[PostgresObjectRow, ...] = ()
    functions: tuple[PostgresObjectRow, ...] = ()
    procedures: tuple[PostgresObjectRow, ...] = ()
    foreign_keys: tuple[PostgresForeignKeyRow, ...] = ()
    dependencies: tuple[PostgresDependencyRow, ...] = ()


@dataclass
class DatabaseGraphFacts:
    """Graph facts emitted from a database metadata source."""

    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


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

    edge: Edge | None = None
    error: DatabaseGraphError | None = None


@dataclass(frozen=True)
class EntityMatch:
    """Entity resolution result for metadata rows."""

    entity: Entity | None = None
    candidates: tuple[Entity, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return len(self.candidates) > 1


@dataclass(frozen=True)
class SqlServerMetadataAdapter:
    """Pure SQL Server metadata adapter."""

    engine: str = SQLSERVER_ENGINE
    metadata_parser: str = SQLSERVER_METADATA_PARSER

    def graph_from_metadata(self, source_name: str, metadata: object) -> DatabaseGraphFacts:
        if not isinstance(metadata, SqlServerMetadata):
            raise TypeError("SQL Server metadata adapter requires SqlServerMetadata.")
        return graph_from_sqlserver_metadata(source_name, metadata)


@dataclass(frozen=True)
class PostgresMetadataAdapter:
    """Pure PostgreSQL metadata adapter."""

    engine: str = POSTGRES_ENGINE
    metadata_parser: str = POSTGRES_METADATA_PARSER

    def graph_from_metadata(self, source_name: str, metadata: object) -> DatabaseGraphFacts:
        if not isinstance(metadata, PostgresMetadata):
            raise TypeError("PostgreSQL metadata adapter requires PostgresMetadata.")
        return graph_from_postgres_metadata(source_name, metadata)


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


def graph_from_database_metadata(source_name: str, engine: str, metadata: object) -> DatabaseGraphFacts:
    """Convert metadata rows for any supported database engine into graph facts."""

    return database_metadata_adapter(engine).graph_from_metadata(source_name, metadata)


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


def graph_from_database_source(_request: DatabaseSourceRequest) -> DatabaseGraphFacts:
    """Live database connector entry point."""

    engine = normalize_database_engine(_request.engine)
    if engine == SQLSERVER_ENGINE:
        return graph_from_sqlserver_source(_request)
    return DatabaseGraphFacts(errors=[database_connector_unavailable_message(_request.source_name, engine)])


def graph_from_sqlserver_source(
    request: DatabaseSourceRequest,
    connect: Callable[[str, int], Any] | None = None,
) -> DatabaseGraphFacts:
    """Read SQL Server catalog metadata and convert it into graph facts."""

    connection_env = request.connection_env.strip()
    if not connection_env:
        return DatabaseGraphFacts(errors=[f"Database source '{request.source_name}' connection_env is not configured."])
    connection_string = os.environ.get(connection_env)
    if not connection_string:
        return DatabaseGraphFacts(
            errors=[f"Database source '{request.source_name}' connection_env is not set in the runtime environment."]
        )
    if connect is None and not sqlserver_driver_available():
        return DatabaseGraphFacts(
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
        return DatabaseGraphFacts(
            errors=[
                f"SQL Server metadata connection failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )

    try:
        metadata_result = read_sqlserver_metadata(connection, request)
    except Exception as exc:
        return DatabaseGraphFacts(
            errors=[
                f"SQL Server metadata read failed for '{request.source_name}': "
                f"{safe_database_error_text(exc, connection_string)}"
            ]
        )
    finally:
        close_database_connection(connection)

    facts = graph_from_sqlserver_metadata(request.source_name, metadata_result.metadata)
    facts.errors.extend(metadata_result.errors)
    return facts


def sqlserver_driver_available() -> bool:
    return importlib.util.find_spec("pyodbc") is not None


def connect_to_sqlserver(connection_string: str, timeout: int) -> Any:
    pyodbc = __import__("pyodbc")
    return pyodbc.connect(connection_string, timeout=timeout, autocommit=True)


def safe_database_error_text(exc: Exception, connection_string: str) -> str:
    return f"{type(exc).__name__}: {str(exc).replace(connection_string, '[redacted]')}"


def read_sqlserver_metadata(connection: Any, request: DatabaseSourceRequest) -> SqlServerMetadataReadResult:
    """Read bounded SQL Server catalog metadata from an open connection."""

    budget = MetadataReadBudget(request.max_metadata_rows or DEFAULT_DATABASE_MAX_METADATA_ROWS)
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
            foreign_keys=tuple(foreign_keys),
            dependencies=tuple(dependencies),
        ),
        errors=budget.errors,
    )


@dataclass
class MetadataReadBudget:
    """Tracks the configured metadata row cap across catalog queries."""

    limit: int
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
                f"SQL Server metadata row limit reached while reading {metadata_source}; "
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


def sqlserver_schema_filter(schema_alias: str, schemas: tuple[str, ...]) -> str:
    if not schemas:
        return ""
    return f"AND {schema_alias}.name IN ({', '.join('?' for _schema in schemas)})"


def sqlserver_in_filter(column_name: str, count: int) -> str:
    return f"{column_name} IN ({', '.join('?' for _index in range(count))})"


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


def include_database_object_type(include_object_types: tuple[str, ...], object_type: str) -> bool:
    return not include_object_types or object_type in include_object_types


def sqlserver_catalog_object_type(value: str | None) -> str:
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
        raise ValueError(f"SQL Server metadata row is missing {field_name}.")
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


def set_cursor_timeout(cursor: Any, timeout: int) -> None:
    try:
        cursor.timeout = timeout
    except Exception:
        return


def close_database_connection(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def normalize_database_engine(engine: str) -> str:
    return required_text(engine, "database engine").lower()


def graph_from_sqlserver_metadata(source_name: str, metadata: SqlServerMetadata) -> DatabaseGraphFacts:
    """Convert SQL Server catalog metadata rows into RepoGraph facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseGraphFacts()

    entities_by_id: dict[str, Entity] = {}
    for entity_type, rows in sqlserver_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_id,
                sqlserver_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=SQLSERVER_OBJECT_METADATA_SOURCES[entity_type],
                ),
            )

    result.entities = list(entities_by_id.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = foreign_key_edge(source_name, row, entity_index)
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
) -> Entity:
    return database_object_entity(
        source_name=source_name,
        database_engine=SQLSERVER_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
    )


def graph_from_postgres_metadata(source_name: str, metadata: PostgresMetadata) -> DatabaseGraphFacts:
    """Convert PostgreSQL catalog metadata rows into RepoGraph facts."""

    source_name = required_text(source_name, "source_name")
    result = DatabaseGraphFacts()

    entities_by_id: dict[str, Entity] = {}
    for entity_type, rows, metadata_source, extra_properties in postgres_object_groups(metadata):
        for row in rows:
            add_entity(
                entities_by_id,
                postgres_object_entity(
                    source_name=source_name,
                    entity_type=entity_type,
                    row=row,
                    metadata_source=metadata_source,
                    extra_properties=extra_properties,
                ),
            )

    result.entities = list(entities_by_id.values())
    entity_index = build_entity_index(result.entities)

    for row in metadata.foreign_keys:
        edge_result = postgres_foreign_key_edge(source_name, row, entity_index)
        append_edge_result(result, edge_result)

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
) -> Entity:
    return database_object_entity(
        source_name=source_name,
        database_engine=POSTGRES_ENGINE,
        entity_type=entity_type,
        schema=row.schema,
        name=row.name,
        metadata_source=metadata_source,
        extra_properties=extra_properties,
    )


def database_object_entity(
    source_name: str,
    database_engine: str,
    entity_type: str,
    schema: str,
    name: str,
    metadata_source: str,
    extra_properties: dict[str, Any] | None = None,
) -> Entity:
    full_name = database_full_name(schema, name)
    schema, short_name = split_sql_name(full_name)
    return Entity(
        entity_type=entity_type,
        name=full_name,
        source_name=source_name,
        aliases={short_name},
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
    entity_index: dict[tuple[str | None, str], list[Entity]],
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


def missing_source_error(
    engine_label: str,
    source_name: str,
    metadata_source: str,
    relationship_name: str,
    source_object: str,
    target_object: str,
    candidates: tuple[Entity, ...],
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
    entity_index: dict[tuple[str | None, str], list[Entity]],
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
    entity_index: dict[tuple[str | None, str], list[Entity]],
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
    entity_index: dict[tuple[str | None, str], list[Entity]],
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
    source_entity: Entity,
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
) -> Edge:
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
    source_entity: Entity,
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
) -> Edge:
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
    return Edge(
        from_entity_id=source_entity.entity_id,
        from_name=source_entity.name,
        from_type=source_entity.entity_type,
        to_name=target_entity.name if target_entity else target_name,
        to_type=target_entity.entity_type if target_entity else target_type,
        to_entity_id=target_entity.entity_id if target_entity else None,
        resolved=target_entity is not None,
        edge_type=edge_type,
        source_name=source_name,
        identity_key=identity_key,
        confidence="high",
        parser=parser,
        properties=properties,
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


def add_entity(entities_by_id: dict[str, Entity], entity: Entity) -> None:
    existing = entities_by_id.get(entity.entity_id)
    if existing is None:
        entities_by_id[entity.entity_id] = entity
        return
    existing.aliases.update(entity.aliases)
    existing.properties.update({key: value for key, value in entity.properties.items() if value is not None})


def append_edge_result(result: DatabaseGraphFacts, edge_result: EdgeBuildResult) -> None:
    if edge_result.edge is not None:
        result.edges.append(edge_result.edge)
    if edge_result.error is not None:
        result.errors.append(edge_result.error.to_message())


def build_entity_index(entities: list[Entity]) -> dict[tuple[str | None, str], list[Entity]]:
    lookup: dict[tuple[str | None, str], list[Entity]] = {}
    for entity in entities:
        keys = {entity.name, *entity.aliases}
        full_name = entity.properties.get("full_name")
        if isinstance(full_name, str):
            keys.add(full_name)
        schema = entity.properties.get("schema")
        if isinstance(schema, str) and schema:
            keys.add(f"{schema}.{entity.name}")
        for key in keys:
            normalized = normalize_key(key)
            lookup.setdefault((entity.entity_type, normalized), []).append(entity)
            lookup.setdefault((None, normalized), []).append(entity)
    return lookup


def find_entity(
    entity_index: dict[tuple[str | None, str], list[Entity]],
    target_type: str | None,
    target_name: str,
) -> EntityMatch:
    normalized_target = normalize_key(target_name)
    candidates: dict[str, Entity] = {}
    for entity_type in resolution_entity_types(target_type):
        for candidate in entity_index.get((entity_type, normalized_target), []):
            candidates[candidate.entity_id] = candidate
    if not candidates:
        for candidate in entity_index.get((None, normalized_target), []):
            candidates[candidate.entity_id] = candidate
    if len(candidates) == 1:
        return EntityMatch(entity=next(iter(candidates.values())))
    return EntityMatch(candidates=tuple(candidates.values()))


def resolution_candidate_properties(candidates: tuple[Entity, ...]) -> list[dict[str, str]]:
    return [
        {
            "entity_id": candidate.entity_id,
            "entity_type": candidate.entity_type,
            "name": candidate.name,
            "source_name": candidate.source_name,
        }
        for candidate in candidates[:25]
    ]


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
