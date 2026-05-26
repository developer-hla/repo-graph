"""Build, load, sync, refresh, and job response workflows."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from repo_graph.api_runtime.requests import (
    BuildLoadRequest,
    BuildRequest,
    LoadRequest,
    RefreshChangedRequest,
    RefreshRequest,
    SnapshotStatusRequest,
    SyncRequest,
)
from repo_graph.api_runtime.settings import (
    RuntimeSettings,
    load_runtime_config,
    resolve_graph_path,
    validate_max_file_bytes,
)
from repo_graph.extraction import build_graph, snapshot_status
from repo_graph.jobs import JobRegistry
from repo_graph.refresh import refresh_graph
from repo_graph.sources import config_summary, inspect_sources, sync_sources_with_status
from repo_graph.storage import load_graph_path


def config_response(settings: RuntimeSettings, config_path: str | None = None) -> dict[str, Any]:
    return config_summary(load_runtime_config(settings, config_path))


def configured_sources_response(settings: RuntimeSettings, config_path: str | None = None) -> dict[str, Any]:
    config = load_runtime_config(settings, config_path)
    items = inspect_sources(config)
    return {
        "config": config_summary(config),
        "items": items,
        "count": len(items),
        "ready_count": sum(1 for item in items if item["ready"]),
        "problem_count": sum(1 for item in items if item["problems"]),
    }


def sync_response(settings: RuntimeSettings, request: SyncRequest) -> dict[str, Any]:
    config = load_runtime_config(settings, request.config_path)
    items = sync_sources_with_status(config)
    failed_count = sum(1 for item in items if item.get("sync", {}).get("status") == "failed")
    return {
        "status": "failed" if failed_count else "synced",
        "config": config_summary(config),
        "items": items,
        "count": len(items),
        "synced_count": len(items) - failed_count,
        "failed_count": failed_count,
    }


def submit_sync_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: SyncRequest,
) -> dict[str, Any]:
    return registry.submit(
        "sync",
        request.model_dump(),
        lambda: sync_response(settings, request),
    )


def snapshot_status_response(settings: RuntimeSettings, request: SnapshotStatusRequest) -> dict[str, Any]:
    config = load_runtime_config(settings, request.config_path)
    return snapshot_status(
        config,
        sync_first=request.sync,
        max_file_bytes=validate_max_file_bytes(request.max_file_bytes),
    )


def build_response(settings: RuntimeSettings, request: BuildRequest) -> dict[str, Any]:
    config = load_runtime_config(settings, request.config_path)
    output_path = resolve_graph_path(settings, request.output_path, config=config)
    graph = build_graph(
        config,
        sync_first=request.sync,
        max_file_bytes=validate_max_file_bytes(request.max_file_bytes),
        strict=request.strict,
    )
    graph_data = graph.to_dict()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(graph_data, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "status": "built",
        "config_path": str(config.config_path),
        "output_path": str(output_path),
        "summary": graph_data["summary"],
    }


def load_response(settings: RuntimeSettings, request: LoadRequest) -> dict[str, Any]:
    graph_path = resolve_graph_path(settings, request.graph_path)
    if not graph_path.exists():
        raise FileNotFoundError(f"Graph JSON not found: {graph_path}")
    summary = load_graph_path(graph_path, settings.neo4j_settings(), clear_existing=request.clear_existing)
    return {
        "status": "loaded",
        "graph_path": str(graph_path),
        "summary": summary.to_dict(),
    }


def build_load_response(settings: RuntimeSettings, request: BuildLoadRequest) -> dict[str, Any]:
    build_result = build_response(settings, request)
    load_result = load_response(
        settings,
        LoadRequest(graph_path=build_result["output_path"], clear_existing=request.clear_existing),
    )
    return {
        "status": "built_and_loaded",
        "build": build_result,
        "load": load_result,
    }


def refresh_response(settings: RuntimeSettings, request: RefreshRequest) -> dict[str, Any]:
    config = load_runtime_config(settings, request.config_path)
    output_path = resolve_graph_path(settings, request.output_path, config=config)
    return refresh_graph(
        config,
        output_path,
        sync_first=request.sync,
        max_file_bytes=validate_max_file_bytes(request.max_file_bytes),
        strict=request.strict,
        load=request.load,
        settings=settings.neo4j_settings() if request.load else None,
    )


def refresh_changed_response(settings: RuntimeSettings, request: RefreshChangedRequest) -> dict[str, Any]:
    config = load_runtime_config(settings, request.config_path)
    max_file_bytes = validate_max_file_bytes(request.max_file_bytes)
    output_path = resolve_graph_path(settings, request.output_path, config=config)
    snapshot = snapshot_status(config, sync_first=request.sync, max_file_bytes=max_file_bytes)
    changed_sources = snapshot_changed_source_names(snapshot)
    if not changed_sources:
        return {
            "status": "skipped",
            "reason": "no_changed_sources",
            "config_path": str(config.config_path),
            "output": str(output_path),
            "snapshot": snapshot,
            "changed_sources": [],
            "neo4j_load_mode": "skipped",
            "rebuilt_count": 0,
            "reused_count": 0,
            "changes": {
                "changed_count": 0,
                "changed_sources": [],
            },
            "cache": {
                "rebuilt_count": 0,
                "reused_count": 0,
            },
            "load": {
                "requested": True,
                "action": "skipped",
                "reason": "no_changed_sources",
                "replace_sources": [],
            },
            "refresh": None,
        }

    refresh = refresh_graph(
        config,
        output_path,
        sync_first=False,
        max_file_bytes=max_file_bytes,
        strict=request.strict,
        load=True,
        settings=settings.neo4j_settings(),
    )
    cache = mapping_value(refresh.get("cache"))
    load = mapping_value(refresh.get("load"))
    return {
        "status": "refreshed",
        "reason": "changed_sources",
        "config_path": str(config.config_path),
        "output": str(output_path),
        "snapshot": snapshot,
        "changed_sources": changed_sources,
        "neo4j_load_mode": load.get("action", "unknown"),
        "rebuilt_count": cache.get("rebuilt_count", 0),
        "reused_count": cache.get("reused_count", 0),
        "changes": refresh.get("changes", {}),
        "cache": refresh.get("cache", {}),
        "load": refresh.get("load", {}),
        "refresh": refresh,
    }


def snapshot_changed_source_names(snapshot: Mapping[str, Any]) -> list[str]:
    items = snapshot.get("items", [])
    if not isinstance(items, list):
        return []
    return [
        item["source_name"]
        for item in items
        if isinstance(item, Mapping) and item.get("changed") and isinstance(item.get("source_name"), str)
    ]


def mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def submit_build_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: BuildRequest,
) -> dict[str, Any]:
    return registry.submit(
        "build",
        request.model_dump(),
        lambda: build_response(settings, request),
    )


def submit_build_load_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: BuildLoadRequest,
) -> dict[str, Any]:
    return registry.submit(
        "build-load",
        request.model_dump(),
        lambda: build_load_response(settings, request),
    )


def submit_refresh_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: RefreshRequest,
) -> dict[str, Any]:
    return registry.submit(
        "refresh",
        request.model_dump(),
        lambda: refresh_response(settings, request),
    )


def submit_refresh_changed_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: RefreshChangedRequest,
) -> dict[str, Any]:
    return registry.submit(
        "refresh-changed",
        request.model_dump(),
        lambda: refresh_changed_response(settings, request),
    )


def submit_snapshot_status_job(
    registry: JobRegistry,
    settings: RuntimeSettings,
    request: SnapshotStatusRequest,
) -> dict[str, Any]:
    return registry.submit(
        "snapshot-status",
        request.model_dump(),
        lambda: snapshot_status_response(settings, request),
    )


def job_response(registry: JobRegistry, job_id: str) -> dict[str, Any]:
    return registry.get(job_id)


def jobs_response(
    registry: JobRegistry,
    status: str | None,
    kind: str | None,
    limit: int,
) -> dict[str, Any]:
    items = registry.list_jobs(status=status, kind=kind, limit=limit)
    return {
        "items": items,
        "count": len(items),
    }


__all__ = [
    "build_load_response",
    "build_response",
    "config_response",
    "configured_sources_response",
    "job_response",
    "jobs_response",
    "load_response",
    "mapping_value",
    "refresh_changed_response",
    "refresh_response",
    "snapshot_changed_source_names",
    "snapshot_status_response",
    "submit_build_job",
    "submit_build_load_job",
    "submit_refresh_changed_job",
    "submit_refresh_job",
    "submit_snapshot_status_job",
    "submit_sync_job",
    "sync_response",
]
