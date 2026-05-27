"""Configuration model types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from repo_graph.config._defaults import DEFAULT_EXCLUDED_DIRECTORIES, DEFAULT_FILE_EXTENSIONS


@dataclass(frozen=True)
class Source:
    """One repository source from a profile."""

    name: str
    source_type: str
    path: Path | None = None
    url: str | None = None
    ref: str = "default"
    org: str | None = None
    visibility: str = "all"
    include_archived: bool = False
    include_forks: bool = False
    include_name_patterns: tuple[str, ...] = ()
    exclude_name_patterns: tuple[str, ...] = ()
    limit: int | None = None
    engine: str | None = None
    connection_env: str | None = None
    schemas: tuple[str, ...] = ()
    include_object_types: tuple[str, ...] = ()
    query_timeout_seconds: int | None = None
    max_metadata_rows: int | None = None


@dataclass(frozen=True)
class IncludeRules:
    file_extensions: set[str] = field(default_factory=lambda: set(DEFAULT_FILE_EXTENSIONS))


@dataclass(frozen=True)
class ExcludeRules:
    directories: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRECTORIES))
    files: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class DependencyFilter:
    package_include_patterns: tuple[str, ...] = ()
    package_exclude_patterns: tuple[str, ...] = ()
    include_relative_imports: bool = True


@dataclass(frozen=True)
class RepoGraphConfig:
    name: str
    config_path: Path
    cache_dir: Path
    output_dir: Path
    sources: tuple[Source, ...]
    include: IncludeRules = field(default_factory=IncludeRules)
    exclude: ExcludeRules = field(default_factory=ExcludeRules)
    dependency_filter: DependencyFilter = field(default_factory=DependencyFilter)
