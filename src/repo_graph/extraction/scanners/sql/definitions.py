"""SQL object definition extraction."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.sql.naming import normalize_sql_name, split_schema_name
from repo_graph.extraction.scanners.sql.provenance import sql_source_provenance

SQL_OBJECT_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\s+([\[\]\w.]+)",
    re.IGNORECASE,
)

SQL_OBJECT_KIND_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\b",
    re.IGNORECASE,
)


def sql_definition_facts(context: FileScanContext, line: str, line_number: int) -> FactBatch:
    facts = FactBatch()
    kind_match = SQL_OBJECT_KIND_RE.search(line)
    object_match = SQL_OBJECT_RE.search(line)
    if not kind_match or not object_match:
        return facts

    entity_type = sql_entity_type(kind_match.group(1))
    name = normalize_sql_name(object_match.group(1))
    schema, short_name = split_schema_name(name)
    entity = entity_fact(
        context,
        entity_type=entity_type,
        name=name,
        line_number=line_number,
        aliases={short_name},
        properties={
            "schema": schema,
            "full_name": name,
            "project": context.project.name if context.project else None,
            **sql_source_provenance(context.rel_path),
        },
    )
    facts.entities.append(entity)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            entity.reference,
            "DEFINES",
            context,
            "sql",
            line_number,
        )
    )
    return facts


def sql_entity_type(kind: str) -> str:
    normalized = kind.upper()
    if normalized in {"PROCEDURE", "PROC"}:
        return "stored_procedure"
    if normalized == "TABLE":
        return "sql_table"
    if normalized == "VIEW":
        return "sql_view"
    if normalized == "FUNCTION":
        return "sql_function"
    return "sql_object"
