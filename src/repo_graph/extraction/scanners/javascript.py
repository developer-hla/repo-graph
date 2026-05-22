"""JavaScript and TypeScript source scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.scanners.shared import (
    export_entities_and_edges,
    http_call_edges,
    import_edges,
    route_entities_and_edges,
)


class JavaScriptExtractor:
    name = "javascript"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.edges.extend(import_edges(context, line, line_number))
            result.extend(route_entities_and_edges(context, line, line_number))
            result.extend(export_entities_and_edges(context, line, line_number))
            result.edges.extend(http_call_edges(context, line, line_number))
        return result
