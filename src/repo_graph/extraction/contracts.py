"""Public extraction contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from repo_graph.extraction.facts import FactBatch
from repo_graph.graph import Entity
from repo_graph.sources import ResolvedSource


@dataclass
class ScanResult:
    facts: FactBatch = field(default_factory=FactBatch)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: ScanResult) -> None:
        self.facts.extend(other.facts)
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
        """Extract facts from a file."""
        ...


__all__ = [
    "FileExtractor",
    "FileScanContext",
    "ProjectInfo",
    "ScanResult",
]
