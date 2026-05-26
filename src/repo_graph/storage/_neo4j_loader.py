"""Neo4j graph loading workflow."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from repo_graph.storage._neo4j_models import LoadSummary
from repo_graph.storage._neo4j_records import (
    graph_record,
    grouped_relationships,
    load_summary,
    normalize_source_names,
    prepare_graph_records,
    resolved_edges,
    unresolved_edges,
    validate_replace_sources,
)
from repo_graph.storage._neo4j_settings import Neo4jSettings
from repo_graph.storage._neo4j_writes import (
    clear_graph_tx,
    delete_current_edges_tx,
    delete_orphan_external_resources_tx,
    delete_orphan_targets_tx,
    delete_source_data_tx,
    initialize_schema,
    write_entities_tx,
    write_graph_tx,
    write_resolved_edges_tx,
    write_sources_tx,
    write_targets_tx,
    write_unresolved_edges_tx,
)


def load_graph_path(
    path: Path,
    settings: Neo4jSettings,
    clear_existing: bool = True,
    replace_sources: Iterable[str] | None = None,
) -> LoadSummary:
    graph_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(graph_data, dict):
        raise ValueError("Graph JSON root must be an object.")
    return load_graph_data(graph_data, settings, clear_existing=clear_existing, replace_sources=replace_sources)


def load_graph_data(
    graph_data: Mapping[str, Any],
    settings: Neo4jSettings,
    clear_existing: bool = True,
    replace_sources: Iterable[str] | None = None,
) -> LoadSummary:
    source_names = normalize_source_names(replace_sources)
    if clear_existing and source_names:
        raise ValueError("Source replacement cannot also clear the whole graph.")
    validate_replace_sources(graph_data, source_names)
    records = prepare_graph_records(graph_data)

    with GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=settings.database) as session:
            initialize_schema(session)
            if clear_existing:
                session.execute_write(clear_graph_tx)
            elif source_names:
                session.execute_write(delete_current_edges_tx, records.edge_records)
                session.execute_write(delete_source_data_tx, source_names)
            session.execute_write(write_graph_tx, graph_record(graph_data))
            if records.source_records:
                session.execute_write(write_sources_tx, records.source_records)
            if records.entity_records:
                session.execute_write(write_entities_tx, records.entity_records)
            if records.target_records:
                session.execute_write(write_targets_tx, records.target_records)
            for relationship_type, edge_records in grouped_relationships(records.edge_records).items():
                session.execute_write(write_resolved_edges_tx, relationship_type, resolved_edges(edge_records))
                session.execute_write(write_unresolved_edges_tx, relationship_type, unresolved_edges(edge_records))
            session.execute_write(delete_orphan_targets_tx)
            session.execute_write(delete_orphan_external_resources_tx)

    return load_summary(
        graph_data,
        records.source_records,
        records.edge_records,
        records.target_records,
        clear_existing=clear_existing,
    )


__all__ = [
    "load_graph_data",
    "load_graph_path",
]
