"""Build graph model records from typed extraction facts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repo_graph.graph.model import Edge, Entity, Graph, stable_id

if TYPE_CHECKING:
    from repo_graph.extraction.facts import EntityFact, EntityReference, FactBatch, RelationshipFact


def add_facts_to_graph(graph: Graph, facts: FactBatch) -> None:
    for fact in facts.entities:
        graph.add_entity(entity_from_fact(fact))
    for fact in facts.relationships:
        graph.add_edge(edge_from_fact(fact))
    graph.errors.extend(issue.message for issue in facts.issues)


def entity_from_fact(fact: EntityFact) -> Entity:
    return Entity(
        entity_type=fact.entity_type,
        name=fact.name,
        source_name=fact.source_name,
        file_path=fact.file_path,
        line_number=fact.line_number,
        aliases=set(fact.aliases),
        properties=fact.properties,
    )


def edge_from_fact(fact: RelationshipFact) -> Edge:
    from_entity_id = entity_id_from_ref(fact.from_ref)
    if not from_entity_id:
        raise ValueError(f"Relationship fact source has no resolvable entity id: {fact.from_ref}")

    to_entity_id = entity_id_from_ref(fact.to_ref)
    resolved = fact.resolved if fact.resolved is not None else to_entity_id is not None
    return Edge(
        from_entity_id=from_entity_id,
        from_name=fact.from_ref.name,
        from_type=fact.from_ref.entity_type,
        to_name=fact.to_ref.name,
        to_type=fact.to_ref.entity_type,
        to_entity_id=to_entity_id,
        resolved=resolved,
        edge_type=fact.edge_type,
        source_name=fact.evidence.source_name,
        file_path=fact.evidence.file_path,
        line_number=fact.evidence.line_number,
        identity_key=fact.identity_key,
        confidence=fact.evidence.confidence,
        parser=fact.evidence.parser,
        properties=fact.properties,
    )


def entity_id_from_ref(ref: EntityReference) -> str | None:
    if ref.entity_id:
        return ref.entity_id
    if ref.source_name is None:
        return None
    return stable_id("entity", ref.source_name, ref.entity_type, ref.name, ref.file_path or "")


__all__ = [
    "add_facts_to_graph",
    "edge_from_fact",
    "entity_from_fact",
    "entity_id_from_ref",
]
