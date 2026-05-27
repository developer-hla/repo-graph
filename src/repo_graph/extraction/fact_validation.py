"""Validation helpers for scanner-emitted facts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from repo_graph.extraction.facts import FactBatch, RelationshipFact
from repo_graph.vocabulary import (
    INTERACTION_DEPENDENCY_SCOPES,
    INTERACTION_EDGE_TYPES,
    INTERACTION_EVIDENCE_KEYS,
    INTERACTION_KINDS,
    INTERACTION_TARGET_BOUNDARIES,
)


@dataclass(frozen=True)
class FactValidationIssue:
    message: str
    edge_type: str
    parser: str
    source_name: str
    file_path: str | None = None
    line_number: int | None = None


def validate_fact_batch(facts: FactBatch) -> list[FactValidationIssue]:
    return validate_relationship_facts(facts.relationships)


def validate_relationship_facts(relationships: Iterable[RelationshipFact]) -> list[FactValidationIssue]:
    issues: list[FactValidationIssue] = []
    for relationship in relationships:
        issues.extend(validate_interaction_relationship_fact(relationship))
    return issues


def validate_interaction_relationship_fact(relationship: RelationshipFact) -> list[FactValidationIssue]:
    if relationship.edge_type not in INTERACTION_EDGE_TYPES:
        return []

    issues: list[FactValidationIssue] = []
    for key in INTERACTION_EVIDENCE_KEYS:
        if key not in relationship.properties:
            issues.append(issue(relationship, f"missing interaction property {key!r}"))

    target_boundary = relationship.properties.get("target_boundary")
    if target_boundary is not None and target_boundary not in INTERACTION_TARGET_BOUNDARIES:
        issues.append(issue(relationship, f"invalid target_boundary {target_boundary!r}"))

    dependency_scope = relationship.properties.get("dependency_scope")
    if dependency_scope is not None and dependency_scope not in INTERACTION_DEPENDENCY_SCOPES:
        issues.append(issue(relationship, f"invalid dependency_scope {dependency_scope!r}"))

    interaction_kind = relationship.properties.get("interaction_kind")
    if interaction_kind is not None and interaction_kind not in INTERACTION_KINDS:
        issues.append(issue(relationship, f"invalid interaction_kind {interaction_kind!r}"))

    return issues


def issue(relationship: RelationshipFact, message: str) -> FactValidationIssue:
    return FactValidationIssue(
        message=message,
        edge_type=relationship.edge_type,
        parser=relationship.parser,
        source_name=relationship.source_name,
        file_path=relationship.evidence.file_path,
        line_number=relationship.evidence.line_number,
    )


__all__ = [
    "FactValidationIssue",
    "validate_fact_batch",
    "validate_interaction_relationship_fact",
    "validate_relationship_facts",
]
