"""Manifest discovery helpers."""

from __future__ import annotations

from pathlib import Path

from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.scanners.dotnet_helpers import DOTNET_BUILD_SUFFIXES, DOTNET_PROJECT_SUFFIXES

MANIFEST_FILENAMES = {
    "App.config",
    "Directory.Build.props",
    "Web.config",
    "package.json",
    "packages.config",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "requirements.txt",
}


def is_project_manifest(path: Path) -> bool:
    return (
        path.name in MANIFEST_FILENAMES
        or is_requirements_file(path)
        or path.suffix.lower() in DOTNET_PROJECT_SUFFIXES
        or path.suffix.lower() in DOTNET_BUILD_SUFFIXES
        or path.suffix.lower() == ".sln"
    )


def is_requirements_file(path: Path) -> bool:
    return path.name == "requirements.txt" or (path.name.startswith("requirements-") and path.suffix == ".txt")


def is_scannable_file(config: RepoGraphConfig, path: Path) -> bool:
    return path.suffix.lower() in config.include.file_extensions or is_project_manifest(path)
