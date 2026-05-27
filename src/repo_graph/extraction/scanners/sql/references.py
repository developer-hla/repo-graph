"""SQL object reference extraction."""

from __future__ import annotations

import re
from collections.abc import Iterable

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.sql.facts import (
    sql_call_fact,
    sql_object_read_fact,
    sql_object_write_fact,
    sql_schema_reference_fact,
)
from repo_graph.extraction.scanners.sql.naming import normalize_sql_name

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
    return [
        *sql_call_facts(context, line, line_number, from_entity=from_entity),
        *sql_object_read_facts(context, line, line_number, from_entity=from_entity),
        *sql_object_write_facts(context, line, line_number, from_entity=from_entity),
        *sql_object_schema_reference_facts(
            context,
            line,
            line_number,
            from_entity=from_entity,
        ),
    ]


def sql_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    return [
        sql_call_fact(
            context,
            match.group(1),
            line_number,
            from_entity=from_entity,
        )
        for match in SQL_EXEC_RE.finditer(line)
    ]


def sql_object_read_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    return [
        sql_object_read_fact(
            context,
            match.group("target"),
            match.group("operation"),
            line_number,
            from_entity=from_entity,
        )
        for match in SQL_READ_REF_RE.finditer(line)
    ]


def sql_object_write_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    return [
        sql_object_write_fact(
            context,
            match.group("target"),
            operation,
            line_number,
            from_entity=from_entity,
        )
        for operation, match in sql_write_reference_matches(line)
    ]


def sql_object_schema_reference_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    return [
        sql_schema_reference_fact(
            context,
            match.group("target"),
            line_number,
            from_entity=from_entity,
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
