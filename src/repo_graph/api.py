"""HTTP API runtime for Repo Graph."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from repo_graph import __version__
from repo_graph.config import RepoGraphConfig, load_config
from repo_graph.jobs import JobRegistry
from repo_graph.refresh import refresh_graph
from repo_graph.reports import unresolved_report_from_items
from repo_graph.scanner import MAX_FILE_BYTES, build_graph
from repo_graph.snapshots import snapshot_status
from repo_graph.sources import config_summary, inspect_sources, sync_sources_with_status
from repo_graph.storage.neo4j import (
    Neo4jSettings,
    get_entity,
    get_entity_neighbors,
    list_unresolved_edges,
    load_graph_path,
    read_graph_scope,
    read_graph_stats,
    search_entities,
)

DEFAULT_CONFIG_PATH = Path("config/local-example.yaml")
DEFAULT_NEO4J_URI = "bolt://neo4j:7687"
DEFAULT_NEO4J_PASSWORD = "repo-graph-password"
UNRESOLVED_REPORT_EDGE_LIMIT = 1000
UI_DIR = Path(__file__).with_name("ui")


@dataclass(frozen=True)
class RuntimeSettings:
    config_path: Path | None = DEFAULT_CONFIG_PATH
    neo4j_uri: str | None = DEFAULT_NEO4J_URI
    neo4j_user: str | None = "neo4j"
    neo4j_password: str | None = DEFAULT_NEO4J_PASSWORD
    neo4j_database: str | None = None

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> RuntimeSettings:
        return cls(
            config_path=config_path or env_path("REPO_GRAPH_CONFIG", DEFAULT_CONFIG_PATH),
            neo4j_uri=env_value("REPO_GRAPH_NEO4J_URI", DEFAULT_NEO4J_URI),
            neo4j_user=env_value("REPO_GRAPH_NEO4J_USER", "neo4j"),
            neo4j_password=env_value("REPO_GRAPH_NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
            neo4j_database=env_value("REPO_GRAPH_NEO4J_DATABASE", None),
        )

    def neo4j_settings(self) -> Neo4jSettings:
        if not self.neo4j_uri or not self.neo4j_user or not self.neo4j_password:
            raise ValueError("Neo4j URI, user, and password must be configured.")
        return Neo4jSettings(
            uri=self.neo4j_uri,
            user=self.neo4j_user,
            password=self.neo4j_password,
            database=self.neo4j_database,
        )


class LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_path: str | None = None
    clear_existing: bool = True


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None
    output_path: str | None = None
    sync: bool = False
    strict: bool = False
    max_file_bytes: int = MAX_FILE_BYTES


class BuildLoadRequest(BuildRequest):
    clear_existing: bool = True


class RefreshRequest(BuildRequest):
    load: bool = False


class SnapshotStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None
    sync: bool = False
    max_file_bytes: int = MAX_FILE_BYTES


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_path: str | None = None


def env_value(name: str, default: str | None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def env_path(name: str, default: Path | None) -> Path | None:
    value = env_value(name, None)
    if value is None:
        return default
    return Path(value)


def health_payload() -> dict[str, str]:
    return {
        "service": "repo-graph",
        "status": "ok",
        "version": __version__,
    }


def manifest_payload(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "service": "repo-graph",
        "version": __version__,
        "schema_version": "1",
        "config": {
            "path": str(settings.config_path) if settings.config_path else None,
            "configured": settings.config_path is not None,
        },
        "graph_store": {
            "type": "neo4j",
            "uri": settings.neo4j_uri,
            "user": settings.neo4j_user,
            "database": settings.neo4j_database,
            "configured": settings.neo4j_uri is not None,
        },
        "endpoints": [
            {"method": "GET", "path": "/health", "available": True},
            {"method": "GET", "path": "/ui", "available": True},
            {"method": "GET", "path": "/manifest", "available": True},
            {"method": "GET", "path": "/config", "available": True},
            {"method": "GET", "path": "/sources/configured", "available": True},
            {"method": "POST", "path": "/sync", "available": True},
            {"method": "POST", "path": "/build", "available": True},
            {"method": "POST", "path": "/build-load", "available": True},
            {"method": "POST", "path": "/snapshot/status", "available": True},
            {"method": "POST", "path": "/refresh", "available": True},
            {"method": "POST", "path": "/jobs/sync", "available": True},
            {"method": "POST", "path": "/jobs/build", "available": True},
            {"method": "POST", "path": "/jobs/build-load", "available": True},
            {"method": "POST", "path": "/jobs/snapshot-status", "available": True},
            {"method": "POST", "path": "/jobs/refresh", "available": True},
            {"method": "GET", "path": "/jobs", "available": True},
            {"method": "GET", "path": "/jobs/{job_id}", "available": True},
            {"method": "POST", "path": "/load", "available": True},
            {"method": "POST", "path": "/query", "available": False},
            {"method": "GET", "path": "/scope", "available": True},
            {"method": "GET", "path": "/sources", "available": True},
            {"method": "GET", "path": "/stats", "available": True},
            {"method": "GET", "path": "/entities/search", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}/neighbors", "available": True},
            {"method": "GET", "path": "/edges/unresolved", "available": True},
            {"method": "GET", "path": "/reports/unresolved", "available": True},
        ],
        "agent_guidance": {
            "purpose": "Discover the local Repo Graph runtime and supported API surface.",
            "query_api_status": "safe read endpoints available",
            "raw_cypher_status": "planned",
            "source_status": "available",
            "sync_status": "available",
            "build_api_status": "available",
            "snapshot_status": "available",
            "refresh_status": "available",
            "job_api_status": "in-memory local runtime only",
            "graph_loader_status": "available",
            "scope_status": "available",
            "unresolved_report_status": "available",
            "ui_status": "available",
        },
    }


def resolve_config_path(settings: RuntimeSettings, config_path: str | None) -> Path:
    if config_path:
        return Path(config_path).expanduser().resolve()
    if settings.config_path is None:
        raise ValueError("No config path provided.")
    return settings.config_path.resolve()


def default_graph_path(settings: RuntimeSettings) -> Path:
    if settings.config_path is None:
        return Path(".repo-graph/output/graph.json").resolve()
    config = load_config(settings.config_path)
    return config.output_dir / "graph.json"


def resolve_graph_path(
    settings: RuntimeSettings,
    graph_path: str | None,
    config: RepoGraphConfig | None = None,
) -> Path:
    if graph_path is None:
        if config is not None:
            return config.output_dir / "graph.json"
        return default_graph_path(settings)
    path = Path(graph_path).expanduser()
    if path.is_absolute():
        return path
    if config is not None:
        return (config.config_path.parent / path).resolve()
    return path.resolve()


def validate_max_file_bytes(value: int) -> int:
    if value < 1:
        raise ValueError("max_file_bytes must be at least 1.")
    return value


def load_runtime_config(settings: RuntimeSettings, config_path: str | None = None) -> RepoGraphConfig:
    return load_config(resolve_config_path(settings, config_path))


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
    config = load_config(resolve_config_path(settings, request.config_path))
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
    config = load_config(resolve_config_path(settings, request.config_path))
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


def search_entities_response(
    settings: RuntimeSettings,
    query: str | None,
    entity_type: str | None,
    source_name: str | None,
    limit: int,
) -> dict[str, Any]:
    items = search_entities(
        settings.neo4j_settings(),
        query=query,
        entity_type=entity_type,
        source_name=source_name,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


def scope_response(settings: RuntimeSettings) -> dict[str, Any]:
    return read_graph_scope(settings.neo4j_settings())


def sources_response(settings: RuntimeSettings) -> dict[str, Any]:
    scope = scope_response(settings)
    items = scope.get("sources", [])
    if not isinstance(items, list):
        items = []
    return {
        "items": items,
        "count": len(items),
        "loaded": bool(scope.get("loaded")),
        "scope_name": scope.get("scope_name"),
        "generated_at": scope.get("generated_at"),
    }


def entity_response(settings: RuntimeSettings, entity_id: str) -> dict[str, Any]:
    entity = get_entity(settings.neo4j_settings(), entity_id)
    if entity is None:
        raise KeyError(entity_id)
    return entity


def neighbors_response(
    settings: RuntimeSettings,
    entity_id: str,
    direction: str,
    edge_type: str | None,
    depth: int,
    limit: int,
) -> dict[str, Any]:
    if depth != 1:
        raise ValueError("Only depth=1 is supported.")
    items = get_entity_neighbors(
        settings.neo4j_settings(),
        entity_id,
        direction=direction,
        edge_type=edge_type,
        limit=limit,
    )
    return {
        "entity_id": entity_id,
        "direction": direction,
        "depth": depth,
        "items": items,
        "count": len(items),
    }


def unresolved_edges_response(
    settings: RuntimeSettings,
    source_name: str | None,
    edge_type: str | None,
    limit: int,
) -> dict[str, Any]:
    items = list_unresolved_edges(settings.neo4j_settings(), source_name=source_name, edge_type=edge_type, limit=limit)
    return {"items": items, "count": len(items)}


def unresolved_report_response(
    settings: RuntimeSettings,
    source_name: str | None,
    edge_type: str | None,
    limit: int,
    examples: int,
) -> dict[str, Any]:
    items = list_unresolved_edges(
        settings.neo4j_settings(),
        source_name=source_name,
        edge_type=edge_type,
        limit=UNRESOLVED_REPORT_EDGE_LIMIT,
    )
    report = unresolved_report_from_items(
        items,
        source_name=source_name,
        edge_type=edge_type,
        group_limit=limit,
        examples_per_group=examples,
    )
    report["edge_sample_limit"] = UNRESOLVED_REPORT_EDGE_LIMIT
    report["edge_sample_truncated"] = len(items) >= UNRESOLVED_REPORT_EDGE_LIMIT
    return report


def ui_index_path() -> Path:
    return UI_DIR / "index.html"


def neo4j_http_exception(operation: str, exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=f"Entity not found: {exc.args[0]}")
    return HTTPException(status_code=503, detail=f"Neo4j {operation} failed: {exc}")


def create_app(settings: RuntimeSettings | None = None, job_registry: JobRegistry | None = None) -> FastAPI:
    runtime_settings = settings or RuntimeSettings.from_env()
    registry = job_registry or JobRegistry()
    app = FastAPI(title="Repo Graph", version=__version__)
    app.mount("/ui/assets", StaticFiles(directory=UI_DIR), name="repo-graph-ui-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def ui() -> FileResponse:
        return FileResponse(ui_index_path())

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return manifest_payload(runtime_settings)

    @app.get("/config")
    def config(config_path: str | None = None) -> dict[str, Any]:
        try:
            return config_response(runtime_settings, config_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/sources/configured")
    def configured_sources(config_path: str | None = None) -> dict[str, Any]:
        try:
            return configured_sources_response(runtime_settings, config_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/sync")
    def sync(request: SyncRequest) -> dict[str, Any]:
        try:
            return sync_response(runtime_settings, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/build")
    def build(request: BuildRequest) -> dict[str, Any]:
        try:
            return build_response(runtime_settings, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph build failed: {exc}") from exc

    @app.post("/build-load")
    def build_load(request: BuildLoadRequest) -> dict[str, Any]:
        try:
            return build_load_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph build-load failed: {exc}") from exc

    @app.post("/refresh")
    def refresh(request: RefreshRequest) -> dict[str, Any]:
        try:
            return refresh_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph refresh failed: {exc}") from exc

    @app.post("/snapshot/status")
    def snapshot_status_endpoint(request: SnapshotStatusRequest) -> dict[str, Any]:
        try:
            return snapshot_status_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot status failed: {exc}") from exc

    @app.post("/jobs/build", status_code=202)
    def submit_build(request: BuildRequest) -> dict[str, Any]:
        return submit_build_job(registry, runtime_settings, request)

    @app.post("/jobs/build-load", status_code=202)
    def submit_build_load(request: BuildLoadRequest) -> dict[str, Any]:
        return submit_build_load_job(registry, runtime_settings, request)

    @app.post("/jobs/sync", status_code=202)
    def submit_sync(request: SyncRequest) -> dict[str, Any]:
        return submit_sync_job(registry, runtime_settings, request)

    @app.post("/jobs/refresh", status_code=202)
    def submit_refresh(request: RefreshRequest) -> dict[str, Any]:
        return submit_refresh_job(registry, runtime_settings, request)

    @app.post("/jobs/snapshot-status", status_code=202)
    def submit_snapshot_status(request: SnapshotStatusRequest) -> dict[str, Any]:
        return submit_snapshot_status_job(registry, runtime_settings, request)

    @app.get("/jobs")
    def list_jobs(
        status: str | None = None,
        kind: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return jobs_response(registry, status, kind, limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return job_response(registry, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Job not found: {exc.args[0]}") from exc

    @app.post("/load")
    def load(request: LoadRequest) -> dict[str, Any]:
        try:
            return load_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j load failed: {exc}") from exc

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        try:
            return read_graph_stats(runtime_settings.neo4j_settings())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j stats failed: {exc}") from exc

    @app.get("/scope")
    def scope() -> dict[str, Any]:
        try:
            return scope_response(runtime_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j scope lookup failed: {exc}") from exc

    @app.get("/sources")
    def sources() -> dict[str, Any]:
        try:
            return sources_response(runtime_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j source lookup failed: {exc}") from exc

    @app.get("/entities/search")
    def search_entities_endpoint(
        q: str | None = None,
        entity_type: str | None = Query(default=None, alias="type"),
        source: str | None = None,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            return search_entities_response(runtime_settings, q, entity_type, source, limit)
        except Exception as exc:
            raise neo4j_http_exception("entity search", exc) from exc

    @app.get("/entities/{entity_id}")
    def get_entity_endpoint(entity_id: str) -> dict[str, Any]:
        try:
            return entity_response(runtime_settings, entity_id)
        except Exception as exc:
            raise neo4j_http_exception("entity lookup", exc) from exc

    @app.get("/entities/{entity_id}/neighbors")
    def get_neighbors_endpoint(
        entity_id: str,
        direction: str = "both",
        depth: int = Query(default=1, ge=1, le=1),
        edge_type: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return neighbors_response(runtime_settings, entity_id, direction, edge_type, depth, limit)
        except Exception as exc:
            raise neo4j_http_exception("neighbor lookup", exc) from exc

    @app.get("/edges/unresolved")
    def get_unresolved_edges_endpoint(
        source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return unresolved_edges_response(runtime_settings, source, edge_type, limit)
        except Exception as exc:
            raise neo4j_http_exception("unresolved edge lookup", exc) from exc

    @app.get("/reports/unresolved")
    def get_unresolved_report_endpoint(
        source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        limit: int = Query(default=50, ge=1, le=200),
        examples: int = Query(default=3, ge=1, le=10),
    ) -> dict[str, Any]:
        try:
            return unresolved_report_response(runtime_settings, source, edge_type, limit, examples)
        except Exception as exc:
            raise neo4j_http_exception("unresolved report lookup", exc) from exc

    return app


app = create_app()
