"""Graph query route registration."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query

from repo_graph.api_runtime import errors, query_responses, source_files
from repo_graph.api_runtime.constants import SOURCE_SNIPPET_MAX_CONTEXT
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.storage import read_graph_stats


def register_query_routes(app: FastAPI, runtime_settings: RuntimeSettings) -> None:
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
