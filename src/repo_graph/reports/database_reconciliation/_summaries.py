"""Database reconciliation summary and hotspot builders."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import add_if_present, compact_dict, string_value
from repo_graph.reports.database_reconciliation._constants import (
    DATABASE_RECONCILIATION_ACTIONS,
    DATABASE_RECONCILIATION_ORDER,
)


def finalize_database_reconciliation_group(group: Mapping[str, Any]) -> dict[str, Any]:
    classification = string_value(group.get("classification")) or "unknown"
    return compact_dict(
        {
            "classification": classification,
            "classification_reason": database_reconciliation_reason(classification),
            "recommended_action": DATABASE_RECONCILIATION_ACTIONS.get(classification),
            "target_type": group.get("target_type"),
            "target_name": group.get("target_name"),
            "count": group.get("count"),
            "source_names": sorted(group.get("source_names", set())),
            "database_sources": sorted(group.get("database_sources", set())),
            "evidence_types": sorted(group.get("evidence_types", set())),
            "current_database_types": sorted(group.get("current_database_types", set())),
            "examples": group.get("examples"),
        }
    )


def database_reconciliation_reason(classification: str) -> str:
    reasons = {
        "code_only_reference": "Code or source SQL references an object not found in current database metadata.",
        "unresolved_database_reference": "Database metadata references an object outside the loaded metadata scope.",
        "schema_drift": "Source schema evidence and current database metadata disagree on the object type.",
        "migration_only_object": (
            "Historical migration evidence exists, but current database metadata does not show the object."
        ),
        "database_only_object": (
            "Current database metadata shows the object, but code and source schema evidence did not reference it."
        ),
    }
    return reasons.get(classification, "No database reconciliation rule matched this item.")


def database_reconciliation_summary(
    items: list[dict[str, Any]],
    limited_items: list[dict[str, Any]],
    current_entities: list[Mapping[str, Any]],
    code_edges: list[Mapping[str, Any]],
    metadata_edges: list[Mapping[str, Any]],
    database_evidence_present: bool,
) -> dict[str, Any]:
    classification_counts: Counter[str] = Counter()
    classification_group_counts = Counter(item["classification"] for item in items)
    for item in items:
        classification_counts[item["classification"]] += int(item["count"])
    return {
        "current_database_entity_count": len(current_entities),
        "code_sql_reference_count": len(code_edges),
        "database_metadata_edge_count": len(metadata_edges),
        "database_evidence_present": database_evidence_present,
        "group_count": len(items),
        "returned_group_count": len(limited_items),
        "classification_counts": dict(sorted(classification_counts.items())),
        "classification_group_counts": dict(sorted(classification_group_counts.items())),
    }


def database_reconciliation_classification_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        classification = item["classification"]
        group = groups.setdefault(
            classification,
            {
                "classification": classification,
                "recommended_action": DATABASE_RECONCILIATION_ACTIONS.get(classification),
                "count": 0,
                "group_count": 0,
                "source_names": set(),
                "database_sources": set(),
            },
        )
        group["count"] += int(item["count"])
        group["group_count"] += 1
        group["source_names"].update(item.get("source_names", []))
        group["database_sources"].update(item.get("database_sources", []))
    return sorted(
        (
            compact_dict(
                {
                    "classification": group["classification"],
                    "recommended_action": group["recommended_action"],
                    "count": group["count"],
                    "group_count": group["group_count"],
                    "source_names": sorted(group["source_names"]),
                    "database_sources": sorted(group["database_sources"]),
                }
            )
            for group in groups.values()
        ),
        key=lambda group: (database_reconciliation_rank(group["classification"]), -group["count"]),
    )


def database_reconciliation_source_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    hotspots: dict[str, dict[str, Any]] = {}
    for item in items:
        for source_name in (*item.get("source_names", []), *item.get("database_sources", [])):
            hotspot = hotspots.setdefault(
                source_name,
                {"source_name": source_name, "count": 0, "classifications": set(), "target_names": set()},
            )
            hotspot["count"] += int(item["count"])
            add_if_present(hotspot["classifications"], item["classification"])
            add_if_present(hotspot["target_names"], item["target_name"])
    return sorted(
        (
            {
                "source_name": hotspot["source_name"],
                "count": hotspot["count"],
                "classifications": sorted(hotspot["classifications"], key=database_reconciliation_rank),
                "target_names": sorted(hotspot["target_names"]),
            }
            for hotspot in hotspots.values()
        ),
        key=lambda hotspot: (-hotspot["count"], hotspot["source_name"]),
    )[:limit]


def database_reconciliation_target_hotspots(items: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "target_type": item["target_type"],
                "target_name": item["target_name"],
                "count": item["count"],
                "classifications": [item["classification"]],
            }
            for item in items
        ),
        key=lambda hotspot: (-int(hotspot["count"]), hotspot["target_type"], hotspot["target_name"]),
    )[:limit]


def database_reconciliation_rank(classification: str) -> int:
    return DATABASE_RECONCILIATION_ORDER.get(classification, len(DATABASE_RECONCILIATION_ORDER))
