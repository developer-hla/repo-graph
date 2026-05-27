"""Storage relationship fact construction."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.sql.properties import source_context_properties
from repo_graph.extraction.scanners.storage.models import StorageOperation, StorageTarget
from repo_graph.extraction.scanners.storage.operations import storage_operations_for_line
from repo_graph.extraction.scanners.storage.targets import storage_target_for_line


def storage_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in storage_operations_for_line(line):
        target = storage_target_for_line(line)
        if target:
            facts.append(storage_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


def storage_relationship_fact(
    context: FileScanContext,
    operation: StorageOperation,
    target: StorageTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "storage",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        storage_kind=target.storage_kind,
        storage_operation=operation.action,
        storage_method=operation.method,
        storage_receiver=operation.receiver,
        bucket=target.bucket,
        container=target.container,
        object_key=target.object_key,
        target_key=target.target_key,
    )
    properties.update(source_context_properties(from_entity))
    if extra_properties:
        properties.update(extra_properties)
    return unresolved_relationship_fact(
        entity_reference(from_entity or context.file_entity),
        target.name,
        operation.edge_type,
        context,
        parser,
        to_type="storage_location",
        line_number=line_number,
        properties=properties,
    )
