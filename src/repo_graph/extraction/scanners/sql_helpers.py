"""SQL scanner helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.legacy_graph_helpers import interaction_properties, resolved_edge, unresolved_edge
from repo_graph.graph import Edge, Entity

SQL_OBJECT_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\s+([\[\]\w.]+)",
    re.IGNORECASE,
)


SQL_OBJECT_KIND_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\b",
    re.IGNORECASE,
)


SQL_EXEC_RE = re.compile(r"\bEXEC(?:UTE)?\s+([\[\]\w.]+)", re.IGNORECASE)


SQL_READ_REF_RE = re.compile(
    r"\b(?P<operation>FROM|JOIN)\s+(?P<target>[\[\]\w.]+)(?![\w.]|\s+import\b)",
    re.IGNORECASE,
)


SQL_WRITE_REF_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("INSERT", re.compile(r"\bINSERT\s+(?:INTO\s+)?(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("UPDATE", re.compile(r"\bUPDATE\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("DELETE", re.compile(r"\bDELETE\s+FROM\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("MERGE", re.compile(r"\bMERGE\s+(?:INTO\s+)?(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\s+TABLE\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("SELECT_INTO", re.compile(r"\bSELECT\b.*?\bINTO\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
)


SQL_SCHEMA_REF_RE = re.compile(r"\bREFERENCES\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)


SQL_REFERENCE_STOPWORDS = frozenset(
    {
        "ACTION",
        "AS",
        "CASCADE",
        "DEFAULT",
        "FROM",
        "NO",
        "NULL",
        "ON",
        "OUTPUT",
        "REFERENCES",
        "SELECT",
        "SET",
        "TABLE",
        "VALUES",
        "WHERE",
    }
)


SQL_BATCH_SEPARATOR_RE = re.compile(r"^\s*GO(?:\s+\d+)?\s*;?\s*$", re.IGNORECASE)


def scan_sql_references(context: FileScanContext, content: str, from_entity: Entity | None = None) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.edges.extend(sql_reference_edges_for_line(context, line, line_number, from_entity=from_entity))
    return result


def sql_reference_edges_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    extra_properties = source_context_properties(from_entity)
    return [
        *sql_call_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_read_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_write_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_schema_reference_edges(
            context,
            line,
            line_number,
            from_entity=from_entity,
            extra_properties=extra_properties,
        ),
    ]


def sql_definition_entities_and_edges(context: FileScanContext, line: str, line_number: int) -> ScanResult:
    result = ScanResult()
    kind_match = SQL_OBJECT_KIND_RE.search(line)
    object_match = SQL_OBJECT_RE.search(line)
    if not kind_match or not object_match:
        return result

    entity_type = sql_entity_type(kind_match.group(1))
    name = normalize_sql_name(object_match.group(1))
    schema, short_name = split_schema_name(name)
    entity = Entity(
        entity_type=entity_type,
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases={short_name},
        properties={
            "schema": schema,
            "full_name": name,
            "project": context.project.name if context.project else None,
            **sql_source_provenance(context.rel_path),
        },
    )
    result.entities.append(entity)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            entity,
            "DEFINES",
            context.source.name,
            context.rel_path,
            "sql",
            line_number,
        )
    )
    return result


def sql_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group(1)),
            "CALLS_SQL",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="stored_procedure",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group(1),
                "EXECUTE",
                "stored_procedure",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_EXEC_RE.finditer(line)
    ]


def sql_object_read_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "READS_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                match.group("operation"),
                "sql_object",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_READ_REF_RE.finditer(line)
    ]


def sql_object_write_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "WRITES_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                operation,
                "sql_object",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for operation, match in sql_write_reference_matches(line)
    ]


def sql_object_schema_reference_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "REFERENCES_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                "REFERENCES",
                "sql_object",
                dependency_scope="schema",
                interaction_kind="sql_schema_reference",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_SCHEMA_REF_RE.finditer(line)
        if sql_reference_target_is_valid(match.group("target"))
    ]


def sql_interaction_properties(
    raw_target: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str = "runtime",
    interaction_kind: str = "sql_reference",
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties = interaction_properties(
        "database",
        dependency_scope,
        interaction_kind,
        protocol="sql",
        raw_target=raw_target,
        normalized_target=normalize_sql_name(raw_target),
        sql_operation=operation.upper(),
        database_object_type=database_object_type,
    )
    if extra_properties:
        properties.update(extra_properties)
    return properties


def sql_write_reference_matches(line: str) -> Iterable[tuple[str, re.Match[str]]]:
    for operation, pattern in SQL_WRITE_REF_PATTERNS:
        for match in pattern.finditer(line):
            if sql_reference_target_is_valid(match.group("target")):
                yield operation, match


def sql_reference_target_is_valid(target: str) -> bool:
    return normalize_sql_name(target).upper() not in SQL_REFERENCE_STOPWORDS


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


def sql_reference_properties(
    context: FileScanContext,
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = sql_reference_extra_properties(context)
    if extra_properties:
        properties.update(extra_properties)
    return properties


def source_context_properties(from_entity: Entity | None) -> dict[str, str]:
    if not from_entity or from_entity.entity_type == "file":
        return {}
    return {
        "source_context_type": from_entity.entity_type,
        "source_context_name": from_entity.name,
    }


def stored_procedure_target(value: str) -> str | None:
    exec_match = SQL_EXEC_RE.search(value)
    if exec_match:
        return normalize_sql_name(exec_match.group(1))
    stripped = value.strip()
    if re.fullmatch(r"[\[\]\w]+(?:\.[\[\]\w]+)+", stripped):
        return normalize_sql_name(stripped)
    return None


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


def normalize_sql_name(value: str) -> str:
    return value.strip().replace("[", "").replace("]", "")


def split_schema_name(value: str) -> tuple[str | None, str]:
    parts = value.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, value
