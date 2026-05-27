""".NET build configuration manifest scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    package_dependency_fact,
    resolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifests.dotnet.constants import DOTNET_BUILD_SUFFIXES
from repo_graph.extraction.scanners.manifests.dotnet.references import dotnet_package_references
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import xml_root


class DotnetBuildConfigExtractor:
    name = "dotnet_build_config"
    target_patterns = ("Directory.Build.props", "*.props", "*.targets")
    parser_ids = ("dotnet_build_config",)

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.name == "Directory.Build.props" or path.suffix.lower() in DOTNET_BUILD_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        root = xml_root(content, context)

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
