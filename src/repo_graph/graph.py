"""Portable graph model for RepoGraph."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from repo_graph.schema import GRAPH_SCHEMA_VERSION


@dataclass
class Entity:
    entity_type: str
    name: str
    source_name: str
    file_path: str | None = None
    line_number: int | None = None
    aliases: set[str] = field(default_factory=set)
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def entity_id(self) -> str:
        return stable_id("entity", self.source_name, self.entity_type, self.name, self.file_path or "")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "source_name": self.source_name,
            "aliases": sorted(self.aliases),
            "properties": self.properties,
        }
        if self.file_path:
            data["file_path"] = self.file_path
        if self.line_number is not None:
            data["line_number"] = self.line_number
        return data


@dataclass
class Edge:
    from_entity_id: str
    from_name: str
    from_type: str
    to_name: str
    edge_type: str
    source_name: str
    to_type: str | None = None
    to_entity_id: str | None = None
    resolved: bool = False
    file_path: str | None = None
    line_number: int | None = None
    confidence: str = "medium"
    parser: str = "unknown"
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def edge_id(self) -> str:
        return stable_id(
            "edge",
            self.from_entity_id,
            self.edge_type,
            self.to_name,
            self.file_path or "",
            str(self.line_number or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "edge_id": self.edge_id,
            "from_entity_id": self.from_entity_id,
            "from_name": self.from_name,
            "from_type": self.from_type,
            "to_name": self.to_name,
            "to_type": self.to_type,
            "to_entity_id": self.to_entity_id,
            "edge_type": self.edge_type,
            "resolved": self.resolved,
            "source_name": self.source_name,
            "confidence": self.confidence,
            "parser": self.parser,
            "properties": self.properties,
        }
        if self.file_path:
            data["file_path"] = self.file_path
        if self.line_number is not None:
            data["line_number"] = self.line_number
        return data


@dataclass
class Graph:
    scope_name: str
    sources: list[dict[str, Any]]
    entities: dict[str, Entity] = field(default_factory=dict)
    edges: dict[str, Edge] = field(default_factory=dict)
    files_scanned: int = 0
    errors: list[str] = field(default_factory=list)

    def add_entity(self, entity: Entity) -> Entity:
        existing = self.entities.get(entity.entity_id)
        if existing:
            existing.aliases.update(entity.aliases)
            existing.properties.update({key: value for key, value in entity.properties.items() if value is not None})
            return existing
        self.entities[entity.entity_id] = entity
        return entity

    def add_edge(self, edge: Edge) -> None:
        self.edges[edge.edge_id] = edge

    def resolve_edges(self) -> None:
        lookup: dict[tuple[str | None, str], list[Entity]] = defaultdict(list)
        for entity in self.entities.values():
            keys = {entity.name, *entity.aliases}
            full_name = entity.properties.get("full_name")
            if isinstance(full_name, str):
                keys.add(full_name)
            schema = entity.properties.get("schema")
            if isinstance(schema, str) and schema:
                keys.add(f"{schema}.{entity.name}")
            for key in keys:
                normalized = normalize_key(key)
                lookup[(entity.entity_type, normalized)].append(entity)
                lookup[(None, normalized)].append(entity)

        for edge in self.edges.values():
            if edge.to_entity_id:
                edge.resolved = edge.to_entity_id in self.entities
                continue
            candidates = resolution_candidates(lookup, edge.to_type, normalize_key(edge.to_name))
            entity = choose_resolution(candidates, edge.source_name)
            if entity:
                edge.to_entity_id = entity.entity_id
                edge.to_type = entity.entity_type
                edge.resolved = True
            elif candidates:
                edge.properties["resolution_status"] = "ambiguous"
                edge.properties["resolution_candidates"] = [
                    {
                        "entity_id": candidate.entity_id,
                        "entity_type": candidate.entity_type,
                        "name": candidate.name,
                        "source_name": candidate.source_name,
                    }
                    for candidate in candidates[:25]
                ]

    def to_dict(self) -> dict[str, Any]:
        entity_counts = Counter(entity.entity_type for entity in self.entities.values())
        edge_counts = Counter(edge.edge_type for edge in self.edges.values())
        resolved_edges = sum(1 for edge in self.edges.values() if edge.resolved)
        return {
            "metadata": {
                "tool": "RepoGraph",
                "schema_version": GRAPH_SCHEMA_VERSION,
                "scope_name": self.scope_name,
                "generated_at": datetime.now(UTC).isoformat(),
            },
            "sources": self.sources,
            "summary": {
                "files_scanned": self.files_scanned,
                "entity_count": len(self.entities),
                "edge_count": len(self.edges),
                "resolved_edge_count": resolved_edges,
                "unresolved_edge_count": len(self.edges) - resolved_edges,
                "error_count": len(self.errors),
            },
            "entity_counts": dict(sorted(entity_counts.items())),
            "edge_counts": dict(sorted(edge_counts.items())),
            "entities": [
                entity.to_dict() for entity in sorted(self.entities.values(), key=lambda item: item.entity_id)
            ],
            "edges": [edge.to_dict() for edge in sorted(self.edges.values(), key=lambda item: item.edge_id)],
            "errors": self.errors,
        }


def stable_id(*parts: str) -> str:
    content = "|".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


def normalize_key(value: str) -> str:
    return value.strip().strip("[]`\"'").lower()


def resolution_candidates(
    lookup: dict[tuple[str | None, str], list[Entity]],
    target_type: str | None,
    target_name: str,
) -> list[Entity]:
    if target_type == "service":
        for entity_types in (["service"], ["project"], ["repository"]):
            candidates = [
                candidate for entity_type in entity_types for candidate in lookup.get((entity_type, target_name), [])
            ]
            if candidates:
                return dedupe_entities(candidates)

    candidates: list[Entity] = []
    for entity_type in resolution_entity_types(target_type):
        candidates.extend(lookup.get((entity_type, target_name), []))
    if not candidates:
        candidates.extend(lookup.get((None, target_name), []))
    return dedupe_entities(candidates)


def resolution_entity_types(target_type: str | None) -> list[str | None]:
    if target_type == "sql_object":
        return ["sql_table", "sql_view", "sql_function", "stored_procedure"]
    if target_type == "service":
        return ["service", "project", "repository"]
    if target_type:
        return [target_type]
    return [None]


def choose_resolution(candidates: list[Entity], source_name: str) -> Entity | None:
    if not candidates:
        return None

    same_source = [candidate for candidate in candidates if candidate.source_name == source_name]
    if len(same_source) == 1:
        return same_source[0]
    if len(same_source) > 1:
        return None

    if len(candidates) == 1:
        return candidates[0]
    return None


def dedupe_entities(candidates: list[Entity]) -> list[Entity]:
    entities: dict[str, Entity] = {}
    for candidate in candidates:
        entities[candidate.entity_id] = candidate
    return list(entities.values())
