"""SQL scanners."""

from __future__ import annotations

import re
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.sql.definitions import sql_definition_facts
from repo_graph.extraction.scanners.sql.references import scan_sql_references, sql_reference_facts_for_line

SQL_BATCH_SEPARATOR_RE = re.compile(r"^\s*GO(?:\s+\d+)?\s*;?\s*$", re.IGNORECASE)


class SqlExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="sql",
        family="sql",
        target_patterns=("*.sql",),
        parser_ids=("sql", "sql_reference"),
        description="SQL object definitions and SQL-to-SQL references.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sql"

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        current_sql_entity: EntityFact | None = None
        for line_number, line in enumerate(content.splitlines(), start=1):
            if SQL_BATCH_SEPARATOR_RE.match(line):
                current_sql_entity = None
                continue
            definition_facts = sql_definition_facts(context, line, line_number)
            facts.extend(definition_facts)
            if definition_facts.entities:
                current_sql_entity = definition_facts.entities[-1]
            facts.relationships.extend(
                sql_reference_facts_for_line(context, line, line_number, from_entity=current_sql_entity)
            )
        return facts


class SqlReferenceExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="sql_reference",
        family="sql",
        target_patterns=("*.cs", "*.js", "*.jsx", "*.py", "*.ts", "*.tsx", "*.vb"),
        parser_ids=("sql_reference",),
        description="Embedded SQL references in application code.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".cs", ".js", ".jsx", ".py", ".ts", ".tsx", ".vb"}

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        return scan_sql_references(context, content)
