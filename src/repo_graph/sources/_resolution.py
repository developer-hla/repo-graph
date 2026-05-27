"""Source resolution helpers."""

from __future__ import annotations

from repo_graph.config import RepoGraphConfig, Source
from repo_graph.sources._expansion import expand_sources
from repo_graph.sources._git import git_commit
from repo_graph.sources._models import ResolvedSource
from repo_graph.sources._paths import git_cache_path


def resolve_sources(config: RepoGraphConfig) -> list[ResolvedSource]:
    return resolve_expanded_sources(config, expand_sources(config.sources))


def resolve_expanded_sources(config: RepoGraphConfig, sources: list[Source]) -> list[ResolvedSource]:
    resolved: list[ResolvedSource] = []
    for source in sources:
        if source.source_type == "local_path":
            if source.path is None:
                raise ValueError(f"Local source '{source.name}' is missing a path.")
            resolved.append(
                ResolvedSource(
                    name=source.name,
                    source_type=source.source_type,
                    path=source.path,
                    url=None,
                    ref=source.ref,
                    commit=git_commit(source.path),
                )
            )
        elif source.source_type == "git":
            path = git_cache_path(config.cache_dir, source)
            resolved.append(
                ResolvedSource(
                    name=source.name,
                    source_type=source.source_type,
                    path=path,
                    url=source.url,
                    ref=source.ref,
                    commit=git_commit(path),
                )
            )
        elif source.source_type == "database":
            continue
        else:
            raise ValueError(f"Unsupported source type: {source.source_type}")
    return resolved
