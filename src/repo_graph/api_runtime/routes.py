"""FastAPI app construction and route registration."""

from __future__ import annotations

from fastapi import FastAPI

from repo_graph import __version__
from repo_graph.api_runtime._build_routes import register_build_routes
from repo_graph.api_runtime._query_routes import register_query_routes
from repo_graph.api_runtime._report_routes import register_report_routes
from repo_graph.api_runtime._source_routes import register_source_routes
from repo_graph.api_runtime._system_routes import register_system_routes
from repo_graph.api_runtime._ui_routes import register_ui_routes
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.jobs import JobRegistry


def create_app(settings: RuntimeSettings | None = None, job_registry: JobRegistry | None = None) -> FastAPI:
    runtime_settings = settings or RuntimeSettings.from_env()
    registry = job_registry or JobRegistry()
    app = FastAPI(title="Repo Graph", version=__version__)

    register_ui_routes(app)
    register_system_routes(app, runtime_settings)
    register_source_routes(app, runtime_settings, registry)
    register_build_routes(app, runtime_settings, registry)
    register_query_routes(app, runtime_settings)
    register_report_routes(app, runtime_settings)

    return app


__all__ = ["create_app"]
