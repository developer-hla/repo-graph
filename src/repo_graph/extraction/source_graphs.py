"""Source-level graph artifacts for incremental builds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.orchestrator import MAX_FILE_BYTES, config_without_unsupported_sources
from repo_graph.extraction.registry import default_extractors
from repo_graph.extraction.snapshots import (
    parser_fingerprint,
    snapshot_root,
    source_snapshot,
    source_snapshot_path,
)
from repo_graph.extraction.source_scanner import scan_source, source_to_dict
from repo_graph.graph import Graph
from repo_graph.sources import ResolvedSource, resolve_sources, sync_sources


def write_source_graphs(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    scannable_config = config_without_unsupported_sources(config)
    sources = sync_sources(scannable_config) if sync_first else resolve_sources(scannable_config)
    root = snapshot_root(config)
    root.mkdir(parents=True, exist_ok=True)
    items = [write_source_graph(config, source, max_file_bytes=max_file_bytes) for source in sources]
    return {
        "artifact_dir": str(root),
        "count": len(items),
        "items": items,
    }


def write_source_graph(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    graph_data = source_graph_data(config, source, max_file_bytes=max_file_bytes)
    snapshot = source_snapshot(config, source, max_file_bytes=max_file_bytes)
    graph_path = source_graph_path(config, source)
    snapshot_path = source_snapshot_path(config, source)
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(json.dumps(graph_data, indent=2, sort_keys=True), encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    summary = graph_data["summary"]
    return {
        "source_name": source.name,
        "graph_path": str(graph_path),
        "snapshot_path": str(snapshot_path),
        "files_scanned": summary["files_scanned"],
        "entity_count": summary["entity_count"],
        "edge_count": summary["edge_count"],
        "error_count": summary["error_count"],
    }


def source_graph_data(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    graph = build_source_graph(config, source, max_file_bytes=max_file_bytes)
    data = graph.to_dict()
    data["metadata"].update(
        {
            "artifact_type": "source_graph",
            "parent_scope_name": config.name,
            "source_name": source.name,
            "parser_fingerprint": parser_fingerprint(),
            "resolution_status": "deferred_global",
        }
    )
    return data


def build_source_graph(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> Graph:
    graph = Graph(scope_name=config.name, sources=[source_to_dict(source)])
    scan_source(config, graph, source, max_file_bytes=max_file_bytes, extractors=default_extractors())
    return graph


def source_graph_path(config: RepoGraphConfig, source: ResolvedSource) -> Path:
    return source_snapshot_path(config, source).with_name("graph.json")
