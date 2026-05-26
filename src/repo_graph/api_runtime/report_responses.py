"""Report response builders for the API."""

from __future__ import annotations

from typing import Any

from repo_graph.api_runtime.constants import (
    DATABASE_RECONCILIATION_EDGE_LIMIT,
    DATABASE_RECONCILIATION_ENTITY_LIMIT,
    INTERACTION_REPORT_EDGE_LIMIT,
    UNRESOLVED_REPORT_EDGE_LIMIT,
)
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.reports import (
    database_reconciliation_report_from_items,
    interactions_report_from_items,
    unresolved_report_from_items,
)
from repo_graph.storage import list_entities_by_types, list_unresolved_edges, search_relationships_by_edge_types
from repo_graph.vocabulary import INTERACTION_EDGE_TYPES, SQL_EDGE_TYPES, SQL_ENTITY_TYPES


def unresolved_report_response(
    settings: RuntimeSettings,
    source_name: str | None,
    edge_type: str | None,
    limit: int,
    examples: int,
) -> dict[str, Any]:
    items = list_unresolved_edges(
        settings.neo4j_settings(),
        source_name=source_name,
        edge_type=edge_type,
        limit=UNRESOLVED_REPORT_EDGE_LIMIT,
    )
    report = unresolved_report_from_items(
        items,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=limit,
        examples_per_group=examples,
    )
    report["edge_sample_limit"] = UNRESOLVED_REPORT_EDGE_LIMIT
    report["edge_sample_truncated"] = len(items) >= UNRESOLVED_REPORT_EDGE_LIMIT
    return report


def interactions_report_response(
    settings: RuntimeSettings,
    source_name: str | None,
    target_source: str | None,
    edge_type: str | None,
    limit: int,
    examples: int,
) -> dict[str, Any]:
    edge_types = [edge_type] if edge_type else sorted(INTERACTION_EDGE_TYPES)
    items = search_relationships_by_edge_types(
        settings.neo4j_settings(),
        edge_types,
        from_source=source_name,
        to_source=target_source,
        limit=INTERACTION_REPORT_EDGE_LIMIT,
    )
    report = interactions_report_from_items(
        items,
        source_name=source_name,
        target_source=target_source,
        edge_type=edge_type,
        group_limit=limit,
        examples_per_group=examples,
    )
    report["edge_sample_limit"] = INTERACTION_REPORT_EDGE_LIMIT
    report["edge_sample_truncated"] = len(items) >= INTERACTION_REPORT_EDGE_LIMIT
    return report


def database_reconciliation_report_response(
    settings: RuntimeSettings,
    source_name: str | None,
    database_source: str | None,
    limit: int,
    examples: int,
) -> dict[str, Any]:
    entities = list_entities_by_types(
        settings.neo4j_settings(),
        SQL_ENTITY_TYPES,
        limit=DATABASE_RECONCILIATION_ENTITY_LIMIT,
    )
    items = search_relationships_by_edge_types(
        settings.neo4j_settings(),
        SQL_EDGE_TYPES,
        limit=DATABASE_RECONCILIATION_EDGE_LIMIT,
    )
    report = database_reconciliation_report_from_items(
        entities,
        items,
        source_name=source_name,
        database_source=database_source,
        group_limit=limit,
        examples_per_group=examples,
    )
    report["entity_sample_limit"] = DATABASE_RECONCILIATION_ENTITY_LIMIT
    report["entity_sample_truncated"] = len(entities) >= DATABASE_RECONCILIATION_ENTITY_LIMIT
    report["edge_sample_limit"] = DATABASE_RECONCILIATION_EDGE_LIMIT
    report["edge_sample_truncated"] = len(items) >= DATABASE_RECONCILIATION_EDGE_LIMIT
    return report


__all__ = [
    "database_reconciliation_report_response",
    "interactions_report_response",
    "unresolved_report_response",
]
