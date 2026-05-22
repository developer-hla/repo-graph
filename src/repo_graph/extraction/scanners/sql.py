"""SQL scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.scanners.sql_helpers import (
    SQL_BATCH_SEPARATOR_RE,
    scan_sql_references,
    sql_call_edges,
    sql_definition_entities_and_edges,
    sql_object_read_edges,
    sql_object_schema_reference_edges,
    sql_object_write_edges,
)
from repo_graph.graph import Entity


class SqlExtractor:
    name = "sql"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sql"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        current_sql_entity: Entity | None = None
        for line_number, line in enumerate(content.splitlines(), start=1):
            if SQL_BATCH_SEPARATOR_RE.match(line):
                current_sql_entity = None
                continue
            definition_result = sql_definition_entities_and_edges(context, line, line_number)
            result.extend(definition_result)
            if definition_result.entities:
                current_sql_entity = definition_result.entities[-1]
            result.edges.extend(sql_call_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(sql_object_read_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(sql_object_write_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(
                sql_object_schema_reference_edges(context, line, line_number, from_entity=current_sql_entity)
            )
        return result


class SqlReferenceExtractor:
    name = "sql_reference"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".cs", ".js", ".jsx", ".py", ".ts", ".tsx", ".vb"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        return scan_sql_references(context, content)
