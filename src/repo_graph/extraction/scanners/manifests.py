"""Manifest and package scanners."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_fact,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
    resolved_relationship_fact,
    scan_issue,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.common import read_yaml_object, string_value
from repo_graph.extraction.scanners.manifest_dotnet_helpers import (
    DOTNET_BUILD_SUFFIXES,
    DOTNET_PROJECT_SUFFIXES,
    config_file_fact,
    config_service_fact,
    dotnet_package_references,
    dotnet_project_metadata_from_root,
    dotnet_project_references,
    framework_config_value_facts,
    packages_config_references,
    solution_project_reference,
    xml_root,
)
from repo_graph.extraction.scanners.manifest_helpers import is_requirements_file
from repo_graph.extraction.scanners.package_helpers import (
    normalize_python_package_name,
    package_dependencies,
    pyproject_dependencies,
    pyproject_metadata,
    python_import_name,
    requirement_dependency,
)


class PackageJsonExtractor:
    name = "package_json"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "package.json"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        try:
            package = json.loads(content)
        except json.JSONDecodeError as exc:
            facts.issues.append(
                scan_issue(context, self.name, f"Invalid package.json {context.source.name}/{context.rel_path}: {exc}")
            )
            return facts
        if not isinstance(package, dict):
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid package.json {context.source.name}/{context.rel_path}: root must be object",
                )
            )
            return facts

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
            facts.entities.append(package_fact)
            package_ref = package_fact.reference
            facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in package_dependencies(package):
            facts.relationships.append(
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

        return facts


class PythonProjectExtractor:
    name = "pyproject"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pyproject.toml"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        try:
            pyproject = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: {exc}",
                )
            )
            return facts
        if not isinstance(pyproject, dict):
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: root must be object",
                )
            )
            return facts

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
            facts.entities.append(package_fact)
            package_ref = package_fact.reference
            facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in pyproject_dependencies(pyproject):
            facts.relationships.append(
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
        return facts


class PythonRequirementsExtractor:
    name = "requirements"

    def can_process(self, rel_path: str) -> bool:
        return is_requirements_file(Path(rel_path))

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        dependency_source = context.project.entity if context.project else context.file_entity
        for line_number, line in enumerate(content.splitlines(), start=1):
            dependency = requirement_dependency(line)
            if not dependency:
                continue
            facts.relationships.append(
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
        return facts


class DotnetProjectExtractor:
    name = "dotnet_project"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in DOTNET_PROJECT_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)
        if root is None:
            return facts

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
            facts.entities.append(package_fact)
            package_ref = package_fact.reference
            facts.relationships.extend(declares_package_facts(context, package_ref, self.name))

        dependency_source_ref = (
            package_ref
            if package_ref
            else entity_reference(context.project.entity if context.project else context.file_entity)
        )
        for dependency in dotnet_package_references(root):
            facts.relationships.append(
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
            facts.relationships.append(
                unresolved_relationship_fact(
                    entity_reference(context.project.entity if context.project else context.file_entity),
                    reference["name"],
                    "DEPENDS_ON_PROJECT",
                    context,
                    self.name,
                    to_type="project",
                    properties=reference,
                )
            )
        return facts


class DotnetPackagesConfigExtractor:
    name = "packages_config"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "packages.config"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)
        config_fact = config_file_fact(context, "packages_config")
        facts.entities.append(config_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                config_fact.reference,
                "DECLARES_CONFIG_FILE",
                context,
                self.name,
            )
        )
        for dependency in packages_config_references(root):
            facts.relationships.append(
                package_dependency_fact(
                    entity_reference(context.project.entity if context.project else context.file_entity),
                    dependency["name"],
                    "dotnet",
                    "packages.config",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        return facts


class DotnetFrameworkConfigExtractor:
    name = "dotnet_framework_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.suffix.lower() == ".config" and path.name != "packages.config"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)
        config_fact = config_file_fact(context, "dotnet_framework_config")
        facts.entities.append(config_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                config_fact.reference,
                "DECLARES_CONFIG_FILE",
                context,
                self.name,
            )
        )
        for config_value in framework_config_value_facts(context, root):
            facts.entities.append(config_value)
            facts.relationships.append(
                resolved_relationship_fact(
                    config_fact.reference,
                    config_value.reference,
                    "DECLARES_CONFIG",
                    context,
                    self.name,
                )
            )
            service_fact = config_service_fact(config_value, context, self.name)
            if service_fact:
                facts.relationships.append(service_fact)
        return facts


class DotnetBuildConfigExtractor:
    name = "dotnet_build_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.name == "Directory.Build.props" or path.suffix.lower() in DOTNET_BUILD_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)
        if root is None:
            return facts

        config_fact = entity_fact(
            context,
            entity_type="build_config",
            name=Path(context.rel_path).name,
            aliases={Path(context.rel_path).name},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        facts.entities.append(config_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                config_fact.reference,
                "DECLARES_BUILD_CONFIG",
                context,
                self.name,
            )
        )
        for dependency in dotnet_package_references(root):
            facts.relationships.append(
                package_dependency_fact(
                    config_fact.reference,
                    dependency["name"],
                    "dotnet",
                    "PackageReference",
                    dependency["version"],
                    dependency["raw_target"],
                    context,
                    self.name,
                )
            )
        return facts


class DotnetSolutionExtractor:
    name = "dotnet_solution"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sln"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        solution_fact = entity_fact(
            context,
            entity_type="solution",
            name=Path(context.rel_path).stem,
            aliases={Path(context.rel_path).stem},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        facts.entities.append(solution_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                solution_fact.reference,
                "DECLARES_SOLUTION",
                context,
                self.name,
            )
        )
        for line_number, line in enumerate(content.splitlines(), start=1):
            reference = solution_project_reference(line)
            if not reference:
                continue
            facts.relationships.append(
                unresolved_relationship_fact(
                    solution_fact.reference,
                    reference["name"],
                    "CONTAINS_PROJECT",
                    context,
                    self.name,
                    to_type="project",
                    line_number=line_number,
                    properties=reference,
                )
            )
        return facts


class PnpmWorkspaceExtractor:
    name = "pnpm_workspace"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pnpm-workspace.yaml"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        data = read_yaml_object(content)
        package_patterns = data.get("packages") if data else None
        workspace_fact = entity_fact(
            context,
            entity_type="workspace",
            name=f"{context.source.name} workspace",
            aliases={context.source.name},
            properties={
                "ecosystem": "javascript",
                "path": context.rel_path,
                "package_patterns": package_patterns if isinstance(package_patterns, list) else [],
            },
        )
        facts.entities.append(workspace_fact)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                workspace_fact.reference,
                "DECLARES_WORKSPACE",
                context,
                self.name,
            )
        )
        return facts
