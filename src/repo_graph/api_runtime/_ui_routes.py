"""UI shell and static asset route registration."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from repo_graph.api_runtime import manifest as manifest_helpers
from repo_graph.api_runtime.constants import UI_DIR


def register_ui_routes(app: FastAPI) -> None:
    app.mount("/ui/assets", StaticFiles(directory=UI_DIR), name="repo-graph-ui-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def ui() -> FileResponse:
        return FileResponse(manifest_helpers.ui_index_path())
