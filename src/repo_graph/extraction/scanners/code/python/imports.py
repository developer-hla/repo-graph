"""Python import relationship helpers."""

from __future__ import annotations

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import RelationshipFact
from repo_graph.extraction.scanners.package_helpers import normalize_python_package_name


def python_import_fact(context: FileScanContext, raw_target: str, level: int, line_number: int) -> RelationshipFact:
    is_relative = level > 0 or raw_target.startswith(".")
    target_name = raw_target if is_relative else normalize_python_package_name(raw_target.split(".", 1)[0])
    return unresolved_relationship_fact(
        entity_reference(context.file_entity),
        target_name,
        "IMPORTS",
        context,
        "python_import",
        to_type="module" if is_relative else "package",
        line_number=line_number,
        properties={
            "raw_target": raw_target,
            "normalized_target": target_name,
            "import_kind": "relative" if is_relative else "package",
        },
    )
