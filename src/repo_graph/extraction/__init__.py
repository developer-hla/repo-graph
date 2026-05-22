"""Extraction pipeline public API."""

from __future__ import annotations

from repo_graph.extraction.cached_builds import CachedBuildResult, build_cached_graph
from repo_graph.extraction.contracts import FileExtractor, FileScanContext, ProjectInfo, ScanResult
from repo_graph.extraction.facts import (
    EntityFact,
    EntityReference,
    Evidence,
    FactBatch,
    RelationshipFact,
    ScanIssue,
)
from repo_graph.extraction.orchestrator import MAX_FILE_BYTES, build_graph
from repo_graph.extraction.snapshots import snapshot_status, write_snapshots
from repo_graph.extraction.source_graphs import write_source_graphs

__all__ = [
    "MAX_FILE_BYTES",
    "CachedBuildResult",
    "EntityFact",
    "EntityReference",
    "Evidence",
    "FactBatch",
    "FileExtractor",
    "FileScanContext",
    "ProjectInfo",
    "RelationshipFact",
    "ScanIssue",
    "ScanResult",
    "build_cached_graph",
    "build_graph",
    "snapshot_status",
    "write_snapshots",
    "write_source_graphs",
]
