"""JavaScript and TypeScript source scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.interaction_helpers import (
    export_symbol_facts,
    http_call_facts,
    import_facts,
    route_facts,
)


class JavaScriptExtractor:
    name = "javascript"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        for line_number, line in enumerate(content.splitlines(), start=1):
            facts.relationships.extend(import_facts(context, line, line_number))
            facts.extend(route_facts(context, line, line_number))
            facts.extend(export_symbol_facts(context, line, line_number))
            facts.relationships.extend(http_call_facts(context, line, line_number))
        return facts
