"""Unresolved edge classification vocabulary."""

from __future__ import annotations

from dataclasses import dataclass

MISSING_SOURCE_EDGE_TYPES = frozenset(
    {
        "CALLS_SERVICE",
        "CALLS_SQL",
        "CONFIGURES_SERVICE",
        "DEPENDS_ON_PACKAGE",
        "DEPENDS_ON_PROJECT",
        "READS_SQL_OBJECT",
        "REFERENCES_SQL_OBJECT",
        "ROUTES_TO_SERVICE",
        "TRIGGERS_ON_SQL_OBJECT",
        "WRITES_SQL_OBJECT",
    }
)
PARSER_GAP_EDGE_TYPES = frozenset(
    {
        "CALLS_HTTP",
        "CALLS_SYMBOL",
        "DECLARES_SYMBOL",
        "IMPORTS",
    }
)
LOCAL_EDGE_PREFIXES = (
    "CONTAINS_",
    "DECLARES_",
    "EXPOSES_",
    "RUNS_",
    "SELECTS_",
)
MISSING_SOURCE_TARGET_TYPES = frozenset(
    {
        "package",
        "project",
        "repository",
        "service",
        "message_contract",
        "message_queue",
        "message_topic",
        "cache_key",
        "cache_store",
        "sql_function",
        "sql_object",
        "sql_table",
        "sql_trigger",
        "sql_view",
        "stored_procedure",
        "storage_location",
    }
)
PARSER_GAP_TARGET_TYPES = frozenset(
    {
        "api_route",
        "class",
        "function",
        "interface",
        "module",
    }
)


@dataclass(frozen=True)
class UnresolvedClassification:
    name: str
    rank: int
    recommended_action: str


UNRESOLVED_CLASSIFICATIONS = (
    UnresolvedClassification(
        "likely_missing_source",
        0,
        "Add or sync the repository, package, service, or database project that owns this target.",
    ),
    UnresolvedClassification(
        "likely_parser_gap",
        1,
        "Improve extractor coverage or add a parser slice for this declaration or reference shape.",
    ),
    UnresolvedClassification(
        "ambiguous_target",
        2,
        "Review the candidates and add enough context for Repo Graph to resolve the target safely.",
    ),
    UnresolvedClassification(
        "needs_review",
        3,
        "Inspect the evidence and decide whether this is missing scope, a parser gap, or expected dynamic behavior.",
    ),
)
CLASSIFICATION_ORDER = {item.name: item.rank for item in UNRESOLVED_CLASSIFICATIONS}
CLASSIFICATION_ACTIONS = {item.name: item.recommended_action for item in UNRESOLVED_CLASSIFICATIONS}
