"""SQL interaction property helpers."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.sql.naming import normalize_sql_name
from repo_graph.extraction.scanners.sql.provenance import sql_reference_extra_properties


def sql_interaction_properties(
    raw_target: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str = "runtime",
    interaction_kind: str = "sql_reference",
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties = interaction_properties(
        "database",
        dependency_scope,
        interaction_kind,
        protocol="sql",
        raw_target=raw_target,
        normalized_target=normalize_sql_name(raw_target),
        sql_operation=operation.upper(),
        database_object_type=database_object_type,
    )
    if extra_properties:
        properties.update(extra_properties)
    return properties


def sql_reference_properties(
    context: FileScanContext,
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = sql_reference_extra_properties(context)
    if extra_properties:
        properties.update(extra_properties)
    return properties


def source_context_properties(from_entity: EntityFact | None) -> dict[str, str]:
    if not from_entity or from_entity.entity_type == "file":
        return {}
    return {
        "source_context_type": from_entity.entity_type,
        "source_context_name": from_entity.name,
    }
