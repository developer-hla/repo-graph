"""Messaging relationship fact construction."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.messaging.models import MessageOperation, MessageTarget
from repo_graph.extraction.scanners.messaging.operations import message_operations_for_line
from repo_graph.extraction.scanners.messaging.targets import message_targets_for_line
from repo_graph.extraction.scanners.sql.properties import source_context_properties


def message_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in message_operations_for_line(line):
        for target in message_targets_for_line(line, operation):
            facts.append(message_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


def message_relationship_fact(
    context: FileScanContext,
    operation: MessageOperation,
    target: MessageTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "messaging",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        message_destination_type=target.entity_type,
        message_destination_kind=target.destination_kind,
        message_operation=operation.action,
        messaging_method=operation.method,
        messaging_receiver=operation.receiver,
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
        to_type=target.entity_type,
        line_number=line_number,
        properties=properties,
    )
