"""Shared import relationship helpers."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import RelationshipFact
from repo_graph.extraction.scanners.package_helpers import import_target_name

IMPORT_RE = re.compile(
    r"(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+|require\s*\()\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


def import_facts(context: FileScanContext, line: str, line_number: int) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for match in IMPORT_RE.finditer(line):
        raw_target = match.group(1)
        target_name = import_target_name(raw_target)
        is_package = not raw_target.startswith(".")
        facts.append(
            unresolved_relationship_fact(
                entity_reference(context.file_entity),
                target_name,
                "IMPORTS",
                context,
                "javascript_import",
                to_type="package" if is_package else "module",
                line_number=line_number,
                properties={
                    "raw_target": raw_target,
                    "normalized_target": target_name,
                    "import_kind": "package" if is_package else "relative",
                },
            )
        )
    return facts
