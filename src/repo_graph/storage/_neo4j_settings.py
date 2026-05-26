"""Neo4j runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_NEO4J_URI = "bolt://neo4j:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = "repo-graph-password"


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str = DEFAULT_NEO4J_URI
    user: str = DEFAULT_NEO4J_USER
    password: str = DEFAULT_NEO4J_PASSWORD
    database: str | None = None

    @classmethod
    def from_env(cls) -> Neo4jSettings:
        return cls(
            uri=env_value("REPO_GRAPH_NEO4J_URI", DEFAULT_NEO4J_URI),
            user=env_value("REPO_GRAPH_NEO4J_USER", DEFAULT_NEO4J_USER),
            password=env_value("REPO_GRAPH_NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
            database=env_optional_value("REPO_GRAPH_NEO4J_DATABASE"),
        )


def env_value(name: str, default: str | None) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return "" if default is None else default
    return value.strip()


def env_optional_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


__all__ = [
    "Neo4jSettings",
    "env_optional_value",
    "env_value",
]
