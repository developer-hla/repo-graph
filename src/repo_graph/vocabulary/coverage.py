"""Coverage warning vocabulary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageWarningRule:
    target: str
    code: str
    message: str
    severity: str


EDGE_TYPE_COVERAGE_WARNING_RULES = (
    CoverageWarningRule("CALLS_SQL", "unresolved_sql_calls", "This source has unresolved SQL calls.", "warning"),
    CoverageWarningRule(
        "READS_SQL_OBJECT",
        "unresolved_sql_reads",
        "This source has unresolved SQL object reads.",
        "warning",
    ),
    CoverageWarningRule(
        "WRITES_SQL_OBJECT",
        "unresolved_sql_writes",
        "This source has unresolved SQL object writes.",
        "warning",
    ),
    CoverageWarningRule(
        "REFERENCES_SQL_OBJECT",
        "unresolved_sql_schema_references",
        "This source has unresolved SQL schema references.",
        "warning",
    ),
    CoverageWarningRule(
        "CALLS_SERVICE",
        "unresolved_service_calls",
        "This source has unresolved service calls.",
        "warning",
    ),
    CoverageWarningRule("CALLS_HTTP", "unresolved_http_calls", "This source has unresolved HTTP calls.", "warning"),
    CoverageWarningRule("IMPORTS", "unresolved_imports", "This source has unresolved imports.", "info"),
)
CLASSIFICATION_COVERAGE_WARNING_RULES = (
    CoverageWarningRule(
        "likely_parser_gap",
        "parser_gap",
        "Parser gaps may hide local symbol, route, or import relationships.",
        "warning",
    ),
    CoverageWarningRule(
        "ambiguous_target",
        "ambiguous_targets",
        "Ambiguous targets exist and were not linked.",
        "warning",
    ),
    CoverageWarningRule(
        "likely_missing_source",
        "missing_source",
        "Missing source coverage may hide additional blast radius.",
        "warning",
    ),
)
