"""Unresolved-reference classification rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import mapping_value, string_value
from repo_graph.vocabulary import (
    CLASSIFICATION_ACTIONS,
    CLASSIFICATION_ORDER,
    LOCAL_EDGE_PREFIXES,
    MISSING_SOURCE_EDGE_TYPES,
    MISSING_SOURCE_TARGET_TYPES,
    PARSER_GAP_EDGE_TYPES,
    PARSER_GAP_TARGET_TYPES,
)


def classify_unresolved_edge(edge: Mapping[str, Any]) -> tuple[str, str]:
    properties = mapping_value(edge.get("properties"))
    if properties.get("resolution_status") == "ambiguous" or properties.get("resolution_candidates"):
        return (
            "ambiguous_target",
            "Multiple graph entities matched this reference, so Repo Graph left it unresolved.",
        )

    edge_type = string_value(edge.get("edge_type")) or ""
    target_type = string_value(edge.get("to_type")) or ""
    if edge_type.startswith(LOCAL_EDGE_PREFIXES):
        return (
            "likely_parser_gap",
            "This local declaration or topology edge should usually resolve inside the scanned source.",
        )
    if edge_type in MISSING_SOURCE_EDGE_TYPES or target_type in MISSING_SOURCE_TARGET_TYPES:
        return (
            "likely_missing_source",
            "The target usually resolves when the source set includes the referenced repo, package, service, "
            "or database project.",
        )
    if edge_type in PARSER_GAP_EDGE_TYPES or target_type in PARSER_GAP_TARGET_TYPES:
        return (
            "likely_parser_gap",
            "The target may need broader source scope or deeper parser coverage before it can resolve.",
        )
    return (
        "needs_review",
        "No specific unresolved-edge heuristic matched this reference.",
    )


def recommended_action(classification: str) -> str:
    return CLASSIFICATION_ACTIONS.get(classification, CLASSIFICATION_ACTIONS["needs_review"])


def classification_rank(classification: str) -> int:
    return CLASSIFICATION_ORDER.get(classification, len(CLASSIFICATION_ORDER))
