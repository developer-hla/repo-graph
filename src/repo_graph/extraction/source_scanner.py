"""Source-level scanner invocation."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.contracts import FileExtractor, FileScanContext, ProjectInfo, ScanResult
from repo_graph.extraction.legacy_graph_helpers import resolved_edge
from repo_graph.extraction.project_discovery import discover_projects
from repo_graph.extraction.scanners.common import safe_relative_path
from repo_graph.extraction.scanners.manifest_helpers import is_scannable_file
from repo_graph.graph import Entity, Graph
from repo_graph.graph.builder import add_facts_to_graph
from repo_graph.sources import ResolvedSource
from repo_graph.validation import positive_int


def source_to_dict(source: ResolvedSource) -> dict[str, str | None]:
    return {
        "name": source.name,
        "type": source.source_type,
        "path": str(source.path),
        "url": source.url,
        "ref": source.ref,
        "commit": source.commit,
    }


def scan_file_content(context: FileScanContext, content: str, extractors: Sequence[FileExtractor]) -> ScanResult:
    result = ScanResult()
    for extractor in extractors:
        if extractor.can_process(context.rel_path):
            try:
                result.extend(extractor.extract(context, content))
            except Exception as exc:
                result.errors.append(f"{extractor.name} failed for {context.source.name}/{context.rel_path}: {exc}")
    return result


def scan_source(
    config: RepoGraphConfig,
    graph: Graph,
    source: ResolvedSource,
    max_file_bytes: int,
    extractors: Sequence[FileExtractor],
) -> None:
    if not source.path.exists():
        graph.errors.append(f"Missing source path: {source.path}")
        return

    repo_entity = graph.add_entity(repository_entity(source))
    projects = discover_projects(config, source, repo_entity)
    for project in projects:
        graph.add_entity(project.entity)
        graph.add_edge(
            resolved_edge(
                repo_entity,
                project.entity,
                "CONTAINS_PROJECT",
                source.name,
                parser="project_discovery",
            )
        )

    for file_path in iter_scannable_files(config, source.path, max_file_bytes=max_file_bytes):
        scan_file_path(graph, source, repo_entity, projects, file_path, extractors)


def scan_file_path(
    graph: Graph,
    source: ResolvedSource,
    repo_entity: Entity,
    projects: Sequence[ProjectInfo],
    file_path: Path,
    extractors: Sequence[FileExtractor],
) -> None:
    rel_path = safe_relative_path(source.path, file_path)
    project = project_for_file(projects, file_path)
    file_entity = graph.add_entity(
        Entity(
            entity_type="file",
            name=rel_path,
            source_name=source.name,
            file_path=rel_path,
            properties={
                "extension": file_path.suffix.lower(),
                "project": project.name if project else None,
            },
        )
    )
    graph.add_edge(resolved_edge(repo_entity, file_entity, "CONTAINS_FILE", source.name, rel_path, "filesystem"))
    if project:
        graph.add_edge(resolved_edge(project.entity, file_entity, "CONTAINS_FILE", source.name, rel_path, "filesystem"))
    graph.files_scanned += 1

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        graph.errors.append(f"Could not read {file_path}: {exc}")
        return

    context = FileScanContext(source, repo_entity, file_entity, file_path, rel_path, project)
    result = scan_file_content(context, content, extractors)
    apply_scan_result(graph, result)


def project_for_file(projects: Sequence[ProjectInfo], file_path: Path) -> ProjectInfo | None:
    matches: list[ProjectInfo] = []
    for project in projects:
        try:
            file_path.relative_to(project.path)
        except ValueError:
            continue
        matches.append(project)
    if not matches:
        return None
    return max(matches, key=lambda project: len(project.path.parts))


def iter_scannable_files(config: RepoGraphConfig, root: Path, max_file_bytes: int) -> Iterable[Path]:
    max_file_bytes = positive_int(max_file_bytes, "max_file_bytes")
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in config.exclude.directories and not dirname.startswith(".")
        ]
        for filename in filenames:
            if filename in config.exclude.files:
                continue
            file_path = current / filename
            if not is_scannable_file(config, file_path):
                continue
            try:
                if file_path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield file_path


def apply_scan_result(graph: Graph, result: ScanResult) -> None:
    for entity in result.entities:
        graph.add_entity(entity)
    for edge_item in result.edges:
        graph.add_edge(edge_item)
    add_facts_to_graph(graph, result.facts)
    graph.errors.extend(result.errors)


def repository_entity(source: ResolvedSource) -> Entity:
    aliases = {source.name}
    if source.url:
        aliases.add(Path(source.url.rstrip("/").removesuffix(".git")).name)
    return Entity(
        entity_type="repository",
        name=source.name,
        source_name=source.name,
        aliases=aliases,
        properties={
            "path": str(source.path),
            "url": source.url,
            "ref": source.ref,
            "commit": source.commit,
        },
    )
