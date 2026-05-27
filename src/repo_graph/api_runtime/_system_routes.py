"""System and configuration route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from repo_graph.api_runtime import config_workflows
from repo_graph.api_runtime import manifest as manifest_helpers
from repo_graph.api_runtime.settings import RuntimeSettings


def register_system_routes(app: FastAPI, runtime_settings: RuntimeSettings) -> None:
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
