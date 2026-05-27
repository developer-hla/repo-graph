""".NET packages.config manifest scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.fact_helpers import (
    entity_reference,
    package_dependency_fact,
    resolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifests.dotnet.config import config_file_fact
from repo_graph.extraction.scanners.manifests.dotnet.references import packages_config_references
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import xml_root


class DotnetPackagesConfigExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="packages_config",
        family="manifest",
        target_patterns=("packages.config",),
        parser_ids=("packages_config",),
        description="Legacy .NET packages.config dependencies.",
    )

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
