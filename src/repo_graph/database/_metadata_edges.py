"""Database metadata relationship fact builders."""

from __future__ import annotations

from typing import Any

from repo_graph.database._constants import CURRENT_DATABASE_SCHEMA_STATE
from repo_graph.database._models import EntityMatch
from repo_graph.database._naming import normalize_sql_identifier
from repo_graph.extraction.facts import EntityFact, EntityReference, Evidence, RelationshipFact


def database_foreign_key_metadata_edge(
    source_entity: EntityFact,
    target_match: EntityMatch,
    target_name: str,
    source_name: str,
    metadata_source: str,
    identity_key: str,
    database_engine: str,
    parser: str,
    constraint_name: str | None = None,
) -> RelationshipFact:
    return database_metadata_edge(
        source_entity=source_entity,
        target_match=target_match,
        target_name=target_name,
        target_type="sql_table",
        edge_type="REFERENCES_SQL_OBJECT",
        source_name=source_name,
        operation="FOREIGN_KEY",
        database_object_type="sql_object",
        dependency_scope="schema",
        interaction_kind="sql_schema_reference",
        metadata_source=metadata_source,
        identity_key=identity_key,
        database_engine=database_engine,
        parser=parser,
        extra_properties={"constraint_name": constraint_name},
    )


def database_dependency_metadata_edge(
    source_entity: EntityFact,
    target_match: EntityMatch,
    target_name: str,
    target_type: str,
    source_name: str,
    metadata_source: str,
    identity_key: str,
    database_engine: str,
    parser: str,
    is_execute_dependency: bool,
    reference_operation: str,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    normalized_target_type = database_dependency_target_type(target_type, is_execute_dependency)
    return database_metadata_edge(
        source_entity=source_entity,
        target_match=target_match,
        target_name=target_name,
        target_type=normalized_target_type,
        edge_type="CALLS_SQL" if is_execute_dependency else "REFERENCES_SQL_OBJECT",
        source_name=source_name,
        operation="EXECUTE" if is_execute_dependency else reference_operation,
        database_object_type=normalized_target_type,
        dependency_scope="runtime" if is_execute_dependency else "schema",
        interaction_kind="sql_reference" if is_execute_dependency else "sql_schema_reference",
        metadata_source=metadata_source,
        identity_key=identity_key,
        database_engine=database_engine,
        parser=parser,
        extra_properties=extra_properties,
    )


def database_dependency_target_type(target_type: str, is_execute_dependency: bool) -> str:
    if is_execute_dependency and target_type == "sql_object":
        return "stored_procedure"
    return target_type


def database_trigger_metadata_edge(
    source_entity: EntityFact,
    target_match: EntityMatch,
    target_name: str,
    source_name: str,
    metadata_source: str,
    identity_key: str,
    database_engine: str,
    parser: str,
    trigger_name: str,
    events: tuple[str, ...],
    is_enabled: bool | None,
) -> RelationshipFact:
    return database_metadata_edge(
        source_entity=source_entity,
        target_match=target_match,
        target_name=target_name,
        target_type="sql_table",
        edge_type="TRIGGERS_ON_SQL_OBJECT",
        source_name=source_name,
        operation="TRIGGER_ON",
        database_object_type="sql_table",
        dependency_scope="runtime",
        interaction_kind="sql_trigger",
        metadata_source=metadata_source,
        identity_key=identity_key,
        database_engine=database_engine,
        parser=parser,
        extra_properties={
            "trigger_events": list(events),
            "trigger_enabled": is_enabled,
            "trigger_name": trigger_name,
        },
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


def resolution_candidate_properties(candidates: tuple[EntityFact, ...]) -> list[dict[str, str]]:
    return [
        {
            "entity_type": candidate.entity_type,
            "name": candidate.name,
            "source_name": candidate.source_name,
        }
        for candidate in candidates[:25]
    ]


__all__ = [
    "database_dependency_metadata_edge",
    "database_dependency_target_type",
    "database_foreign_key_metadata_edge",
    "database_trigger_metadata_edge",
]
