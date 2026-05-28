"""Public unresolved-reference report API."""

from __future__ import annotations

from repo_graph.reports.unresolved._builder import (
    unresolved_report,
    unresolved_report_from_graph,
    unresolved_report_from_items,
)

__all__ = [
    "unresolved_report",
    "unresolved_report_from_graph",
    "unresolved_report_from_items",
]
