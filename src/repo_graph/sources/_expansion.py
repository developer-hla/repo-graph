"""Configured source expansion helpers."""

from __future__ import annotations

from repo_graph.config import Source
from repo_graph.sources._github import github_org_sources


def expand_sources(sources: tuple[Source, ...] | list[Source]) -> list[Source]:
    expanded: list[Source] = []
    seen_names: set[str] = set()
    for source in sources:
        for expanded_source in expand_one_source(source):
            if expanded_source.name in seen_names:
                raise ValueError(f"Duplicate expanded source name: {expanded_source.name}")
            seen_names.add(expanded_source.name)
            expanded.append(expanded_source)
    return expanded


def expand_one_source(source: Source) -> list[Source]:
    if source.source_type == "github_org":
        return github_org_sources(source)
    return [source]
