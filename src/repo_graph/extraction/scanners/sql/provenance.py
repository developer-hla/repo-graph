"""SQL source provenance helpers."""

from __future__ import annotations

import re
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext


def sql_source_provenance(rel_path: str) -> dict[str, str]:
    path = Path(rel_path)
    lower_parts = {part.lower() for part in path.parts}
    filename = path.name.lower()
    if lower_parts.intersection({"migration", "migrations", "revision", "revisions", "rev", "revs", "alembic"}):
        return {"schema_state": "historical", "sql_source_kind": "migration_file"}
    if lower_parts.intersection({"flyway", "liquibase"}) or re.match(r"v\d+__", filename, re.IGNORECASE):
        return {"schema_state": "historical", "sql_source_kind": "migration_file"}
    if filename in {"schema.sql", "tables.sql", "views.sql", "functions.sql", "procedures.sql"}:
        return {"schema_state": "current_schema", "sql_source_kind": "schema_file"}
    return {"schema_state": "unknown", "sql_source_kind": "sql_file"}


def sql_reference_extra_properties(context: FileScanContext) -> dict[str, str]:
    if Path(context.rel_path).suffix.lower() == ".sql":
        return sql_source_provenance(context.rel_path)
    return {}
