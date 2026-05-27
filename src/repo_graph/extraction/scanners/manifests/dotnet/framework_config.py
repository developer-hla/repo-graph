""".NET framework configuration manifest scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifests.dotnet.config import (
    config_file_fact,
    config_service_fact,
    framework_config_value_facts,
)
from repo_graph.extraction.scanners.manifests.dotnet.xml_utils import xml_root


class DotnetFrameworkConfigExtractor:
    name = "dotnet_framework_config"
    target_patterns = ("*.config except packages.config",)
    parser_ids = ("dotnet_framework_config",)

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
