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
    "FactValidationIssue",
    "FileExtractor",
    "FileScanContext",
    "ProjectInfo",
    "RelationshipFact",
    "ScanIssue",
    "ScannerMetadataMixin",
    "ScannerSpec",
    "SourceScanResult",
    "build_cached_graph",
    "build_graph",
    "scanner_spec",
    "snapshot_status",
    "validate_fact_batch",
    "validate_interaction_relationship_fact",
    "validate_relationship_facts",
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
    if name == "ScannerMetadataMixin":
        from repo_graph.extraction.contracts import ScannerMetadataMixin

        return ScannerMetadataMixin
    if name == "ScannerSpec":
        from repo_graph.extraction.contracts import ScannerSpec

        return ScannerSpec
    if name == "scanner_spec":
        from repo_graph.extraction.contracts import scanner_spec

        return scanner_spec
    if name == "FactValidationIssue":
        from repo_graph.extraction.fact_validation import FactValidationIssue

        return FactValidationIssue
    if name == "validate_fact_batch":
        from repo_graph.extraction.fact_validation import validate_fact_batch

        return validate_fact_batch
    if name == "validate_interaction_relationship_fact":
        from repo_graph.extraction.fact_validation import validate_interaction_relationship_fact

        return validate_interaction_relationship_fact
    if name == "validate_relationship_facts":
        from repo_graph.extraction.fact_validation import validate_relationship_facts

        return validate_relationship_facts
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
