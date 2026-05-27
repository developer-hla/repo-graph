"""Shared JavaScript export symbol helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import FactBatch

EXPORT_FUNCTION_RE = re.compile(r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
EXPORT_CLASS_RE = re.compile(r"\bexport\s+class\s+([A-Za-z_$][\w$]*)")
EXPORT_CONST_RE = re.compile(
    r"\bexport\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)?\s*=>"
)


def export_symbol_facts(context: FileScanContext, line: str, line_number: int) -> FactBatch:
    facts = FactBatch()
    for entity_type, name in exported_symbols(line):
        symbol = entity_fact(
            context,
            entity_type=entity_type,
            name=name,
            line_number=line_number,
            aliases={name},
            properties={"project": context.project.name if context.project else None},
        )
        facts.entities.append(symbol)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                symbol.reference,
                "DECLARES_SYMBOL",
                context,
                "javascript_export",
                line_number,
            )
        )
    return facts


def exported_symbols(line: str) -> Iterable[tuple[str, str]]:
    for match in EXPORT_FUNCTION_RE.finditer(line):
        yield "function", match.group(1)
    for match in EXPORT_CLASS_RE.finditer(line):
        yield "class", match.group(1)
    for match in EXPORT_CONST_RE.finditer(line):
        yield "function", match.group(1)
