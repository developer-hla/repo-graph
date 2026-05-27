"""Project boundary discovery from source manifests."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.contracts import ProjectInfo
from repo_graph.extraction.facts import EntityFact, EntityReference
from repo_graph.extraction.scanners.common import (
    project_name_from_path,
    read_json_object,
    read_toml_object,
    safe_relative_path,
    string_value,
)
from repo_graph.extraction.scanners.manifest_helpers import is_project_manifest, is_requirements_file
from repo_graph.extraction.scanners.manifests import DOTNET_PROJECT_SUFFIXES, dotnet_project_metadata
from repo_graph.extraction.scanners.package_helpers import (
    normalize_python_package_name,
    pyproject_metadata,
    python_import_name,
)
from repo_graph.extraction.source_facts import project_fact
from repo_graph.sources import ResolvedSource


def requirements_project_info(source: ResolvedSource, repo_entity: EntityFact, manifest_path: Path) -> ProjectInfo:
    name = project_name_from_path(source, manifest_path.parent)
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "python_requirements",
        "python",
        manifest_path=manifest_path,
    )


def javascript_project_info(source: ResolvedSource, repo_entity: EntityFact, manifest_path: Path) -> ProjectInfo | None:
    package = read_json_object(manifest_path) or {}
    package_name = string_value(package.get("name"))
    name = package_name or project_name_from_path(source, manifest_path.parent)
    project_type = "javascript_root" if manifest_path.parent == source.path else "javascript_package"
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        project_type,
        "javascript",
        package_name=package_name,
        version=string_value(package.get("version")),
        manifest_path=manifest_path,
        aliases={package_name} if package_name else set(),
    )


def iter_project_manifest_paths(config: RepoGraphConfig, root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in config.exclude.directories and not dirname.startswith(".")
        ]
        for filename in filenames:
            file_path = current / filename
            if is_project_manifest(file_path):
                yield file_path


def dotnet_project_info(source: ResolvedSource, repo_entity: EntityFact, manifest_path: Path) -> ProjectInfo:
    try:
        content = manifest_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    metadata = dotnet_project_metadata(content)
    name = metadata["package_id"] or metadata["assembly_name"] or manifest_path.stem
    aliases = {manifest_path.stem}
    for value in (metadata["package_id"], metadata["assembly_name"], metadata["root_namespace"]):
        if value:
            aliases.add(value)
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "dotnet_project",
        "dotnet",
        package_name=metadata["package_id"] or metadata["assembly_name"],
        version=metadata["version"],
        manifest_path=manifest_path,
        aliases=aliases,
    )


def project_info(
    source: ResolvedSource,
    repo_entity: EntityFact,
    name: str,
    path: Path,
    project_type: str,
    ecosystem: str,
    package_name: str | None = None,
    version: str | None = None,
    manifest_path: Path | None = None,
    aliases: set[str] | None = None,
) -> ProjectInfo:
    rel_path = safe_relative_path(source.path, path)
    manifest_rel_path = safe_relative_path(source.path, manifest_path) if manifest_path else None
    project_aliases = {name, path.name, *(aliases or set())}
    if package_name:
        project_aliases.add(package_name)
    entity = project_fact(
        source,
        name,
        manifest_rel_path,
        project_aliases,
        properties={
            "path": rel_path,
            "manifest_path": manifest_rel_path,
            "package_name": package_name,
            "version": version,
            "ecosystem": ecosystem,
            "project_type": project_type,
            "repository": repo_entity.name,
        },
    )
    return ProjectInfo(name=name, path=path, entity=entity, ecosystem=ecosystem)


def python_project_info(source: ResolvedSource, repo_entity: EntityFact, manifest_path: Path) -> ProjectInfo | None:
    pyproject = read_toml_object(manifest_path) or {}
    metadata = pyproject_metadata(pyproject)
    name = metadata["name"] or project_name_from_path(source, manifest_path.parent)
    package_name = metadata["name"] or None
    project_aliases = (
        {normalize_python_package_name(package_name), python_import_name(package_name)} if package_name else set()
    )
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "python_project",
        "python",
        package_name=package_name,
        version=metadata["version"],
        manifest_path=manifest_path,
        aliases=project_aliases,
    )


def dedupe_projects(projects: list[ProjectInfo]) -> list[ProjectInfo]:
    deduped: dict[EntityReference, ProjectInfo] = {}
    for project in projects:
        deduped[project.entity.reference] = project
    return list(deduped.values())


def dotnet_solution_project_info(source: ResolvedSource, repo_entity: EntityFact, manifest_path: Path) -> ProjectInfo:
    return project_info(
        source,
        repo_entity,
        manifest_path.stem,
        manifest_path.parent,
        "dotnet_solution",
        "dotnet",
        manifest_path=manifest_path,
        aliases={manifest_path.stem},
    )


def discover_projects(config: RepoGraphConfig, source: ResolvedSource, repo_entity: EntityFact) -> list[ProjectInfo]:
    projects: list[ProjectInfo] = []

    for manifest_path in iter_project_manifest_paths(config, source.path):
        project = project_info_for_manifest(source, repo_entity, manifest_path)
        if project:
            projects.append(project)

    return dedupe_projects(projects)


def project_info_for_manifest(
    source: ResolvedSource,
    repo_entity: EntityFact,
    manifest_path: Path,
) -> ProjectInfo | None:
    if manifest_path.name == "package.json":
        return javascript_project_info(source, repo_entity, manifest_path)
    if manifest_path.name == "pyproject.toml":
        return python_project_info(source, repo_entity, manifest_path)
    if is_requirements_file(manifest_path) and not (manifest_path.parent / "pyproject.toml").exists():
        return requirements_project_info(source, repo_entity, manifest_path)
    if manifest_path.suffix.lower() in DOTNET_PROJECT_SUFFIXES:
        return dotnet_project_info(source, repo_entity, manifest_path)
    if manifest_path.suffix.lower() == ".sln":
        return dotnet_solution_project_info(source, repo_entity, manifest_path)
    if manifest_path.name in {"App.config", "Web.config", "packages.config"}:
        return None
    return None
