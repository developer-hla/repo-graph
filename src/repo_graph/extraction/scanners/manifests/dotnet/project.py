""".NET project manifest scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    declares_package_facts,
    entity_reference,
    package_dependency_fact,
    package_entity_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifests.dotnet.constants import DOTNET_PROJECT_SUFFIXES
from repo_graph.extraction.scanners.manifests.dotnet.metadata import dotnet_project_metadata_from_root
from repo_graph.extraction.scanners.manifests.dotnet.references import (
    dotnet_package_references,
    dotnet_project_references,
)
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import xml_root


class DotnetProjectExtractor:
    name = "dotnet_project"
    target_patterns = ("*.csproj", "*.fsproj", "*.vbproj")
    parser_ids = ("dotnet_project",)

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in DOTNET_PROJECT_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)

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
