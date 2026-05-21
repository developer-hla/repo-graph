"""Cached graph builds from source-level artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_graph.config import RepoGraphConfig
from repo_graph.graph import Edge, Entity, Graph
from repo_graph.scanner import MAX_FILE_BYTES, apply_dependency_filter, source_to_dict
from repo_graph.snapshots import (
    compare_source_snapshot,
    snapshot_root,
    source_snapshot_path,
)
from repo_graph.source_graphs import source_graph_path, write_source_graph
from repo_graph.sources import ResolvedSource, resolve_sources, sync_sources


@dataclass(frozen=True)
class CachedBuildResult:
    graph: Graph
    cache_summary: dict[str, Any]


def build_cached_graph(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    strict: bool = False,
) -> CachedBuildResult:
    sources = sync_sources(config) if sync_first else resolve_sources(config)
    snapshot_root(config).mkdir(parents=True, exist_ok=True)
    source_results = [source_cache_item(config, source, max_file_bytes) for source in sources]
    items = [item for item, _graph_data in source_results]
    graph_payloads = [graph_data for _item, graph_data in source_results]
    graph = merge_source_graphs(config.name, [source_to_dict(source) for source in sources], graph_payloads)
    graph.resolve_edges()
    apply_dependency_filter(graph, config)
    if strict and graph.errors:
        error_summary = "; ".join(graph.errors[:5])
        raise RuntimeError(f"Cached graph build failed with {len(graph.errors)} scanner errors: {error_summary}")
    return CachedBuildResult(
        graph=graph,
        cache_summary={
            "artifact_dir": str(snapshot_root(config)),
            "source_count": len(items),
            "reused_count": sum(1 for item in items if item["status"] == "reused"),
            "rebuilt_count": sum(1 for item in items if item["status"] == "rebuilt"),
            "items": items,
        },
    )


def source_cache_item(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    comparison = compare_source_snapshot(config, source, max_file_bytes=max_file_bytes)
    graph_path = source_graph_path(config, source)
    snapshot_path = source_snapshot_path(config, source)
    reasons = list(comparison.reasons)
    graph_missing = not graph_path.exists()
    if graph_missing:
        reasons.append("graph_missing")

    status = "reused"
    if comparison.changed or graph_missing:
        write_source_graph(config, source, max_file_bytes=max_file_bytes)
        status = "rebuilt"

    graph_data = load_source_graph_data(graph_path)
    summary = mapping_value(graph_data.get("summary"))
    return (
        {
            "source_name": source.name,
            "status": status,
            "changed": comparison.changed,
            "reasons": reasons,
            "graph_path": str(graph_path),
            "snapshot_path": str(snapshot_path),
            "files_scanned": int_value(summary.get("files_scanned")),
            "entity_count": int_value(summary.get("entity_count")),
            "edge_count": int_value(summary.get("edge_count")),
            "error_count": int_value(summary.get("error_count")),
        },
        graph_data,
    )


def load_source_graph_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Source graph must be a JSON object: {path}")
    metadata = mapping_value(data.get("metadata"))
    if metadata.get("artifact_type") != "source_graph":
        raise ValueError(f"Source graph is missing artifact metadata: {path}")
    return data


def merge_source_graphs(
    scope_name: str,
    sources: list[dict[str, str | None]],
    source_graphs: list[dict[str, Any]],
) -> Graph:
    graph = Graph(scope_name=scope_name, sources=sources)
    for source_graph in source_graphs:
        merge_source_graph(graph, source_graph)
    return graph


def merge_source_graph(graph: Graph, source_graph: Mapping[str, Any]) -> None:
    for entity_data in list_value(source_graph.get("entities")):
        graph.add_entity(entity_from_dict(entity_data))
    for edge_data in list_value(source_graph.get("edges")):
        graph.add_edge(edge_from_dict(edge_data))
    summary = mapping_value(source_graph.get("summary"))
    graph.files_scanned += int_value(summary.get("files_scanned"))
    graph.errors.extend(str(error) for error in list_value(source_graph.get("errors")))


def entity_from_dict(data: Any) -> Entity:
    item = mapping_value(data)
    aliases = {str(alias) for alias in list_value(item.get("aliases"))}
    return Entity(
        entity_type=required_str(item, "entity_type"),
        name=required_str(item, "name"),
        source_name=required_str(item, "source_name"),
        file_path=optional_str(item.get("file_path")),
        line_number=optional_int(item.get("line_number")),
        aliases=aliases,
        properties=dict_value(item.get("properties")),
    )


def edge_from_dict(data: Any) -> Edge:
    item = mapping_value(data)
    return Edge(
        from_entity_id=required_str(item, "from_entity_id"),
        from_name=required_str(item, "from_name"),
        from_type=required_str(item, "from_type"),
        to_name=required_str(item, "to_name"),
        to_type=optional_str(item.get("to_type")),
        to_entity_id=optional_str(item.get("to_entity_id")),
        edge_type=required_str(item, "edge_type"),
        resolved=bool(item.get("resolved")),
        source_name=required_str(item, "source_name"),
        file_path=optional_str(item.get("file_path")),
        line_number=optional_int(item.get("line_number")),
        identity_key=optional_str(item.get("identity_key")),
        confidence=optional_str(item.get("confidence")) or "medium",
        parser=optional_str(item.get("parser")) or "unknown",
        properties=dict_value(item.get("properties")),
    )


def required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Source graph item is missing required string field: {key}")
    return value


def optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def int_value(value: Any) -> int:
    return value if isinstance(value, int) else 0


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
