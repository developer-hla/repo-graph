"""Public extraction contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from repo_graph.graph import Edge, Entity
from repo_graph.sources import ResolvedSource


@dataclass
class ScanResult:
    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: ScanResult) -> None:
        self.entities.extend(other.entities)
        self.edges.extend(other.edges)
        self.errors.extend(other.errors)


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    path: Path
    entity: Entity
    ecosystem: str | None = None


@dataclass(frozen=True)
class FileScanContext:
    source: ResolvedSource
    repo_entity: Entity
    file_entity: Entity
    file_path: Path
    rel_path: str
    project: ProjectInfo | None = None


class FileExtractor(Protocol):
    name: str

    def can_process(self, rel_path: str) -> bool:
        """Return whether this extractor can scan a relative file path."""
        ...

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        """Extract entities and edges from a file."""
        ...


__all__ = [
    "FileExtractor",
    "FileScanContext",
    "ProjectInfo",
    "ScanResult",
]
