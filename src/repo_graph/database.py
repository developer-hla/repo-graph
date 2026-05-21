"""Pure database metadata adapters for RepoGraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from repo_graph.graph import Edge, Entity, normalize_key, resolution_entity_types

SQLSERVER_METADATA_PARSER = "sqlserver_metadata"
POSTGRES_METADATA_PARSER = "postgres_metadata"
SQLSERVER_ENGINE = "sqlserver"
POSTGRES_ENGINE = "postgres"
CURRENT_DATABASE_SCHEMA_STATE = "current_database"

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
    """Live database connector entry point.

    The registry and request contract are in place, but no connector opens a
    real database connection yet.
    """

    raise DatabaseConnectorUnavailable(database_connector_unavailable_message(_request.source_name, _request.engine))


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
