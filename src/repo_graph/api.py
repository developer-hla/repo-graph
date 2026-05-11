"""HTTP API runtime for Repo Graph."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from repo_graph import __version__

DEFAULT_CONFIG_PATH = Path("config/local-example.yaml")
DEFAULT_NEO4J_URI = "bolt://neo4j:7687"


@dataclass(frozen=True)
class RuntimeSettings:
    config_path: Path | None = DEFAULT_CONFIG_PATH
    neo4j_uri: str | None = DEFAULT_NEO4J_URI
    neo4j_user: str | None = "neo4j"

    @classmethod
    def from_env(cls, config_path: Path | None = None) -> RuntimeSettings:
        return cls(
            config_path=config_path or env_path("REPO_GRAPH_CONFIG", DEFAULT_CONFIG_PATH),
            neo4j_uri=env_value("REPO_GRAPH_NEO4J_URI", DEFAULT_NEO4J_URI),
            neo4j_user=env_value("REPO_GRAPH_NEO4J_USER", "neo4j"),
        )


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
            "configured": settings.neo4j_uri is not None,
        },
        "endpoints": [
            {"method": "GET", "path": "/health", "available": True},
            {"method": "GET", "path": "/manifest", "available": True},
            {"method": "POST", "path": "/build", "available": False},
            {"method": "POST", "path": "/load", "available": False},
            {"method": "POST", "path": "/query", "available": False},
            {"method": "GET", "path": "/stats", "available": False},
        ],
        "agent_guidance": {
            "purpose": "Discover the local Repo Graph runtime and supported API surface.",
            "query_api_status": "planned",
            "graph_loader_status": "planned",
        },
    }


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    runtime_settings = settings or RuntimeSettings.from_env()
    app = FastAPI(title="Repo Graph", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return health_payload()

    @app.get("/manifest")
    def manifest() -> dict[str, Any]:
        return manifest_payload(runtime_settings)

    return app


app = create_app()
