"""Public extraction contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.sources import ResolvedSource


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    path: Path
    entity: EntityFact
    ecosystem: str | None = None


@dataclass(frozen=True)
class FileScanContext:
    source: ResolvedSource
    repo_entity: EntityFact
    file_entity: EntityFact
    file_path: Path
    rel_path: str
    project: ProjectInfo | None = None


class FileExtractor(Protocol):
    name: str
    target_patterns: tuple[str, ...]
    parser_ids: tuple[str, ...]

    def can_process(self, rel_path: str) -> bool:
        """Return whether this extractor can scan a relative file path."""
        ...

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        """Extract facts from a file."""
        ...


__all__ = [
    "FileExtractor",
    "FileScanContext",
    "ProjectInfo",
]
