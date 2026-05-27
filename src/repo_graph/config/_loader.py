"""Configuration loading for RepoGraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from repo_graph.config._defaults import DEFAULT_CACHE_DIR, DEFAULT_OUTPUT_DIR
from repo_graph.config._models import RepoGraphConfig
from repo_graph.config._rules import parse_dependency_filter, parse_exclude, parse_include
from repo_graph.config._sources import parse_sources
from repo_graph.config._values import resolve_config_path


def load_raw_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping.")
    return data


def load_config(path: Path) -> RepoGraphConfig:
    config_path = path.resolve()
    config_dir = config_path.parent
    raw = load_raw_config(config_path)

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Config must define a non-empty 'name'.")

    cache_dir = parse_config_path(raw, "cache_dir", DEFAULT_CACHE_DIR, config_dir)
    output_dir = parse_config_path(raw, "output_dir", DEFAULT_OUTPUT_DIR, config_dir)

    return RepoGraphConfig(
        name=name,
        config_path=config_path,
        cache_dir=cache_dir,
        output_dir=output_dir,
        sources=tuple(parse_sources(raw.get("sources"), config_dir)),
        include=parse_include(raw.get("include")),
        exclude=parse_exclude(raw.get("exclude")),
        dependency_filter=parse_dependency_filter(raw.get("dependency_filter")),
    )


def parse_config_path(raw: dict[str, Any], field_name: str, default: str, config_dir: Path) -> Path:
    value = raw.get(field_name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{field_name}' must be a path string.")
    return resolve_config_path(config_dir, value)
