"""API manifest and UI shell helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_graph import __version__
from repo_graph.api_runtime.constants import UI_DIR
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.vocabulary import IMPACT_PROFILES


def health_payload() -> dict[str, str]:
    return {
        "service": "repo-graph",
        "status": "ok",
        "version": __version__,
    }


def manifest_payload(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "service": "repo-graph",
        "version": __version__,
        "schema_version": "1",
        "config": {
            "path": str(settings.config_path) if settings.config_path else None,
            "configured": settings.config_path is not None,
        },
        "graph_store": {
            "type": "neo4j",
            "uri": settings.neo4j_uri,
            "user": settings.neo4j_user,
            "database": settings.neo4j_database,
            "configured": settings.neo4j_uri is not None,
        },
        "endpoints": [
            {"method": "GET", "path": "/health", "available": True},
            {"method": "GET", "path": "/ui", "available": True},
            {"method": "GET", "path": "/manifest", "available": True},
            {"method": "GET", "path": "/config", "available": True},
            {"method": "GET", "path": "/sources/configured", "available": True},
            {"method": "POST", "path": "/sync", "available": True},
            {"method": "POST", "path": "/build", "available": True},
            {"method": "POST", "path": "/build-load", "available": True},
            {"method": "POST", "path": "/snapshot/status", "available": True},
            {"method": "POST", "path": "/refresh", "available": True},
            {"method": "POST", "path": "/jobs/sync", "available": True},
            {"method": "POST", "path": "/jobs/build", "available": True},
            {"method": "POST", "path": "/jobs/build-load", "available": True},
            {"method": "POST", "path": "/jobs/snapshot-status", "available": True},
            {"method": "POST", "path": "/jobs/refresh", "available": True},
            {"method": "POST", "path": "/jobs/refresh-changed", "available": True},
            {"method": "GET", "path": "/jobs", "available": True},
            {"method": "GET", "path": "/jobs/{job_id}", "available": True},
            {"method": "POST", "path": "/load", "available": True},
            {"method": "POST", "path": "/query", "available": False},
            {"method": "GET", "path": "/scope", "available": True},
            {"method": "GET", "path": "/sources", "available": True},
            {"method": "GET", "path": "/sources/{source_name}/overview", "available": True},
            {"method": "GET", "path": "/sources/{source_name}/files/snippet", "available": True},
            {"method": "GET", "path": "/stats", "available": True},
            {"method": "GET", "path": "/explore", "available": True},
            {"method": "GET", "path": "/entities/search", "available": True},
            {"method": "GET", "path": "/relationships/search", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}/overview", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}/neighbors", "available": True},
            {"method": "GET", "path": "/entities/{entity_id}/impact", "available": True},
            {"method": "GET", "path": "/edges/unresolved", "available": True},
            {"method": "GET", "path": "/reports/interactions", "available": True},
            {"method": "GET", "path": "/reports/database-reconciliation", "available": True},
            {"method": "GET", "path": "/reports/unresolved", "available": True},
        ],
        "agent_guidance": {
            "purpose": "Discover the local Repo Graph runtime and supported API surface.",
            "query_api_status": "safe read endpoints available",
            "raw_cypher_status": "planned",
            "source_status": "available",
            "source_overview_status": "available",
            "source_snippet_status": "available",
            "sync_status": "available",
            "build_api_status": "available",
            "snapshot_status": "available",
            "refresh_status": "available",
            "refresh_changed_status": "available",
            "job_api_status": "in-memory local runtime only",
            "graph_loader_status": "available",
            "scope_status": "available",
            "explore_status": "available",
            "relationship_search_status": "available",
            "entity_overview_status": "available",
            "impact_status": "available",
            "impact_default_profile": "impact",
            "impact_profiles": sorted(IMPACT_PROFILES),
            "interaction_report_status": "available",
            "database_reconciliation_report_status": "available",
            "unresolved_report_status": "available",
            "ui_status": "available",
        },
    }


def ui_index_path() -> Path:
    return UI_DIR / "index.html"


__all__ = [
    "health_payload",
    "manifest_payload",
    "ui_index_path",
]
