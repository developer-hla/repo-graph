"""HTTP API runtime for Repo Graph."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from repo_graph import __version__
from repo_graph.config import RepoGraphConfig, load_config
from repo_graph.scanner import MAX_FILE_BYTES, build_graph
from repo_graph.storage.neo4j import (
    Neo4jSettings,
    get_entity,
    get_entity_neighbors,
    list_unresolved_edges,
    load_graph_path,
    read_graph_stats,
    search_entities,
)

DEFAULT_CONFIG_PATH = Path("config/local-example.yaml")
DEFAULT_NEO4J_URI = "bolt://neo4j:7687"
DEFAULT_NEO4J_PASSWORD = "repo-graph-password"


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
            {"method": "GET", "path": "/manifest", "available": True},
            {"method": "POST", "path": "/build", "available": True},
            {"method": "POST", "path": "/build-load", "available": True},
            {"method": "POST", "path": "/load", "available": True},
            {"method": "POST", "path": "/query", "available": False},
            {"method": "GET", "path": "/stats", "available": True},
            {"method": "GET", "path": "/entities/search", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}/neighbors", "available": True},
            {"method": "GET", "path": "/edges/unresolved", "available": True},
        ],
        "agent_guidance": {
            "purpose": "Discover the local Repo Graph runtime and supported API surface.",
            "query_api_status": "safe read endpoints available",
            "raw_cypher_status": "planned",
            "build_api_status": "available",
            "graph_loader_status": "available",
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


def neo4j_http_exception(operation: str, exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=f"Entity not found: {exc.args[0]}")
    return HTTPException(status_code=503, detail=f"Neo4j {operation} failed: {exc}")


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or RuntimeSettings.from_env()
    app = FastAPI(title="Repo Graph", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return manifest_payload(runtime_settings)

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

    return app


app = create_app()
