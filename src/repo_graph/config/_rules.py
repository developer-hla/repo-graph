"""Include, exclude, and dependency-filter config parsing."""

from __future__ import annotations

from typing import Any

from repo_graph.config._defaults import DEFAULT_EXCLUDED_DIRECTORIES, DEFAULT_FILE_EXTENSIONS
from repo_graph.config._models import DependencyFilter, ExcludeRules, IncludeRules
from repo_graph.config._values import bool_value, normalize_extension, string_tuple, validate_regex_patterns


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
