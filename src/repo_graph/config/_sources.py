"""Source list config parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_graph.config._database import parse_database_source
from repo_graph.config._github import parse_github_org_source
from repo_graph.config._models import Source
from repo_graph.config._values import resolve_config_path


def parse_sources(raw_sources: Any, config_dir: Path) -> list[Source]:
    if raw_sources is None:
        return []
    if not isinstance(raw_sources, list):
        raise ValueError("Config 'sources' must be a list.")

    sources: list[Source] = []
    seen_names: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        sources.append(parse_source(raw_source, config_dir, index, seen_names))
    return sources


def parse_source(raw_source: Any, config_dir: Path, index: int, seen_names: set[str]) -> Source:
    if not isinstance(raw_source, dict):
        raise ValueError(f"Source at index {index} must be a mapping.")

    source_type = raw_source.get("type")
    if not isinstance(source_type, str) or not source_type.strip():
        raise ValueError(f"Source at index {index} must define 'type'.")
    source_type = source_type.strip()

    name = raw_source.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Source at index {index} must define non-empty 'name'.")
    name = name.strip()
    if name in seen_names:
        raise ValueError(f"Duplicate source name: {name}")
    seen_names.add(name)

    ref = raw_source.get("ref", "default")
    if ref is None:
        ref = "default"
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"Source '{name}' has invalid 'ref'.")

    return parse_typed_source(raw_source, config_dir, source_type, name, ref.strip())


def parse_typed_source(raw_source: dict[str, Any], config_dir: Path, source_type: str, name: str, ref: str) -> Source:
    if source_type == "local_path":
        raw_path = raw_source.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"Local source '{name}' must define 'path'.")
        return Source(
            name=name,
            source_type=source_type,
            path=resolve_config_path(config_dir, raw_path),
            ref=ref,
        )
    if source_type == "git":
        url = raw_source.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError(f"Git source '{name}' must define 'url'.")
        return Source(name=name, source_type=source_type, url=url.strip(), ref=ref)
    if source_type == "github_org":
        return parse_github_org_source(raw_source, name, ref)
    if source_type == "database":
        return parse_database_source(raw_source, name, ref)
    raise ValueError(f"Unsupported source type '{source_type}' for source '{name}'.")
