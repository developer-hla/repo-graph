"""Database reconciliation report builder."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from repo_graph.reports._common import (
    DEFAULT_EXAMPLE_LIMIT,
    DEFAULT_GROUP_LIMIT,
    compact_dict,
    edge_from_item,
    edge_matches,
    graph_items,
    mapping_value,
    string_value,
    validate_positive_int,
)
from repo_graph.reports.database_reconciliation._constants import (
    CURRENT_DATABASE_SCHEMA_STATE,
    HISTORICAL_SCHEMA_STATE,
)
from repo_graph.reports.database_reconciliation._groups import (
    GroupMap,
    add_code_only_reference_groups,
    add_database_only_object_groups,
    add_migration_only_object_groups,
    add_schema_drift_groups,
    add_unresolved_database_reference_groups,
)
from repo_graph.reports.database_reconciliation._normalization import (
    entity_index_by_sql_name,
    is_current_database_entity,
    is_database_metadata_edge,
    is_sql_edge,
    is_sql_entity,
    relationship_sql_entities,
    schema_state,
    source_matches,
)
from repo_graph.reports.database_reconciliation._summaries import (
    database_reconciliation_classification_groups,
    database_reconciliation_rank,
    database_reconciliation_source_hotspots,
    database_reconciliation_summary,
    database_reconciliation_target_hotspots,
    finalize_database_reconciliation_group,
)


def database_reconciliation_report_from_graph(
    graph_data: Mapping[str, Any],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    metadata = mapping_value(graph_data.get("metadata"))
    return database_reconciliation_report(
        graph_items(graph_data, "entities"),
        graph_items(graph_data, "edges"),
        source_name=source_name,
        database_source=database_source,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
        scope_name=string_value(metadata.get("scope_name")),
        generated_at=string_value(metadata.get("generated_at")),
    )


def database_reconciliation_report_from_items(
    entities: Iterable[Mapping[str, Any]],
    items: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
) -> dict[str, Any]:
    item_list = list(items)
    return database_reconciliation_report(
        [*entities, *relationship_sql_entities(item_list)],
        [edge_from_item(item) for item in item_list],
        source_name=source_name,
        database_source=database_source,
        group_limit=group_limit,
        examples_per_group=examples_per_group,
    )


def database_reconciliation_report(
    entities: Iterable[Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    source_name: str | None = None,
    database_source: str | None = None,
    group_limit: int = DEFAULT_GROUP_LIMIT,
    examples_per_group: int = DEFAULT_EXAMPLE_LIMIT,
    scope_name: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    validate_positive_int(group_limit, "group_limit")
    validate_positive_int(examples_per_group, "examples_per_group")

    entity_items = [entity for entity in entities if is_sql_entity(entity)]
    entity_by_id = {
        string_value(entity.get("entity_id")): entity
        for entity in entity_items
        if string_value(entity.get("entity_id"))
    }
    current_entities = [
        entity
        for entity in entity_items
        if is_current_database_entity(entity) and source_matches(entity, database_source)
    ]
    historical_entities = [
        entity
        for entity in entity_items
        if schema_state(entity) == HISTORICAL_SCHEMA_STATE and source_matches(entity, source_name)
    ]
    source_schema_entities = [
        entity
        for entity in entity_items
        if schema_state(entity) not in {CURRENT_DATABASE_SCHEMA_STATE, HISTORICAL_SCHEMA_STATE}
        and source_matches(entity, source_name)
    ]
    current_index = entity_index_by_sql_name(current_entities)
    source_schema_index = entity_index_by_sql_name(source_schema_entities)
    historical_index = entity_index_by_sql_name(historical_entities)
    sql_edges = [edge for edge in edges if is_sql_edge(edge)]
    code_edges = [
        edge for edge in sql_edges if not is_database_metadata_edge(edge) and edge_matches(edge, source_name, None)
    ]
    metadata_edges = [
        edge for edge in sql_edges if is_database_metadata_edge(edge) and edge_matches(edge, database_source, None)
    ]

    groups: GroupMap = {}
    database_evidence_present = bool(current_entities)
    if database_evidence_present:
        add_code_only_reference_groups(groups, code_edges, entity_by_id, current_index, examples_per_group)
        add_migration_only_object_groups(groups, historical_index, current_index, examples_per_group)
        add_schema_drift_groups(groups, source_schema_index, current_index, examples_per_group)
        add_database_only_object_groups(
            groups,
            current_entities,
            code_edges,
            entity_by_id,
            source_schema_index,
            examples_per_group,
        )
    add_unresolved_database_reference_groups(groups, metadata_edges, examples_per_group)

    items = [finalize_database_reconciliation_group(group) for group in groups.values()]
    items.sort(
        key=lambda item: (
            database_reconciliation_rank(item["classification"]),
            -item["count"],
            item["target_type"],
            item["target_name"],
        )
    )
    limited_items = items[:group_limit]
    return compact_dict(
        {
            "scope_name": scope_name,
            "generated_at": generated_at,
            "filters": compact_dict({"source": source_name, "database_source": database_source}),
            "summary": database_reconciliation_summary(
                items,
                limited_items,
                current_entities,
                code_edges,
                metadata_edges,
                database_evidence_present,
            ),
            "classification_groups": database_reconciliation_classification_groups(items),
            "source_hotspots": database_reconciliation_source_hotspots(items),
            "target_hotspots": database_reconciliation_target_hotspots(items),
            "items": limited_items,
        }
    )
