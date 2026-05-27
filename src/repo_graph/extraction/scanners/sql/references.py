"""SQL object reference extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.sql.naming import normalize_sql_name
from repo_graph.extraction.scanners.sql.properties import (
    source_context_properties,
    sql_interaction_properties,
    sql_reference_properties,
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


def scan_sql_references(
    context: FileScanContext,
    content: str,
    from_entity: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    for line_number, line in enumerate(content.splitlines(), start=1):
        facts.relationships.extend(sql_reference_facts_for_line(context, line, line_number, from_entity=from_entity))
    return facts


def sql_reference_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    extra_properties = source_context_properties(from_entity)
    return [
        *sql_call_facts(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_read_facts(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_write_facts(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_schema_reference_facts(
            context,
            line,
            line_number,
            from_entity=from_entity,
            extra_properties=extra_properties,
        ),
    ]


def sql_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    return [
        unresolved_relationship_fact(
            source_ref,
            normalize_sql_name(match.group(1)),
            "CALLS_SQL",
            context,
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


def sql_object_read_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    return [
        unresolved_relationship_fact(
            source_ref,
            normalize_sql_name(match.group("target")),
            "READS_SQL_OBJECT",
            context,
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


def sql_object_write_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    return [
        unresolved_relationship_fact(
            source_ref,
            normalize_sql_name(match.group("target")),
            "WRITES_SQL_OBJECT",
            context,
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


def sql_object_schema_reference_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    return [
        unresolved_relationship_fact(
            source_ref,
            normalize_sql_name(match.group("target")),
            "REFERENCES_SQL_OBJECT",
            context,
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


def sql_write_reference_matches(line: str) -> Iterable[tuple[str, re.Match[str]]]:
    for operation, pattern in SQL_WRITE_REF_PATTERNS:
        for match in pattern.finditer(line):
            if sql_reference_target_is_valid(match.group("target")):
                yield operation, match


def sql_reference_target_is_valid(target: str) -> bool:
    return normalize_sql_name(target).upper() not in SQL_REFERENCE_STOPWORDS


def stored_procedure_target(value: str) -> str | None:
    exec_match = SQL_EXEC_RE.search(value)
    if exec_match:
        return normalize_sql_name(exec_match.group(1))
    stripped = value.strip()
    if re.fullmatch(r"[\[\]\w]+(?:\.[\[\]\w]+)+", stripped):
        return normalize_sql_name(stripped)
    return None
