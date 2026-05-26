"""Typed extraction facts emitted by scanners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Evidence:
    source_name: str
    parser: str
    file_path: str | None = None
    line_number: int | None = None
    confidence: str = "medium"


@dataclass(frozen=True)
class EntityReference:
    entity_type: str
    name: str
    source_name: str | None = None
    file_path: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class EntityFact:
    entity_type: str
    name: str
    source_name: str
    file_path: str | None = None
    line_number: int | None = None
    aliases: frozenset[str] = frozenset()
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def reference(self) -> EntityReference:
        return EntityReference(
            entity_type=self.entity_type,
            name=self.name,
            source_name=self.source_name,
            file_path=self.file_path,
        )


@dataclass(frozen=True)
class RelationshipFact:
    from_ref: EntityReference
    to_ref: EntityReference
    edge_type: str
    evidence: Evidence
    identity_key: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    resolved: bool | None = None

    @property
    def from_name(self) -> str:
        return self.from_ref.name

    @property
    def from_type(self) -> str:
        return self.from_ref.entity_type

    @property
    def to_name(self) -> str:
        return self.to_ref.name

    @property
    def to_type(self) -> str:
        return self.to_ref.entity_type

    @property
    def to_entity_id(self) -> str | None:
        return self.to_ref.entity_id

    @property
    def source_name(self) -> str:
        return self.evidence.source_name

    @property
    def parser(self) -> str:
        return self.evidence.parser

    @property
    def confidence(self) -> str:
        return self.evidence.confidence


@dataclass(frozen=True)
class ScanIssue:
    message: str
    evidence: Evidence


@dataclass
class FactBatch:
    entities: list[EntityFact] = field(default_factory=list)
    relationships: list[RelationshipFact] = field(default_factory=list)
    issues: list[ScanIssue] = field(default_factory=list)

    def extend(self, other: FactBatch) -> None:
        self.entities.extend(other.entities)
        self.relationships.extend(other.relationships)
        self.issues.extend(other.issues)


__all__ = [
    "EntityFact",
    "EntityReference",
    "Evidence",
    "FactBatch",
    "RelationshipFact",
    "ScanIssue",
]
