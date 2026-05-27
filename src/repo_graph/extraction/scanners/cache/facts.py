"""Cache relationship fact construction."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.cache.models import CacheOperation, CacheTarget
from repo_graph.extraction.scanners.cache.operations import cache_operations_for_line
from repo_graph.extraction.scanners.cache.targets import cache_target_for_line
from repo_graph.extraction.scanners.sql.properties import source_context_properties


def cache_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in cache_operations_for_line(line):
        target = cache_target_for_line(line)
        if target:
            facts.append(cache_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


def cache_relationship_fact(
    context: FileScanContext,
    operation: CacheOperation,
    target: CacheTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "cache",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        cache_operation=operation.action,
        cache_method=operation.method,
        cache_receiver=operation.receiver,
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
        to_type="cache_key",
        line_number=line_number,
        properties=properties,
    )
