"""Package and dependency scanner helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.legacy_graph_helpers import unresolved_edge
from repo_graph.extraction.scanners.common import object_mapping, string_value
from repo_graph.graph import Edge, Entity

REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")


def package_dependencies(package: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for dependency_type in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = package.get(dependency_type)
        if isinstance(deps, dict):
            for dep_name, version in deps.items():
                if isinstance(dep_name, str):
                    yield {
                        "name": package_root(dep_name),
                        "version": version if isinstance(version, str) else None,
                        "dependency_type": dependency_type,
                        "raw_target": dep_name,
                    }


def pyproject_metadata(pyproject: dict[str, Any]) -> dict[str, str | None]:
    project = object_mapping(pyproject.get("project"))
    poetry = object_mapping(object_mapping(pyproject.get("tool")).get("poetry"))
    name = string_value(project.get("name")) or string_value(poetry.get("name"))
    version = string_value(project.get("version")) or string_value(poetry.get("version"))
    return {"name": name, "version": version}


def pyproject_dependencies(pyproject: dict[str, Any]) -> Iterable[dict[str, str | None]]:
    project = object_mapping(pyproject.get("project"))
    raw_dependencies = project.get("dependencies")
    if isinstance(raw_dependencies, list):
        for raw_dependency in raw_dependencies:
            if isinstance(raw_dependency, str):
                dependency = requirement_dependency(raw_dependency)
                if dependency:
                    dependency["dependency_type"] = "project.dependencies"
                    yield dependency

    optional_dependencies = object_mapping(project.get("optional-dependencies"))
    for group_name, dependencies in optional_dependencies.items():
        if not isinstance(dependencies, list):
            continue
        for raw_dependency in dependencies:
            if isinstance(raw_dependency, str):
                dependency = requirement_dependency(raw_dependency)
                if dependency:
                    dependency["dependency_type"] = f"project.optional-dependencies.{group_name}"
                    yield dependency

    poetry = object_mapping(object_mapping(pyproject.get("tool")).get("poetry"))
    for dependency_type, dependencies in poetry_dependency_groups(poetry):
        for package_name, version in dependencies.items():
            if not isinstance(package_name, str) or package_name.lower() == "python":
                continue
            yield {
                "name": normalize_python_package_name(package_name),
                "version": dependency_version(version),
                "dependency_type": dependency_type,
                "raw_target": package_name,
            }


def poetry_dependency_groups(poetry: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    dependencies = object_mapping(poetry.get("dependencies"))
    if dependencies:
        yield "tool.poetry.dependencies", dependencies

    dev_dependencies = object_mapping(poetry.get("dev-dependencies"))
    if dev_dependencies:
        yield "tool.poetry.dev-dependencies", dev_dependencies

    groups = object_mapping(poetry.get("group"))
    for group_name, group_data in groups.items():
        group_dependencies = object_mapping(object_mapping(group_data).get("dependencies"))
        if group_dependencies:
            yield f"tool.poetry.group.{group_name}.dependencies", group_dependencies


def dependency_version(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        version = value.get("version")
        return version if isinstance(version, str) else None
    return None


def requirement_dependency(line: str) -> dict[str, str | None] | None:
    raw_target = line.strip()
    if not raw_target or raw_target.startswith("#") or raw_target.startswith(("-", "--")):
        return None
    raw_target = raw_target.split(" #", 1)[0].strip()
    match = REQUIREMENT_NAME_RE.match(raw_target)
    if not match:
        return None
    name = normalize_python_package_name(match.group(1))
    version = raw_target[match.end() :].strip() or None
    return {
        "name": name,
        "version": version,
        "dependency_type": None,
        "raw_target": raw_target,
    }


def normalize_python_package_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def python_import_name(value: str) -> str:
    return normalize_python_package_name(value).replace("-", "_")


def dependency_source_entity(context: FileScanContext, package_entity: Entity | None = None) -> Entity:
    if package_entity:
        return package_entity
    if context.project:
        return context.project.entity
    return context.file_entity


def package_dependency_edge(
    from_entity: Entity,
    name: str | None,
    ecosystem: str,
    dependency_type: str | None,
    version: str | None,
    raw_target: str | None,
    source_name: str,
    file_path: str,
    parser: str,
    line_number: int | None = None,
) -> Edge:
    target_name = name or raw_target or ""
    return unresolved_edge(
        from_entity,
        target_name,
        "DEPENDS_ON_PACKAGE",
        source_name,
        file_path,
        parser,
        to_type="package",
        line_number=line_number,
        properties={
            "ecosystem": ecosystem,
            "dependency_type": dependency_type,
            "version": version,
            "raw_target": raw_target,
            "normalized_target": target_name,
        },
    )


def package_root(value: str) -> str:
    if value.startswith("@"):
        parts = value.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else value
    return value.split("/")[0]


def import_target_name(raw_target: str) -> str:
    if raw_target.startswith("."):
        return raw_target
    return package_root(raw_target)
