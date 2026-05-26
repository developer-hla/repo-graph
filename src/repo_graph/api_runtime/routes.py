"""FastAPI route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from repo_graph import __version__
from repo_graph.api_runtime import config_workflows, errors, query_responses, report_responses, source_files
from repo_graph.api_runtime import manifest as manifest_helpers
from repo_graph.api_runtime.constants import SOURCE_SNIPPET_MAX_CONTEXT, UI_DIR
from repo_graph.api_runtime.requests import (
    BuildLoadRequest,
    BuildRequest,
    LoadRequest,
    RefreshChangedRequest,
    RefreshRequest,
    SnapshotStatusRequest,
    SyncRequest,
)
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.jobs import JobRegistry
from repo_graph.storage import read_graph_stats


def create_app(settings: RuntimeSettings | None = None, job_registry: JobRegistry | None = None) -> FastAPI:
    runtime_settings = settings or RuntimeSettings.from_env()
    registry = job_registry or JobRegistry()
    app = FastAPI(title="Repo Graph", version=__version__)
    app.mount("/ui/assets", StaticFiles(directory=UI_DIR), name="repo-graph-ui-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def ui() -> FileResponse:
        return FileResponse(manifest_helpers.ui_index_path())

    @app.get("/health")
    def health() -> dict[str, str]:
        return manifest_helpers.health_payload()

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return manifest_helpers.manifest_payload(runtime_settings)

    @app.get("/config")
    def config(config_path: str | None = None) -> dict[str, Any]:
        try:
            return config_workflows.config_response(runtime_settings, config_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/sources/configured")
    def configured_sources(config_path: str | None = None) -> dict[str, Any]:
        try:
            return config_workflows.configured_sources_response(runtime_settings, config_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/sync")
    def sync(request: SyncRequest) -> dict[str, Any]:
        try:
            return config_workflows.sync_response(runtime_settings, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/build")
    def build(request: BuildRequest) -> dict[str, Any]:
        try:
            return config_workflows.build_response(runtime_settings, request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph build failed: {exc}") from exc

    @app.post("/build-load")
    def build_load(request: BuildLoadRequest) -> dict[str, Any]:
        try:
            return config_workflows.build_load_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph build-load failed: {exc}") from exc

    @app.post("/refresh")
    def refresh(request: RefreshRequest) -> dict[str, Any]:
        try:
            return config_workflows.refresh_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Graph refresh failed: {exc}") from exc

    @app.post("/snapshot/status")
    def snapshot_status_endpoint(request: SnapshotStatusRequest) -> dict[str, Any]:
        try:
            return config_workflows.snapshot_status_response(runtime_settings, request)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Snapshot status failed: {exc}") from exc

    @app.post("/jobs/build", status_code=202)
    def submit_build(request: BuildRequest) -> dict[str, Any]:
        return config_workflows.submit_build_job(registry, runtime_settings, request)

    @app.post("/jobs/build-load", status_code=202)
    def submit_build_load(request: BuildLoadRequest) -> dict[str, Any]:
        return config_workflows.submit_build_load_job(registry, runtime_settings, request)

    @app.post("/jobs/sync", status_code=202)
    def submit_sync(request: SyncRequest) -> dict[str, Any]:
        return config_workflows.submit_sync_job(registry, runtime_settings, request)

    @app.post("/jobs/refresh", status_code=202)
    def submit_refresh(request: RefreshRequest) -> dict[str, Any]:
        return config_workflows.submit_refresh_job(registry, runtime_settings, request)

    @app.post("/jobs/refresh-changed", status_code=202)
    def submit_refresh_changed(request: RefreshChangedRequest) -> dict[str, Any]:
        return config_workflows.submit_refresh_changed_job(registry, runtime_settings, request)

    @app.post("/jobs/snapshot-status", status_code=202)
    def submit_snapshot_status(request: SnapshotStatusRequest) -> dict[str, Any]:
        return config_workflows.submit_snapshot_status_job(registry, runtime_settings, request)

    @app.get("/jobs")
    def list_jobs(
        status: str | None = None,
        kind: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return config_workflows.jobs_response(registry, status, kind, limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return config_workflows.job_response(registry, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Job not found: {exc.args[0]}") from exc

    @app.post("/load")
    def load(request: LoadRequest) -> dict[str, Any]:
        try:
            return config_workflows.load_response(runtime_settings, request)
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
            return query_responses.scope_response(runtime_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j scope lookup failed: {exc}") from exc

    @app.get("/sources")
    def sources() -> dict[str, Any]:
        try:
            return query_responses.sources_response(runtime_settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j source lookup failed: {exc}") from exc

    @app.get("/sources/{source_name}/overview")
    def source_overview(source_name: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        try:
            return query_responses.source_overview_response(runtime_settings, source_name, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Source not found: {exc.args[0]}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j source overview lookup failed: {exc}") from exc

    @app.get("/sources/{source_name}/files/snippet")
    def source_file_snippet(
        source_name: str,
        path: str = Query(..., min_length=1),
        line: int = Query(default=1, ge=1),
        context: int = Query(default=3, ge=0, le=SOURCE_SNIPPET_MAX_CONTEXT),
    ) -> dict[str, Any]:
        try:
            return source_files.source_file_snippet_response(runtime_settings, source_name, path, line, context)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Source not found: {exc.args[0]}") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Source snippet lookup failed: {exc}") from exc

    @app.get("/explore")
    def explore(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        try:
            return query_responses.explore_response(runtime_settings, limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Neo4j explore lookup failed: {exc}") from exc

    @app.get("/entities/search")
    def search_entities_endpoint(
        q: str | None = None,
        entity_type: str | None = Query(default=None, alias="type"),
        source: str | None = None,
        limit: int = Query(default=25, ge=1, le=100),
    ) -> dict[str, Any]:
        try:
            return query_responses.search_entities_response(runtime_settings, q, entity_type, source, limit)
        except Exception as exc:
            raise errors.neo4j_http_exception("entity search", exc) from exc

    @app.get("/relationships/search")
    def search_relationships_endpoint(
        from_source: str | None = None,
        to_source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        from_type: str | None = None,
        to_type: str | None = None,
        resolved: bool | None = None,
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return query_responses.relationship_search_response(
                runtime_settings,
                from_source,
                to_source,
                edge_type,
                from_type,
                to_type,
                resolved,
                limit,
            )
        except Exception as exc:
            raise errors.neo4j_http_exception("relationship search", exc) from exc

    @app.get("/entities/{entity_id}")
    def get_entity_endpoint(entity_id: str) -> dict[str, Any]:
        try:
            return query_responses.entity_response(runtime_settings, entity_id)
        except Exception as exc:
            raise errors.neo4j_http_exception("entity lookup", exc) from exc

    @app.get("/entities/{entity_id}/overview")
    def get_entity_overview_endpoint(
        entity_id: str,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return query_responses.entity_overview_response(runtime_settings, entity_id, limit)
        except Exception as exc:
            raise errors.neo4j_http_exception("entity overview lookup", exc) from exc

    @app.get("/entities/{entity_id}/neighbors")
    def get_neighbors_endpoint(
        entity_id: str,
        direction: str = "both",
        depth: int = Query(default=1, ge=1, le=3),
        edge_type: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return query_responses.neighbors_response(runtime_settings, entity_id, direction, edge_type, depth, limit)
        except Exception as exc:
            raise errors.neo4j_http_exception("neighbor lookup", exc) from exc

    @app.get("/entities/{entity_id}/impact")
    def get_impact_endpoint(
        entity_id: str,
        direction: str = "in",
        depth: int = Query(default=2, ge=1, le=3),
        edge_type: str | None = Query(default=None, alias="type"),
        profile: str = "impact",
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return query_responses.impact_response(
                runtime_settings,
                entity_id,
                direction,
                edge_type,
                depth,
                limit,
                profile,
            )
        except Exception as exc:
            raise errors.neo4j_http_exception("impact lookup", exc) from exc

    @app.get("/edges/unresolved")
    def get_unresolved_edges_endpoint(
        source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            return query_responses.unresolved_edges_response(runtime_settings, source, edge_type, limit)
        except Exception as exc:
            raise errors.neo4j_http_exception("unresolved edge lookup", exc) from exc

    @app.get("/reports/unresolved")
    def get_unresolved_report_endpoint(
        source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        limit: int = Query(default=50, ge=1, le=200),
        examples: int = Query(default=3, ge=1, le=10),
    ) -> dict[str, Any]:
        try:
            return report_responses.unresolved_report_response(runtime_settings, source, edge_type, limit, examples)
        except Exception as exc:
            raise errors.neo4j_http_exception("unresolved report lookup", exc) from exc

    @app.get("/reports/interactions")
    def get_interactions_report_endpoint(
        source: str | None = None,
        target_source: str | None = None,
        edge_type: str | None = Query(default=None, alias="type"),
        limit: int = Query(default=50, ge=1, le=200),
        examples: int = Query(default=3, ge=1, le=10),
    ) -> dict[str, Any]:
        try:
            return report_responses.interactions_report_response(
                runtime_settings,
                source,
                target_source,
                edge_type,
                limit,
                examples,
            )
        except Exception as exc:
            raise errors.neo4j_http_exception("interactions report lookup", exc) from exc

    @app.get("/reports/database-reconciliation")
    def get_database_reconciliation_report_endpoint(
        source: str | None = None,
        database_source: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        examples: int = Query(default=3, ge=1, le=10),
    ) -> dict[str, Any]:
        try:
            return report_responses.database_reconciliation_report_response(
                runtime_settings,
                source,
                database_source,
                limit,
                examples,
            )
        except Exception as exc:
            raise errors.neo4j_http_exception("database reconciliation report lookup", exc) from exc

    return app


__all__ = ["create_app"]
