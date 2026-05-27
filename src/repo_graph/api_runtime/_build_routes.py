"""Build, load, refresh, and job route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from repo_graph.api_runtime import config_workflows
from repo_graph.api_runtime.requests import (
    BuildLoadRequest,
    BuildRequest,
    LoadRequest,
    RefreshChangedRequest,
    RefreshRequest,
)
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.jobs import JobRegistry


def register_build_routes(app: FastAPI, runtime_settings: RuntimeSettings, registry: JobRegistry) -> None:
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

    @app.post("/jobs/build", status_code=202)
    def submit_build(request: BuildRequest) -> dict[str, Any]:
        return config_workflows.submit_build_job(registry, runtime_settings, request)

    @app.post("/jobs/build-load", status_code=202)
    def submit_build_load(request: BuildLoadRequest) -> dict[str, Any]:
        return config_workflows.submit_build_load_job(registry, runtime_settings, request)

    @app.post("/jobs/refresh", status_code=202)
    def submit_refresh(request: RefreshRequest) -> dict[str, Any]:
        return config_workflows.submit_refresh_job(registry, runtime_settings, request)

    @app.post("/jobs/refresh-changed", status_code=202)
    def submit_refresh_changed(request: RefreshChangedRequest) -> dict[str, Any]:
        return config_workflows.submit_refresh_changed_job(registry, runtime_settings, request)

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
