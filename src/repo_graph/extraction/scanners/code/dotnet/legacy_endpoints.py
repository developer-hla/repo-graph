"""Legacy ASMX and WCF endpoint scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.interactions.routes import route_entity_fact


class LegacyDotnetEndpointExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="legacy_dotnet_endpoint",
        family="code",
        target_patterns=("*.asmx", "*.svc"),
        parser_ids=("legacy_dotnet_endpoint",),
        description="Legacy ASMX and WCF endpoint route declarations.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".asmx", ".svc"}

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        suffix = Path(context.rel_path).suffix.lower()
        framework = "asmx" if suffix == ".asmx" else "wcf"
        path = "/" + context.rel_path.replace("\\", "/")
        route = route_entity_fact(context, "POST", path, 1, framework, operation_name=None)
        facts.entities.append(route)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                route.reference,
                "DECLARES_ROUTE",
                context,
                self.name,
                1,
            )
        )
        if context.project:
            facts.relationships.append(
                resolved_relationship_fact(
                    entity_reference(context.project.entity),
                    route.reference,
                    "EXPOSES_ROUTE",
                    context,
                    self.name,
                    1,
                )
            )
        return facts
