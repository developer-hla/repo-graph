"""Temporary graph helpers for legacy scanners."""

from __future__ import annotations

from typing import Any

from repo_graph.graph import Edge, Entity


def resolved_edge(
    from_entity: Entity,
    to_entity: Entity,
    edge_type: str,
    source_name: str,
    file_path: str | None = None,
    parser: str = "unknown",
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> Edge:
    return Edge(
        from_entity_id=from_entity.entity_id,
        from_name=from_entity.name,
        from_type=from_entity.entity_type,
        to_name=to_entity.name,
        to_type=to_entity.entity_type,
        to_entity_id=to_entity.entity_id,
        resolved=True,
        edge_type=edge_type,
        source_name=source_name,
        file_path=file_path,
        line_number=line_number,
        parser=parser,
        confidence="high",
        properties=properties or {},
    )


def unresolved_edge(
    from_entity: Entity,
    to_name: str,
    edge_type: str,
    source_name: str,
    file_path: str,
    parser: str,
    to_type: str | None = None,
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> Edge:
    return Edge(
        from_entity_id=from_entity.entity_id,
        from_name=from_entity.name,
        from_type=from_entity.entity_type,
        to_name=to_name,
        to_type=to_type,
        edge_type=edge_type,
        source_name=source_name,
        file_path=file_path,
        line_number=line_number,
        parser=parser,
        confidence="medium",
        properties=properties or {},
    )


def interaction_properties(
    target_boundary: str,
    dependency_scope: str,
    interaction_kind: str,
    **evidence: Any,
) -> dict[str, Any]:
    return {
        "target_boundary": target_boundary,
        "dependency_scope": dependency_scope,
        "interaction_kind": interaction_kind,
        **{key: value for key, value in evidence.items() if value is not None},
    }
