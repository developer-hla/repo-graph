"""Configured source and source refresh route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from repo_graph.api_runtime import config_workflows
from repo_graph.api_runtime.requests import SnapshotStatusRequest, SyncRequest
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.jobs import JobRegistry


def register_source_routes(app: FastAPI, runtime_settings: RuntimeSettings, registry: JobRegistry) -> None:
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

    @app.post("/jobs/sync", status_code=202)
    def submit_sync(request: SyncRequest) -> dict[str, Any]:
        return config_workflows.submit_sync_job(registry, runtime_settings, request)

    @app.post("/jobs/snapshot-status", status_code=202)
    def submit_snapshot_status(request: SnapshotStatusRequest) -> dict[str, Any]:
        return config_workflows.submit_snapshot_status_job(registry, runtime_settings, request)
