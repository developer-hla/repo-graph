"""One-command incremental refresh workflow."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from repo_graph.cached_builds import build_cached_graph
from repo_graph.config import RepoGraphConfig
from repo_graph.scanner import MAX_FILE_BYTES
from repo_graph.storage.neo4j import Neo4jSettings, load_graph_path, read_graph_scope

ScopeReader = Callable[[Neo4jSettings], Mapping[str, Any]]
GraphLoader = Callable[..., Any]


def refresh_graph(
    config: RepoGraphConfig,
    output_path: Path,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    strict: bool = False,
    load: bool = False,
    settings: Neo4jSettings | None = None,
    scope_reader: ScopeReader = read_graph_scope,
    graph_loader: GraphLoader = load_graph_path,
) -> dict[str, Any]:
    cached_result = build_cached_graph(
        config,
        sync_first=sync_first,
        max_file_bytes=max_file_bytes,
        strict=strict,
    )
    graph_data = cached_result.graph.to_dict()
    graph_data["metadata"].update(
        {
            "build_mode": "cached",
            "source_artifact_dir": cached_result.cache_summary["artifact_dir"],
            "source_artifact_reused_count": cached_result.cache_summary["reused_count"],
            "source_artifact_rebuilt_count": cached_result.cache_summary["rebuilt_count"],
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph_data, indent=2, sort_keys=True), encoding="utf-8")

    changed_sources = changed_source_names(cached_result.cache_summary)
    return {
        "status": "refreshed",
        "config_path": str(config.config_path),
        "output": str(output_path),
        "summary": graph_data["summary"],
        "cache": cached_result.cache_summary,
        "changes": {
            "changed_count": len(changed_sources),
            "changed_sources": changed_sources,
            "rebuilt_sources": source_names_by_status(cached_result.cache_summary, "rebuilt"),
            "reused_sources": source_names_by_status(cached_result.cache_summary, "reused"),
        },
        "load": refresh_load_result(
            output_path,
            graph_scope_name=config.name,
            graph_source_names=graph_source_names(graph_data),
            changed_sources=changed_sources,
            load=load,
            settings=settings,
            scope_reader=scope_reader,
            graph_loader=graph_loader,
        ),
    }


def changed_source_names(cache_summary: Mapping[str, Any]) -> list[str]:
    return [
        str(item["source_name"])
        for item in cache_items(cache_summary)
        if bool(item.get("changed")) and isinstance(item.get("source_name"), str)
    ]


def source_names_by_status(cache_summary: Mapping[str, Any], status: str) -> list[str]:
    return [
        str(item["source_name"])
        for item in cache_items(cache_summary)
        if item.get("status") == status and isinstance(item.get("source_name"), str)
    ]


def cache_items(cache_summary: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = cache_summary.get("items", [])
    return [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []


def graph_source_names(graph_data: Mapping[str, Any]) -> tuple[str, ...]:
    sources = graph_data.get("sources", [])
    if not isinstance(sources, list):
        return ()
    return source_names_from_items(sources)


def loaded_source_names(scope: Mapping[str, Any]) -> tuple[str, ...]:
    sources = scope.get("sources", [])
    if not isinstance(sources, list):
        return ()
    return source_names_from_items(sources)


def source_names_from_items(sources: list[Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            source["name"] for source in sources if isinstance(source, Mapping) and isinstance(source.get("name"), str)
        )
    )


def refresh_load_result(
    graph_path: Path,
    graph_scope_name: str,
    graph_source_names: tuple[str, ...],
    changed_sources: list[str],
    load: bool,
    settings: Neo4jSettings | None,
    scope_reader: ScopeReader,
    graph_loader: GraphLoader,
) -> dict[str, Any]:
    if not load:
        return {"requested": False, "action": "not_requested"}
    if settings is None:
        raise ValueError("Neo4j settings are required when refresh load is requested.")

    current_scope_payload = dict(scope_reader(settings))
    current_scope = current_scope_payload.get("scope_name")
    if not current_scope_payload.get("loaded") or not current_scope:
        summary = graph_loader(graph_path, settings, clear_existing=True)
        return load_result("full_load", "graph_not_loaded", [], summary)
    if current_scope != graph_scope_name:
        summary = graph_loader(graph_path, settings, clear_existing=True)
        return load_result("full_load", "loaded_scope_mismatch", [], summary)
    if loaded_source_names(current_scope_payload) != graph_source_names:
        summary = graph_loader(graph_path, settings, clear_existing=True)
        return load_result("full_load", "loaded_sources_mismatch", [], summary)
    if not changed_sources:
        return {
            "requested": True,
            "action": "skipped",
            "reason": "no_changed_sources",
            "replace_sources": [],
        }

    summary = graph_loader(graph_path, settings, clear_existing=False, replace_sources=changed_sources)
    return load_result("replace_sources", "changed_sources", changed_sources, summary)


def load_result(action: str, reason: str, replace_sources: list[str], summary: Any) -> dict[str, Any]:
    return {
        "requested": True,
        "action": action,
        "reason": reason,
        "replace_sources": replace_sources,
        "summary": summary.to_dict(),
    }
