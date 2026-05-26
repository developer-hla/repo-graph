"""Typed database metadata models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from repo_graph.extraction.facts import EntityFact, Evidence, FactBatch, RelationshipFact, ScanIssue


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
