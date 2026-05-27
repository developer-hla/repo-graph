""".NET solution manifest scanner."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.manifests.dotnet.solutions import solution_project_reference


class DotnetSolutionExtractor:
    name = "dotnet_solution"
    target_patterns = ("*.sln",)
    parser_ids = ("dotnet_solution",)

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
