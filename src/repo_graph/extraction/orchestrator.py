"""Extraction orchestration."""

from __future__ import annotations

import re
from dataclasses import replace

from repo_graph.config import RepoGraphConfig, Source
from repo_graph.database import DatabaseGraphFacts, DatabaseSourceRequest, graph_from_database_source
from repo_graph.extraction._scanner_impl import scan_source, source_to_dict
from repo_graph.extraction.registry import default_extractors
from repo_graph.graph import Edge, Graph
from repo_graph.sources import resolve_sources, sync_sources

MAX_FILE_BYTES = 1_000_000


def build_graph(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    strict: bool = False,
) -> Graph:
    scannable_config = config_without_unsupported_sources(config)
    sources = sync_sources(scannable_config) if sync_first else resolve_sources(scannable_config)
    graph = Graph(
        scope_name=config.name,
        sources=[source_to_dict(source) for source in sources] + database_source_dicts(config),
    )
    extractors = default_extractors()
    for source in sources:
        scan_source(config, graph, source, max_file_bytes=max_file_bytes, extractors=extractors)
    scan_database_sources(config, graph)
    if strict and graph.errors:
        error_summary = "; ".join(graph.errors[:5])
        raise RuntimeError(f"Graph build failed with {len(graph.errors)} scanner errors: {error_summary}")
    graph.resolve_edges()
    apply_dependency_filter(graph, config)
    return graph


def config_without_unsupported_sources(config: RepoGraphConfig) -> RepoGraphConfig:
    return replace(config, sources=tuple(source for source in config.sources if source.source_type != "database"))


def database_source_dicts(config: RepoGraphConfig) -> list[dict[str, str | None]]:
    return [database_source_to_dict(source) for source in config.sources if source.source_type == "database"]


def database_source_to_dict(source: Source) -> dict[str, str | None]:
    return {
        "name": source.name,
        "type": source.source_type,
        "path": None,
        "url": None,
        "ref": source.ref,
        "commit": None,
    }


def scan_database_sources(config: RepoGraphConfig, graph: Graph) -> None:
    for source in config.sources:
        if source.source_type == "database":
            add_database_facts(graph, graph_from_database_source(database_source_request(source)))


def add_database_facts(graph: Graph, facts: DatabaseGraphFacts) -> None:
    graph.errors.extend(facts.errors)
    for entity in facts.entities:
        graph.add_entity(entity)
    for edge in facts.edges:
        graph.add_edge(edge)


def database_source_request(source: Source) -> DatabaseSourceRequest:
    return DatabaseSourceRequest(
        source_name=source.name,
        engine=source.engine or "",
        connection_env=source.connection_env or "",
        schemas=source.schemas,
        include_object_types=source.include_object_types,
        query_timeout_seconds=source.query_timeout_seconds,
        max_metadata_rows=source.max_metadata_rows,
    )


def apply_dependency_filter(graph: Graph, config: RepoGraphConfig) -> None:
    dependency_filter = config.dependency_filter
    if (
        not dependency_filter.package_include_patterns
        and not dependency_filter.package_exclude_patterns
        and dependency_filter.include_relative_imports
    ):
        return

    graph.edges = {edge_id: edge for edge_id, edge in graph.edges.items() if keep_dependency_edge(edge, config)}


def keep_dependency_edge(edge: Edge, config: RepoGraphConfig) -> bool:
    if edge.edge_type == "IMPORTS" and edge.properties.get("import_kind") == "relative":
        return config.dependency_filter.include_relative_imports
    if edge.edge_type not in {"DEPENDS_ON_PACKAGE", "IMPORTS"}:
        return True
    if edge.edge_type == "IMPORTS" and edge.to_type != "package":
        return True
    if package_reference_matches(edge, config.dependency_filter.package_exclude_patterns):
        return False
    if edge.resolved:
        return True
    include_patterns = config.dependency_filter.package_include_patterns
    return not include_patterns or package_reference_matches(edge, include_patterns)


def package_reference_matches(edge: Edge, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    candidates = package_reference_candidates(edge)
    return any(re.search(pattern, candidate) for pattern in patterns for candidate in candidates)


def package_reference_candidates(edge: Edge) -> tuple[str, ...]:
    candidates = [edge.to_name]
    for key in ("raw_target", "normalized_target"):
        value = edge.properties.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    return tuple(dict.fromkeys(candidates))
