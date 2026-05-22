"""Configuration loading for RepoGraph."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from repo_graph.database import supported_database_engines

DEFAULT_CACHE_DIR = ".repo-graph/cache/repos"
DEFAULT_OUTPUT_DIR = ".repo-graph/output"
GITHUB_ORG_VISIBILITIES = {"all", "public", "private", "forks", "sources", "member"}
DATABASE_ENGINES = supported_database_engines()
DATABASE_OBJECT_TYPES = {
    "dependency",
    "foreign_key",
    "function",
    "stored_procedure",
    "table",
    "trigger",
    "view",
}
DEFAULT_DATABASE_OBJECT_TYPES = tuple(sorted(DATABASE_OBJECT_TYPES))

DEFAULT_FILE_EXTENSIONS = {
    ".cs",
    ".csproj",
    ".asmx",
    ".config",
    ".fsproj",
    ".js",
    ".json",
    ".jsx",
    ".py",
    ".props",
    ".sln",
    ".sql",
    ".svc",
    ".targets",
    ".toml",
    ".ts",
    ".tsx",
    ".vb",
    ".vbproj",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".repo-graph",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "out",
}


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

    raw_cache_dir = raw.get("cache_dir", DEFAULT_CACHE_DIR)
    if not isinstance(raw_cache_dir, str) or not raw_cache_dir.strip():
        raise ValueError("Config 'cache_dir' must be a path string.")
    cache_dir = resolve_config_path(config_dir, raw_cache_dir)

    raw_output_dir = raw.get("output_dir", DEFAULT_OUTPUT_DIR)
    if not isinstance(raw_output_dir, str) or not raw_output_dir.strip():
        raise ValueError("Config 'output_dir' must be a path string.")
    output_dir = resolve_config_path(config_dir, raw_output_dir)

    sources = parse_sources(raw.get("sources"), config_dir)
    include = parse_include(raw.get("include"))
    exclude = parse_exclude(raw.get("exclude"))
    dependency_filter = parse_dependency_filter(raw.get("dependency_filter"))

    return RepoGraphConfig(
        name=name,
        config_path=config_path,
        cache_dir=cache_dir,
        output_dir=output_dir,
        sources=tuple(sources),
        include=include,
        exclude=exclude,
        dependency_filter=dependency_filter,
    )


def resolve_config_path(config_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def parse_sources(raw_sources: Any, config_dir: Path) -> list[Source]:
    if raw_sources is None:
        return []
    if not isinstance(raw_sources, list):
        raise ValueError("Config 'sources' must be a list.")

    sources: list[Source] = []
    seen_names: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
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

        if source_type == "local_path":
            raw_path = raw_source.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"Local source '{name}' must define 'path'.")
            sources.append(
                Source(
                    name=name,
                    source_type=source_type,
                    path=resolve_config_path(config_dir, raw_path),
                    ref=ref.strip(),
                )
            )
        elif source_type == "git":
            url = raw_source.get("url")
            if not isinstance(url, str) or not url.strip():
                raise ValueError(f"Git source '{name}' must define 'url'.")
            sources.append(Source(name=name, source_type=source_type, url=url.strip(), ref=ref.strip()))
        elif source_type == "github_org":
            sources.append(parse_github_org_source(raw_source, name, ref.strip()))
        elif source_type == "database":
            sources.append(parse_database_source(raw_source, name, ref.strip()))
        else:
            raise ValueError(f"Unsupported source type '{source_type}' for source '{name}'.")

    return sources


def parse_github_org_source(raw_source: dict[str, Any], name: str, ref: str) -> Source:
    org = raw_source.get("org")
    if not isinstance(org, str) or not org.strip():
        raise ValueError(f"GitHub org source '{name}' must define 'org'.")
    visibility = raw_source.get("visibility", "all")
    if not isinstance(visibility, str) or not visibility.strip():
        raise ValueError(f"GitHub org source '{name}' has invalid 'visibility'.")
    visibility = visibility.strip()
    if visibility not in GITHUB_ORG_VISIBILITIES:
        raise ValueError(f"GitHub org source '{name}' has unsupported 'visibility'.")

    include = object_mapping(raw_source.get("include"), f"GitHub org source '{name}' include")
    exclude = object_mapping(raw_source.get("exclude"), f"GitHub org source '{name}' exclude")
    limit = optional_positive_int(raw_source.get("limit"), f"GitHub org source '{name}' limit")
    return Source(
        name=name,
        source_type="github_org",
        ref=ref,
        org=org.strip(),
        visibility=visibility,
        include_archived=bool_value(include.get("archived"), default=False),
        include_forks=bool_value(include.get("forks"), default=False),
        include_name_patterns=string_tuple(include.get("name_patterns")),
        exclude_name_patterns=string_tuple(exclude.get("name_patterns")),
        limit=limit,
    )


def parse_database_source(raw_source: dict[str, Any], name: str, ref: str) -> Source:
    if "connection_string" in raw_source:
        raise ValueError(f"Database source '{name}' must use 'connection_env', not 'connection_string'.")
    engine = required_string(raw_source.get("engine"), f"Database source '{name}' engine")
    if engine not in DATABASE_ENGINES:
        raise ValueError(f"Database source '{name}' has unsupported engine '{engine}'.")
    connection_env = required_string(raw_source.get("connection_env"), f"Database source '{name}' connection_env")
    schemas = string_tuple(raw_source.get("schemas"), field_name=f"Database source '{name}' schemas")
    include_object_types = string_tuple(
        raw_source.get("include_object_types", DEFAULT_DATABASE_OBJECT_TYPES),
        field_name=f"Database source '{name}' include_object_types",
    )
    unsupported_object_types = sorted(set(include_object_types) - DATABASE_OBJECT_TYPES)
    if unsupported_object_types:
        raise ValueError(
            f"Database source '{name}' has unsupported include_object_types: {', '.join(unsupported_object_types)}"
        )
    return Source(
        name=name,
        source_type="database",
        ref=ref,
        engine=engine,
        connection_env=connection_env,
        schemas=schemas,
        include_object_types=include_object_types,
        query_timeout_seconds=optional_positive_int(
            raw_source.get("query_timeout_seconds"),
            f"Database source '{name}' query_timeout_seconds",
        ),
        max_metadata_rows=optional_positive_int(
            raw_source.get("max_metadata_rows"),
            f"Database source '{name}' max_metadata_rows",
        ),
    )


def parse_include(raw_include: Any) -> IncludeRules:
    if raw_include is None:
        return IncludeRules()
    if not isinstance(raw_include, dict):
        raise ValueError("Config 'include' must be a mapping.")

    raw_extensions = raw_include.get("file_extensions", DEFAULT_FILE_EXTENSIONS)
    if not isinstance(raw_extensions, list | set | tuple):
        raise ValueError("Config 'include.file_extensions' must be a list.")
    extensions = {normalize_extension(value) for value in raw_extensions}
    return IncludeRules(file_extensions=extensions)


def parse_exclude(raw_exclude: Any) -> ExcludeRules:
    if raw_exclude is None:
        return ExcludeRules()
    if not isinstance(raw_exclude, dict):
        raise ValueError("Config 'exclude' must be a mapping.")

    directories = set(DEFAULT_EXCLUDED_DIRECTORIES)
    raw_directories = raw_exclude.get("directories")
    if raw_directories is not None:
        if not isinstance(raw_directories, list | set | tuple):
            raise ValueError("Config 'exclude.directories' must be a list.")
        directories.update(str(value) for value in raw_directories)

    files: set[str] = set()
    raw_files = raw_exclude.get("files")
    if raw_files is not None:
        if not isinstance(raw_files, list | set | tuple):
            raise ValueError("Config 'exclude.files' must be a list.")
        files.update(str(value) for value in raw_files)

    return ExcludeRules(directories=directories, files=files)


def parse_dependency_filter(raw_filter: Any) -> DependencyFilter:
    if raw_filter is None:
        return DependencyFilter()
    if not isinstance(raw_filter, dict):
        raise ValueError("Config 'dependency_filter' must be a mapping.")

    include_patterns = string_tuple(
        raw_filter.get("package_include_patterns"),
        field_name="dependency_filter.package_include_patterns",
    )
    exclude_patterns = string_tuple(
        raw_filter.get("package_exclude_patterns"),
        field_name="dependency_filter.package_exclude_patterns",
    )
    validate_regex_patterns(include_patterns, "dependency_filter.package_include_patterns")
    validate_regex_patterns(exclude_patterns, "dependency_filter.package_exclude_patterns")

    return DependencyFilter(
        package_include_patterns=include_patterns,
        package_exclude_patterns=exclude_patterns,
        include_relative_imports=bool_value(raw_filter.get("include_relative_imports"), default=True),
    )


def validate_regex_patterns(patterns: tuple[str, ...], field_name: str) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{field_name} contains invalid regex '{pattern}': {exc}") from exc


def normalize_extension(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("File extensions must be non-empty strings.")
    extension = value.strip().lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


def object_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError(f"{field_name} must be a mapping.")


def string_tuple(value: Any, field_name: str = "Name patterns") -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple | set):
        raise ValueError(f"{field_name} must be a list.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings.")
        items.append(item.strip())
    return tuple(items)


def required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("Boolean config values must be true or false.")


def optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value
