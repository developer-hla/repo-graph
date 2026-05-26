"""API runtime settings and path resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from repo_graph.api_runtime.constants import DEFAULT_CONFIG_PATH, DEFAULT_NEO4J_PASSWORD, DEFAULT_NEO4J_URI
from repo_graph.config import RepoGraphConfig, load_config
from repo_graph.storage import Neo4jSettings
from repo_graph.validation import positive_int


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
    return positive_int(value, "max_file_bytes")


def load_runtime_config(settings: RuntimeSettings, config_path: str | None = None) -> RepoGraphConfig:
    return load_config(resolve_config_path(settings, config_path))


__all__ = [
    "RuntimeSettings",
    "default_graph_path",
    "env_path",
    "env_value",
    "load_runtime_config",
    "resolve_config_path",
    "resolve_graph_path",
    "validate_max_file_bytes",
]
