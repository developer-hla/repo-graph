"""Source synchronization workflows."""

from __future__ import annotations

from repo_graph.config import RepoGraphConfig, Source
from repo_graph.sources._expansion import expand_sources
from repo_graph.sources._git import sync_git_source
from repo_graph.sources._models import ResolvedSource
from repo_graph.sources._resolution import resolve_expanded_sources


def sync_sources(config: RepoGraphConfig) -> list[ResolvedSource]:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    expanded_sources = expand_sources(config.sources)
    for source in expanded_sources:
        sync_one_source(config, source)
    return resolve_expanded_sources(config, expanded_sources)


def sync_one_source(config: RepoGraphConfig, source: Source) -> None:
    if source.source_type == "git":
        sync_git_source(config.cache_dir, source)
        return
    if source.source_type == "local_path":
        if source.path is None or not source.path.exists():
            raise FileNotFoundError(f"Local source path does not exist: {source.path}")
        return
    if source.source_type == "database":
        return
    raise ValueError(f"Unsupported source type: {source.source_type}")
