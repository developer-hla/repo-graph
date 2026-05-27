"""Source resolver public API."""

from __future__ import annotations

from repo_graph.sources._models import ResolvedSource
from repo_graph.sources._paths import source_path
from repo_graph.sources._resolution import resolve_sources
from repo_graph.sources._status import config_summary, inspect_sources, sync_sources_with_status
from repo_graph.sources._sync import sync_sources

__all__ = [
    "ResolvedSource",
    "config_summary",
    "inspect_sources",
    "resolve_sources",
    "source_path",
    "sync_sources",
    "sync_sources_with_status",
]
