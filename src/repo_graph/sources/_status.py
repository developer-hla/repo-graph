"""Source inspection and status payload helpers."""

from __future__ import annotations

import os
from typing import Any

from repo_graph.config import RepoGraphConfig, Source
from repo_graph.database import (
    POSTGRES_ENGINE,
    SQLSERVER_ENGINE,
    normalize_database_engine,
    postgres_driver_available,
    sqlserver_driver_available,
)
from repo_graph.sources._expansion import expand_one_source
from repo_graph.sources._git import git_commit, git_repo_present, safe_git_origin_url
from repo_graph.sources._paths import source_path
from repo_graph.sources._sync import sync_one_source


def config_summary(config: RepoGraphConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "config_path": str(config.config_path),
        "cache_dir": str(config.cache_dir),
        "output_dir": str(config.output_dir),
        "source_count": len(config.sources),
        "include": {"file_extensions": sorted(config.include.file_extensions)},
        "exclude": {
            "directories": sorted(config.exclude.directories),
            "files": sorted(config.exclude.files),
        },
        "dependency_filter": {
            "package_include_patterns": list(config.dependency_filter.package_include_patterns),
            "package_exclude_patterns": list(config.dependency_filter.package_exclude_patterns),
            "include_relative_imports": config.dependency_filter.include_relative_imports,
        },
    }


def inspect_sources(config: RepoGraphConfig) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for source in config.sources:
        try:
            statuses.extend(source_status(config, expanded_source) for expanded_source in expand_one_source(source))
        except Exception as exc:
            statuses.append(source_expansion_failure_status(source, exc))
    return statuses


def sync_sources_with_status(config: RepoGraphConfig) -> list[dict[str, Any]]:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    for source in config.sources:
        try:
            expanded_sources = expand_one_source(source)
        except Exception as exc:
            status = source_expansion_failure_status(source, exc)
            status["sync"] = {"status": "failed", "error": str(exc)}
            statuses.append(status)
            continue
        for expanded_source in expanded_sources:
            if expanded_source.source_type == "database":
                status = source_status(config, expanded_source)
                status["sync"] = {"status": "skipped", "reason": "not_applicable"}
                statuses.append(status)
                continue
            try:
                sync_one_source(config, expanded_source)
            except Exception as exc:
                status = source_status(config, expanded_source)
                status["sync"] = {"status": "failed", "error": str(exc)}
                statuses.append(status)
                continue
            status = source_status(config, expanded_source)
            status["sync"] = {"status": "succeeded"}
            statuses.append(status)
    return statuses


def source_status(config: RepoGraphConfig, source: Source) -> dict[str, Any]:
    path = source_path(config, source)
    status: dict[str, Any] = {
        "name": source.name,
        "type": source.source_type,
        "ref": source.ref,
        "configured": configured_source_payload(source),
        "resolved_path": str(path) if path is not None else None,
        "exists": path.exists() if path is not None else False,
        "git_repo_present": git_repo_present(path),
        "current_commit": git_commit(path) if path is not None else None,
    }
    if source.url is not None:
        status["url"] = source.url
    if path is not None and git_repo_present(path):
        status["origin_url"] = safe_git_origin_url(path)
    status["ready"] = source_ready(status, source)
    status["problems"] = source_problems(status, source)
    return status


def configured_source_payload(source: Source) -> dict[str, Any]:
    payload = {
        "path": str(source.path) if source.path is not None else None,
        "url": source.url,
        "ref": source.ref,
    }
    if source.source_type == "github_org":
        payload.update(
            {
                "org": source.org,
                "visibility": source.visibility,
                "include_archived": source.include_archived,
                "include_forks": source.include_forks,
                "include_name_patterns": list(source.include_name_patterns),
                "exclude_name_patterns": list(source.exclude_name_patterns),
                "limit": source.limit,
            }
        )
    if source.source_type == "database":
        payload.update(
            {
                "engine": source.engine,
                "connection_env": source.connection_env,
                "schemas": list(source.schemas),
                "include_object_types": list(source.include_object_types),
                "query_timeout_seconds": source.query_timeout_seconds,
                "max_metadata_rows": source.max_metadata_rows,
            }
        )
    return payload


def source_ready(status: dict[str, Any], source: Source) -> bool:
    if source.source_type == "database":
        return not database_source_problems(source)
    if source.source_type == "local_path":
        return bool(status["exists"])
    if source.source_type == "git":
        return bool(status["exists"] and status["git_repo_present"] and status.get("current_commit"))
    return False


def source_problems(status: dict[str, Any], source: Source) -> list[str]:
    problems: list[str] = []
    if source.source_type == "database":
        return database_source_problems(source)
    if not status["exists"]:
        problems.append("path_missing")
    if source.source_type == "git":
        if status["exists"] and not status["git_repo_present"]:
            problems.append("path_exists_but_not_git_repo")
        if source.url and status.get("origin_url") and status["origin_url"] != source.url:
            problems.append("origin_url_mismatch")
        if not status.get("current_commit"):
            problems.append("commit_unknown")
    return problems


def database_source_problems(source: Source) -> list[str]:
    problems: list[str] = []
    engine = normalize_database_engine(source.engine) if source.engine else ""
    if engine and engine not in {POSTGRES_ENGINE, SQLSERVER_ENGINE}:
        problems.append("database_connector_unavailable")
    if not source.connection_env or source.connection_env not in os.environ:
        problems.append("connection_env_missing")
    if engine == SQLSERVER_ENGINE and not sqlserver_driver_available():
        problems.append("database_driver_missing")
    if engine == POSTGRES_ENGINE and not postgres_driver_available():
        problems.append("database_driver_missing")
    return problems


def source_expansion_failure_status(source: Source, exc: Exception) -> dict[str, Any]:
    return {
        "name": source.name,
        "type": source.source_type,
        "ref": source.ref,
        "configured": configured_source_payload(source),
        "resolved_path": None,
        "exists": False,
        "git_repo_present": False,
        "current_commit": None,
        "ready": False,
        "problems": ["source_expansion_failed"],
        "error": str(exc),
    }
