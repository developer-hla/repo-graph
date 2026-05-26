"""Small helpers for building typed extraction facts."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, EntityReference, Evidence, RelationshipFact
from repo_graph.graph import Entity


def entity_reference(entity: Entity | EntityFact) -> EntityReference:
    if isinstance(entity, EntityFact):
        return entity.reference
    return EntityReference(
        entity_type=entity.entity_type,
        name=entity.name,
        source_name=entity.source_name,
        file_path=entity.file_path,
        entity_id=entity.entity_id,
    )


def source_evidence(
    context: FileScanContext,
    parser: str,
    line_number: int | None = None,
    confidence: str = "medium",
) -> Evidence:
    return evidence(
        context.source.name,
        parser,
        file_path=context.rel_path,
        line_number=line_number,
        confidence=confidence,
    )


def evidence(
    source_name: str,
    parser: str,
    file_path: str | None = None,
    line_number: int | None = None,
    confidence: str = "medium",
) -> Evidence:
    return Evidence(
        source_name=source_name,
        parser=parser,
        file_path=file_path,
        line_number=line_number,
        confidence=confidence,
    )


def entity_fact(
    context: FileScanContext,
    entity_type: str,
    name: str,
    aliases: set[str] | None = None,
    properties: dict[str, Any] | None = None,
    line_number: int | None = None,
    file_path: str | None = None,
) -> EntityFact:
    return EntityFact(
        entity_type=entity_type,
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path if file_path is None else file_path,
        line_number=line_number,
        aliases=frozenset(aliases or set()),
        properties=properties or {},
    )


def package_entity_fact(
    context: FileScanContext,
    name: str,
    aliases: set[str],
    properties: dict[str, Any],
    line_number: int | None = None,
) -> EntityFact:
    return EntityFact(
        entity_type="package",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=frozenset(aliases),
        properties=properties,
    )


def resolved_relationship_fact(
    from_ref: EntityReference,
    to_ref: EntityReference,
    edge_type: str,
    context: FileScanContext,
    parser: str,
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return RelationshipFact(
        from_ref=from_ref,
        to_ref=to_ref,
        edge_type=edge_type,
        evidence=source_evidence(context, parser, line_number=line_number, confidence="high"),
        properties=properties or {},
        resolved=True,
    )


def resolved_source_relationship_fact(
    from_ref: EntityReference,
    to_ref: EntityReference,
    edge_type: str,
    source_name: str,
    parser: str,
    file_path: str | None = None,
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return RelationshipFact(
        from_ref=from_ref,
        to_ref=to_ref,
        edge_type=edge_type,
        evidence=evidence(
            source_name,
            parser,
            file_path=file_path,
            line_number=line_number,
            confidence="high",
        ),
        properties=properties or {},
        resolved=True,
    )


def unresolved_relationship_fact(
    from_ref: EntityReference,
    to_name: str,
    edge_type: str,
    context: FileScanContext,
    parser: str,
    to_type: str,
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    return RelationshipFact(
        from_ref=from_ref,
        to_ref=EntityReference(entity_type=to_type, name=to_name),
        edge_type=edge_type,
        evidence=source_evidence(context, parser, line_number=line_number),
        properties=properties or {},
        resolved=False,
    )


def declares_package_facts(
    context: FileScanContext,
    package_ref: EntityReference,
    parser: str,
) -> list[RelationshipFact]:
    relationships = [
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            package_ref,
            "DECLARES_PACKAGE",
            context,
            parser,
        )
    ]
    if context.project:
        relationships.append(
            resolved_relationship_fact(
                entity_reference(context.project.entity),
                package_ref,
                "DECLARES_PACKAGE",
                context,
                parser,
            )
        )
    return relationships


def package_dependency_fact(
    from_ref: EntityReference,
    name: str | None,
    ecosystem: str,
    dependency_type: str | None,
    version: str | None,
    raw_target: str | None,
    context: FileScanContext,
    parser: str,
    line_number: int | None = None,
) -> RelationshipFact:
    target_name = name or raw_target or ""
    return RelationshipFact(
        from_ref=from_ref,
        to_ref=EntityReference(entity_type="package", name=target_name),
        edge_type="DEPENDS_ON_PACKAGE",
        evidence=source_evidence(context, parser, line_number=line_number),
        properties={
            "ecosystem": ecosystem,
            "dependency_type": dependency_type,
            "version": version,
            "raw_target": raw_target,
            "normalized_target": target_name,
        },
    )


__all__ = [
    "declares_package_facts",
    "entity_fact",
    "entity_reference",
    "evidence",
    "package_dependency_fact",
    "package_entity_fact",
    "resolved_relationship_fact",
    "resolved_source_relationship_fact",
    "source_evidence",
    "unresolved_relationship_fact",
]
