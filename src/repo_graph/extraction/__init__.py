"""Extraction pipeline public API."""

from __future__ import annotations

from repo_graph.extraction.facts import (
    EntityFact,
    EntityReference,
    Evidence,
    FactBatch,
    RelationshipFact,
    ScanIssue,
)

MAX_FILE_BYTES = 1_000_000

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
    "SourceScanResult",
    "build_cached_graph",
    "build_graph",
    "snapshot_status",
    "write_snapshots",
    "write_source_graphs",
]


def __getattr__(name: str) -> object:
    if name == "FileExtractor":
        from repo_graph.extraction.contracts import FileExtractor

        return FileExtractor
    if name == "FileScanContext":
        from repo_graph.extraction.contracts import FileScanContext

        return FileScanContext
    if name == "ProjectInfo":
        from repo_graph.extraction.contracts import ProjectInfo

        return ProjectInfo
    if name == "CachedBuildResult":
        from repo_graph.extraction.cached_builds import CachedBuildResult

        return CachedBuildResult
    if name == "SourceScanResult":
        from repo_graph.extraction.source_scanner import SourceScanResult

        return SourceScanResult
    if name == "build_cached_graph":
        from repo_graph.extraction.cached_builds import build_cached_graph

        return build_cached_graph
    if name == "build_graph":
        from repo_graph.extraction.orchestrator import build_graph

        return build_graph
    if name == "snapshot_status":
        from repo_graph.extraction.snapshots import snapshot_status

        return snapshot_status
    if name == "write_snapshots":
        from repo_graph.extraction.snapshots import write_snapshots

        return write_snapshots
    if name == "write_source_graphs":
        from repo_graph.extraction.source_graphs import write_source_graphs

        return write_source_graphs
    raise AttributeError(f"module 'repo_graph.extraction' has no attribute {name!r}")
