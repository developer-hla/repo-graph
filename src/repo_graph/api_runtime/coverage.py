"""Coverage warning helpers for graph query responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.api_runtime.constants import UNRESOLVED_REPORT_EDGE_LIMIT
from repo_graph.api_runtime.relationships import string_mapping_value
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.reports import unresolved_report_from_items
from repo_graph.storage import list_unresolved_edges
from repo_graph.vocabulary import CLASSIFICATION_COVERAGE_WARNING_RULES, EDGE_TYPE_COVERAGE_WARNING_RULES


def coverage_warnings_for_entity_source(settings: RuntimeSettings, entity: Mapping[str, Any]) -> dict[str, Any]:
    source_name = string_mapping_value(entity, "source_name")
    if not source_name:
        return {
            "source_name": None,
            "status": "unknown",
            "unresolved_edge_count": 0,
            "warnings": [
                {
                    "code": "source_unknown",
                    "message": "Coverage could not be checked because this entity has no source.",
                    "severity": "info",
                }
            ],
        }

    items = list_unresolved_edges(
        settings.neo4j_settings(),
        source_name=source_name,
        edge_type=None,
        limit=UNRESOLVED_REPORT_EDGE_LIMIT,
    )
    report = unresolved_report_from_items(
        items,
        source_name=source_name,
        edge_type=None,
        group_limit=25,
        examples_per_group=1,
    )
    warnings = coverage_warnings_from_report(report)
    return {
        "source_name": source_name,
        "status": "warning" if warnings else "ok",
        "unresolved_edge_count": report.get("summary", {}).get("unresolved_edge_count", 0),
        "edge_sample_limit": UNRESOLVED_REPORT_EDGE_LIMIT,
        "edge_sample_truncated": len(items) >= UNRESOLVED_REPORT_EDGE_LIMIT,
        "warnings": warnings,
    }


def coverage_warnings_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    groups = report.get("items", [])
    if not isinstance(groups, list):
        return warnings
    warnings.extend(coverage_edge_type_warnings(groups))
    warnings.extend(coverage_classification_warnings(report))
    warnings.sort(key=lambda item: (coverage_severity_rank(item["severity"]), -item["count"], item["code"]))
    return warnings[:8]


def coverage_edge_type_warnings(groups: list[Any]) -> list[dict[str, Any]]:
    edge_counts: dict[str, int] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        edge_type = string_mapping_value(group, "edge_type")
        if not edge_type:
            continue
        edge_counts[edge_type] = edge_counts.get(edge_type, 0) + int(group.get("count") or 0)

    return [
        coverage_warning(rule.code, rule.message, count, rule.severity, edge_type=rule.target)
        for rule in EDGE_TYPE_COVERAGE_WARNING_RULES
        if (count := edge_counts.get(rule.target, 0)) > 0
    ]


def coverage_classification_warnings(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        return []
    classification_counts = summary.get("classification_edge_counts", {})
    if not isinstance(classification_counts, Mapping):
        return []
    return [
        coverage_warning(rule.code, rule.message, count, rule.severity, classification=rule.target)
        for rule in CLASSIFICATION_COVERAGE_WARNING_RULES
        if (count := int(classification_counts.get(rule.target) or 0)) > 0
    ]


def coverage_warning(
    code: str,
    message: str,
    count: int,
    severity: str,
    edge_type: str | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "count": count,
        "severity": severity,
        "edge_type": edge_type,
        "classification": classification,
    }


def coverage_severity_rank(severity: str) -> int:
    return {"warning": 0, "info": 1}.get(severity, 2)


__all__ = [
    "coverage_classification_warnings",
    "coverage_edge_type_warnings",
    "coverage_severity_rank",
    "coverage_warning",
    "coverage_warnings_for_entity_source",
    "coverage_warnings_from_report",
]
