"""Configuration loading for RepoGraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_FILE_EXTENSIONS = {
    ".cs",
    ".csproj",
    ".fsproj",
    ".js",
    ".json",
    ".jsx",
    ".props",
    ".sln",
    ".sql",
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


@dataclass(frozen=True)
class IncludeRules:
    file_extensions: set[str] = field(default_factory=lambda: set(DEFAULT_FILE_EXTENSIONS))


@dataclass(frozen=True)
class ExcludeRules:
    directories: set[str] = field(default_factory=lambda: set(DEFAULT_EXCLUDED_DIRECTORIES))
    files: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class RepoGraphConfig:
    name: str
    config_path: Path
    cache_dir: Path
    output_dir: Path
    sources: tuple[Source, ...]
    include: IncludeRules = field(default_factory=IncludeRules)
    exclude: ExcludeRules = field(default_factory=ExcludeRules)


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

    raw_cache_dir = raw.get("cache_dir", ".repo-graph/cache/repos")
    if not isinstance(raw_cache_dir, str) or not raw_cache_dir.strip():
        raise ValueError("Config 'cache_dir' must be a path string.")
    cache_dir = resolve_config_path(config_dir, raw_cache_dir)

    raw_output_dir = raw.get("output_dir", ".repo-graph/output")
    if not isinstance(raw_output_dir, str) or not raw_output_dir.strip():
        raise ValueError("Config 'output_dir' must be a path string.")
    output_dir = resolve_config_path(config_dir, raw_output_dir)

    sources = parse_sources(raw.get("sources"), config_dir)
    include = parse_include(raw.get("include"))
    exclude = parse_exclude(raw.get("exclude"))

    return RepoGraphConfig(
        name=name,
        config_path=config_path,
        cache_dir=cache_dir,
        output_dir=output_dir,
        sources=tuple(sources),
        include=include,
        exclude=exclude,
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
        else:
            raise ValueError(f"Unsupported source type '{source_type}' for source '{name}'.")

    return sources


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


def normalize_extension(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("File extensions must be non-empty strings.")
    extension = value.strip().lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension
