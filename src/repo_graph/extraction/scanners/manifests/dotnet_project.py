""".NET project and config manifest scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_fact,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
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
