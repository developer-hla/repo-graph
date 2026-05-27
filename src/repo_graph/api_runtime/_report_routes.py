"""Report route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query

from repo_graph.api_runtime import errors, report_responses
from repo_graph.api_runtime.settings import RuntimeSettings


def register_report_routes(app: FastAPI, runtime_settings: RuntimeSettings) -> None:
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
