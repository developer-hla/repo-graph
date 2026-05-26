"""SQL scanners."""

from __future__ import annotations

from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.facts import EntityFact
from repo_graph.extraction.scanners.sql_helpers import (
    SQL_BATCH_SEPARATOR_RE,
    scan_sql_references,
    sql_definition_facts,
    sql_reference_facts_for_line,
)


class SqlExtractor:
    name = "sql"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sql"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        current_sql_entity: EntityFact | None = None
        for line_number, line in enumerate(content.splitlines(), start=1):
            if SQL_BATCH_SEPARATOR_RE.match(line):
                current_sql_entity = None
                continue
            definition_facts = sql_definition_facts(context, line, line_number)
            result.facts.extend(definition_facts)
            if definition_facts.entities:
                current_sql_entity = definition_facts.entities[-1]
            result.facts.relationships.extend(
                sql_reference_facts_for_line(context, line, line_number, from_entity=current_sql_entity)
            )
        return result


class SqlReferenceExtractor:
    name = "sql_reference"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".cs", ".js", ".jsx", ".py", ".ts", ".tsx", ".vb"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        return scan_sql_references(context, content)
