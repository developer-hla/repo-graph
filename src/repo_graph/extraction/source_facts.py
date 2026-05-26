"""Source-level facts for repository, project, and file scaffolding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_graph.extraction.facts import EntityFact
from repo_graph.sources import ResolvedSource


def repository_fact(source: ResolvedSource) -> EntityFact:
    aliases = {source.name}
    if source.url:
        aliases.add(Path(source.url.rstrip("/").removesuffix(".git")).name)
    return EntityFact(
        entity_type="repository",
        name=source.name,
        source_name=source.name,
        aliases=frozenset(aliases),
        properties={
            "path": str(source.path),
            "url": source.url,
            "ref": source.ref,
            "commit": source.commit,
        },
    )


def project_fact(
    source: ResolvedSource,
    name: str,
    file_path: str | None,
    aliases: set[str],
    properties: dict[str, Any],
) -> EntityFact:
    return EntityFact(
        entity_type="project",
        name=name,
        source_name=source.name,
        file_path=file_path,
        aliases=frozenset(aliases),
        properties=properties,
    )


def file_fact(
    source: ResolvedSource,
    rel_path: str,
    extension: str,
    project_name: str | None,
) -> EntityFact:
    return EntityFact(
        entity_type="file",
        name=rel_path,
        source_name=source.name,
        file_path=rel_path,
        properties={
            "extension": extension,
            "project": project_name,
        },
    )


__all__ = [
    "file_fact",
    "project_fact",
    "repository_fact",
]
