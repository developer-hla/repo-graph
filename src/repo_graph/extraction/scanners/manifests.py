"""Manifest and package scanners."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
)
from repo_graph.extraction.legacy_graph_helpers import resolved_edge, unresolved_edge
from repo_graph.extraction.scanners.common import read_yaml_object, string_value
from repo_graph.extraction.scanners.dotnet_helpers import (
    DOTNET_BUILD_SUFFIXES,
    DOTNET_PROJECT_SUFFIXES,
    config_file_entity,
    config_service_edge,
    dotnet_package_references,
    dotnet_project_metadata_from_root,
    dotnet_project_references,
    framework_config_values,
    packages_config_references,
    solution_project_reference,
    xml_root,
)
from repo_graph.extraction.scanners.manifest_helpers import is_requirements_file
from repo_graph.extraction.scanners.package_helpers import (
    normalize_python_package_name,
    package_dependencies,
    package_dependency_edge,
    pyproject_dependencies,
    pyproject_metadata,
    python_import_name,
    requirement_dependency,
)
from repo_graph.graph import Entity


class PackageJsonExtractor:
    name = "package_json"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "package.json"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            package = json.loads(content)
        except json.JSONDecodeError as exc:
            result.errors.append(f"Invalid package.json {context.source.name}/{context.rel_path}: {exc}")
            return result
        if not isinstance(package, dict):
            result.errors.append(f"Invalid package.json {context.source.name}/{context.rel_path}: root must be object")
            return result

        package_name = string_value(package.get("name"))
        package_ref = None
        if package_name:
            package_fact = package_entity_fact(
                context,
                name=package_name,
                aliases={package_name, package_name.removeprefix("@").split("/")[-1]},
                properties={
                    "version": package.get("version"),
                    "private": package.get("private"),
                    "scripts": sorted((package.get("scripts") or {}).keys())
                    if isinstance(package.get("scripts"), dict)
                    else [],
                },
            )
            result.facts.entities.append(package_fact)
            package_ref = package_fact.reference
            result.facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in package_dependencies(package):
            result.facts.relationships.append(
                package_dependency_fact(
                    dependency_source_ref,
                    dependency["name"],
                    "javascript",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )

        return result


class PythonProjectExtractor:
    name = "pyproject"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pyproject.toml"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            pyproject = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            result.errors.append(f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: {exc}")
            return result
        if not isinstance(pyproject, dict):
            result.errors.append(
                f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: root must be object"
            )
            return result

        metadata = pyproject_metadata(pyproject)
        package_ref = None
        if metadata["name"]:
            package_name = metadata["name"]
            package_fact = package_entity_fact(
                context,
                name=package_name,
                aliases={package_name, normalize_python_package_name(package_name), python_import_name(package_name)},
                properties={
                    "ecosystem": "python",
                    "version": metadata["version"],
                    "project": context.project.name if context.project else None,
                },
            )
            result.facts.entities.append(package_fact)
            package_ref = package_fact.reference
            result.facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in pyproject_dependencies(pyproject):
            result.facts.relationships.append(
                package_dependency_fact(
                    dependency_source_ref,
                    dependency["name"],
                    "python",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        return result


class PythonRequirementsExtractor:
    name = "requirements"

    def can_process(self, rel_path: str) -> bool:
        return is_requirements_file(Path(rel_path))

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        dependency_source = context.project.entity if context.project else context.file_entity
        for line_number, line in enumerate(content.splitlines(), start=1):
            dependency = requirement_dependency(line)
            if not dependency:
                continue
            result.facts.relationships.append(
                package_dependency_fact(
                    entity_reference(dependency_source),
                    dependency["name"],
                    "python",
                    "requirements",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                    line_number=line_number,
                )
            )
        return result


class DotnetProjectExtractor:
    name = "dotnet_project"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in DOTNET_PROJECT_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        if root is None:
            return result

        metadata = dotnet_project_metadata_from_root(root, Path(context.rel_path).stem)
        package_ref = None
        package_name = metadata["package_id"] or metadata["assembly_name"]
        if package_name:
            aliases = {package_name}
            if metadata["assembly_name"]:
                aliases.add(metadata["assembly_name"])
            package_fact = package_entity_fact(
                context,
                name=package_name,
                aliases=aliases,
                properties={
                    "ecosystem": "dotnet",
                    "version": metadata["version"],
                    "target_framework": metadata["target_framework"],
                    "target_frameworks": metadata["target_frameworks"],
                    "output_type": metadata["output_type"],
                    "project": context.project.name if context.project else None,
                },
            )
            result.facts.entities.append(package_fact)
            package_ref = package_fact.reference
            result.facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in dotnet_package_references(root):
            result.facts.relationships.append(
                package_dependency_fact(
                    dependency_source_ref,
                    dependency["name"],
                    "dotnet",
                    "PackageReference",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        for reference in dotnet_project_references(root):
            result.edges.append(
                unresolved_edge(
                    context.project.entity if context.project else context.file_entity,
                    reference["name"],
                    "DEPENDS_ON_PROJECT",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    to_type="project",
                    properties=reference,
                )
            )
        return result


class DotnetPackagesConfigExtractor:
    name = "packages_config"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "packages.config"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        dependency_source = context.project.entity if context.project else context.file_entity
        config_entity = config_file_entity(context, "packages_config")
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_CONFIG_FILE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for dependency in packages_config_references(root):
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "dotnet",
                    "packages.config",
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
        return result


class DotnetFrameworkConfigExtractor:
    name = "dotnet_framework_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.suffix.lower() == ".config" and path.name != "packages.config"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        config_entity = config_file_entity(context, "dotnet_framework_config")
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_CONFIG_FILE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for config_value in framework_config_values(context, root):
            result.entities.append(config_value)
            result.edges.append(
                resolved_edge(
                    config_entity,
                    config_value,
                    "DECLARES_CONFIG",
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
            service_edge = config_service_edge(config_value, context, self.name)
            if service_edge:
                result.edges.append(service_edge)
        return result


class DotnetBuildConfigExtractor:
    name = "dotnet_build_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.name == "Directory.Build.props" or path.suffix.lower() in DOTNET_BUILD_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        if root is None:
            return result

        config_entity = Entity(
            entity_type="build_config",
            name=Path(context.rel_path).name,
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={Path(context.rel_path).name},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_BUILD_CONFIG",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for dependency in dotnet_package_references(root):
            result.facts.relationships.append(
                package_dependency_fact(
                    entity_reference(config_entity),
                    dependency["name"],
                    "dotnet",
                    "PackageReference",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        return result


class DotnetSolutionExtractor:
    name = "dotnet_solution"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sln"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        solution = Entity(
            entity_type="solution",
            name=Path(context.rel_path).stem,
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={Path(context.rel_path).stem},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        result.entities.append(solution)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                solution,
                "DECLARES_SOLUTION",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for line_number, line in enumerate(content.splitlines(), start=1):
            reference = solution_project_reference(line)
            if not reference:
                continue
            result.edges.append(
                unresolved_edge(
                    solution,
                    reference["name"],
                    "CONTAINS_PROJECT",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    to_type="project",
                    line_number=line_number,
                    properties=reference,
                )
            )
        return result


class PnpmWorkspaceExtractor:
    name = "pnpm_workspace"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pnpm-workspace.yaml"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        data = read_yaml_object(content)
        package_patterns = data.get("packages") if data else None
        workspace = Entity(
            entity_type="workspace",
            name=f"{context.source.name} workspace",
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={context.source.name},
            properties={
                "ecosystem": "javascript",
                "path": context.rel_path,
                "package_patterns": package_patterns if isinstance(package_patterns, list) else [],
            },
        )
        result.entities.append(workspace)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                workspace,
                "DECLARES_WORKSPACE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        return result
