"""Canonical graph vocabulary and policy metadata."""

from __future__ import annotations

from dataclasses import dataclass

ENTITY_TYPES = (
    "api_route",
    "build_config",
    "class",
    "config_file",
    "config_value",
    "container",
    "deployment",
    "file",
    "function",
    "ingress",
    "interface",
    "module",
    "package",
    "project",
    "repository",
    "service",
    "solution",
    "sql_function",
    "sql_table",
    "sql_trigger",
    "sql_view",
    "stored_procedure",
    "workspace",
)
EDGE_TARGET_TYPES = tuple(sorted({*ENTITY_TYPES, "sql_object"}))
SQL_ENTITY_TYPES = frozenset({"sql_function", "sql_table", "sql_trigger", "sql_view", "stored_procedure"})

EDGE_TYPES = (
    "CALLS_HTTP",
    "CALLS_SERVICE",
    "CALLS_SQL",
    "CALLS_SYMBOL",
    "CONFIGURES_SERVICE",
    "CONTAINS_FILE",
    "CONTAINS_PROJECT",
    "DECLARES_BUILD_CONFIG",
    "DECLARES_CONFIG",
    "DECLARES_CONFIG_FILE",
    "DECLARES_DEPLOYMENT",
    "DECLARES_INGRESS",
    "DECLARES_PACKAGE",
    "DECLARES_ROUTE",
    "DECLARES_SERVICE",
    "DECLARES_SOLUTION",
    "DECLARES_SYMBOL",
    "DECLARES_WORKSPACE",
    "DEFINES",
    "DEPENDS_ON_PACKAGE",
    "DEPENDS_ON_PROJECT",
    "EXPOSES_ROUTE",
    "HANDLES_ROUTE",
    "IMPORTS",
    "READS_SQL_OBJECT",
    "REFERENCES_SQL_OBJECT",
    "ROUTES_TO_SERVICE",
    "RUNS_CONTAINER",
    "SELECTS_DEPLOYMENT",
    "TRIGGERS_ON_SQL_OBJECT",
    "WRITES_SQL_OBJECT",
)
SQL_EDGE_TYPES = frozenset(
    {"CALLS_SQL", "READS_SQL_OBJECT", "REFERENCES_SQL_OBJECT", "TRIGGERS_ON_SQL_OBJECT", "WRITES_SQL_OBJECT"}
)
INTERACTION_EDGE_TYPES = frozenset(
    {
        "CALLS_HTTP",
        "CALLS_SERVICE",
        "CALLS_SQL",
        "CONFIGURES_SERVICE",
        "READS_SQL_OBJECT",
        "REFERENCES_SQL_OBJECT",
        "ROUTES_TO_SERVICE",
        "TRIGGERS_ON_SQL_OBJECT",
        "WRITES_SQL_OBJECT",
    }
)
INTERACTION_EVIDENCE_KEYS = (
    "target_boundary",
    "dependency_scope",
    "interaction_kind",
)
INTERACTION_TARGET_BOUNDARIES = (
    "application",
    "database",
)
INTERACTION_DEPENDENCY_SCOPES = (
    "configuration",
    "deployment",
    "runtime",
    "schema",
)
INTERACTION_KINDS = (
    "http_call",
    "ingress_route",
    "service_call",
    "service_configuration",
    "sql_reference",
    "sql_schema_reference",
    "sql_trigger",
)

PARSER_IDS = (
    "dotnet_build_config",
    "dotnet_controller_route",
    "dotnet_framework_config",
    "dotnet_http",
    "dotnet_minimal_route",
    "dotnet_project",
    "dotnet_solution",
    "dotnet_symbol",
    "filesystem",
    "javascript_export",
    "javascript_http",
    "javascript_import",
    "javascript_route",
    "kubernetes_container",
    "kubernetes_deployment",
    "kubernetes_env",
    "kubernetes_ingress",
    "kubernetes_ingress_route",
    "kubernetes_selector",
    "kubernetes_service",
    "legacy_dotnet_endpoint",
    "package_json",
    "packages_config",
    "pnpm_workspace",
    "postgres_metadata",
    "project_discovery",
    "pyproject",
    "python_call",
    "python_http",
    "python_import",
    "python_route",
    "python_symbol",
    "requirements",
    "sql",
    "sql_reference",
    "sqlserver_metadata",
    "vb_config_service",
    "vb_contract_route",
    "vb_http",
    "vb_sql_command",
    "vb_symbol",
)

IMPACT_EDGE_TYPES = frozenset(
    {
        "CALLS_HTTP",
        "CALLS_SERVICE",
        "CALLS_SQL",
        "CALLS_SYMBOL",
        "CONFIGURES_SERVICE",
        "DEPENDS_ON_PACKAGE",
        "DEPENDS_ON_PROJECT",
        "HANDLES_ROUTE",
        "IMPORTS",
        "READS_SQL_OBJECT",
        "REFERENCES_SQL_OBJECT",
        "ROUTES_TO_SERVICE",
        "SELECTS_DEPLOYMENT",
        "TRIGGERS_ON_SQL_OBJECT",
        "WRITES_SQL_OBJECT",
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
        "sql_function",
        "sql_object",
        "sql_table",
        "sql_trigger",
        "sql_view",
        "stored_procedure",
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
