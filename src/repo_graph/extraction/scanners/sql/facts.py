"""SQL relationship fact construction."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.sql.naming import normalize_sql_name
from repo_graph.extraction.scanners.sql.properties import (
    source_context_properties,
    sql_interaction_properties,
    sql_reference_properties,
)


def sql_call_fact(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    parser: str = "sql_reference",
    from_entity: EntityFact | None = None,
    target_name: str | None = None,
    extra_properties: dict[str, Any] | None = None,
    include_reference_properties: bool = True,
) -> RelationshipFact:
    return sql_relationship_fact(
        context,
        raw_target,
        target_name or normalize_sql_name(raw_target),
        "CALLS_SQL",
        "stored_procedure",
        "EXECUTE",
        "stored_procedure",
        line_number,
        parser,
        from_entity=from_entity,
        extra_properties=extra_properties,
        include_reference_properties=include_reference_properties,
    )


def sql_object_read_fact(
    context: FileScanContext,
    raw_target: str,
    operation: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return sql_relationship_fact(
        context,
        raw_target,
        normalize_sql_name(raw_target),
        "READS_SQL_OBJECT",
        "sql_object",
        operation,
        "sql_object",
        line_number,
        "sql_reference",
        from_entity=from_entity,
        extra_properties=extra_properties,
        include_reference_properties=True,
    )


def sql_object_write_fact(
    context: FileScanContext,
    raw_target: str,
    operation: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return sql_relationship_fact(
        context,
        raw_target,
        normalize_sql_name(raw_target),
        "WRITES_SQL_OBJECT",
        "sql_object",
        operation,
        "sql_object",
        line_number,
        "sql_reference",
        from_entity=from_entity,
        extra_properties=extra_properties,
        include_reference_properties=True,
    )


def sql_schema_reference_fact(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return sql_relationship_fact(
        context,
        raw_target,
        normalize_sql_name(raw_target),
        "REFERENCES_SQL_OBJECT",
        "sql_object",
        "REFERENCES",
        "sql_object",
        line_number,
        "sql_reference",
        from_entity=from_entity,
        dependency_scope="schema",
        interaction_kind="sql_schema_reference",
        extra_properties=extra_properties,
        include_reference_properties=True,
    )


def sql_relationship_fact(
    context: FileScanContext,
    raw_target: str,
    target_name: str,
    edge_type: str,
    to_type: str,
    operation: str,
    database_object_type: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    dependency_scope: str = "runtime",
    interaction_kind: str = "sql_reference",
    extra_properties: dict[str, Any] | None = None,
    include_reference_properties: bool = True,
) -> RelationshipFact:
    properties = sql_interaction_properties(
        raw_target,
        operation,
        database_object_type,
        dependency_scope=dependency_scope,
        interaction_kind=interaction_kind,
        extra_properties=sql_relationship_extra_properties(
            context,
            from_entity,
            extra_properties,
            include_reference_properties=include_reference_properties,
        ),
    )
    return unresolved_relationship_fact(
        entity_reference(from_entity or context.file_entity),
        target_name,
        edge_type,
        context,
        parser,
        to_type=to_type,
        line_number=line_number,
        properties=properties,
    )


def sql_relationship_extra_properties(
    context: FileScanContext,
    from_entity: EntityFact | None,
    extra_properties: dict[str, Any] | None,
    include_reference_properties: bool,
) -> dict[str, Any]:
    properties: dict[str, Any] = source_context_properties(from_entity)
    if extra_properties:
        properties.update(extra_properties)
    if include_reference_properties:
        return sql_reference_properties(context, properties)
    return properties


__all__ = [
    "sql_call_fact",
    "sql_object_read_fact",
    "sql_object_write_fact",
    "sql_schema_reference_fact",
]
