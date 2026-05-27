"""Blast-radius profile vocabulary."""

from __future__ import annotations

IMPACT_EDGE_TYPES = frozenset(
    {
        "CALLS_HTTP",
        "CALLS_SERVICE",
        "CALLS_SQL",
        "CALLS_SYMBOL",
        "CONFIGURES_SERVICE",
        "CONSUMES_MESSAGE",
        "DEPENDS_ON_PACKAGE",
        "DEPENDS_ON_PROJECT",
        "HANDLES_ROUTE",
        "IMPORTS",
        "PUBLISHES_MESSAGE",
        "READS_CACHE_KEY",
        "READS_SQL_OBJECT",
        "READS_STORAGE_OBJECT",
        "REFERENCES_SQL_OBJECT",
        "ROUTES_TO_SERVICE",
        "SELECTS_DEPLOYMENT",
        "TRIGGERS_ON_SQL_OBJECT",
        "WRITES_SQL_OBJECT",
        "WRITES_STORAGE_OBJECT",
        "WRITES_CACHE_KEY",
        "RUNS_JOB",
        "SCHEDULES_JOB",
    }
)
STRUCTURAL_EDGE_TYPES = frozenset(
    {
        "CONTAINS_FILE",
        "CONTAINS_PROJECT",
        "DECLARES_BUILD_CONFIG",
        "DECLARES_CONFIG",
        "DECLARES_CONFIG_FILE",
        "DECLARES_DEPLOYMENT",
        "DECLARES_INGRESS",
        "DECLARES_JOB",
        "DECLARES_PACKAGE",
        "DECLARES_ROUTE",
        "DECLARES_SERVICE",
        "DECLARES_SOLUTION",
        "DECLARES_SYMBOL",
        "DECLARES_WORKSPACE",
        "DEFINES",
        "EXPOSES_ROUTE",
        "RUNS_CONTAINER",
    }
)
IMPACT_PROFILES = {
    "all": None,
    "impact": IMPACT_EDGE_TYPES,
    "structural": STRUCTURAL_EDGE_TYPES,
}
IMPACT_PROFILE_DESCRIPTIONS = {
    "all": "Traverse all edge types.",
    "impact": "Traverse dependency and usage edges for refactor blast-radius analysis.",
    "structural": "Traverse containment and declaration edges.",
}
