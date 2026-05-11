"""Repository scanners for RepoGraph."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from repo_graph.config import RepoGraphConfig
from repo_graph.graph import Edge, Entity, Graph
from repo_graph.sources import ResolvedSource, resolve_sources, sync_sources

MAX_FILE_BYTES = 1_000_000

IMPORT_RE = re.compile(
    r"(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+|require\s*\()\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
ROUTE_RE = re.compile(
    r"\b(?:app|router|server|fastify)\s*\.\s*(get|post|put|patch|delete|options|head)\s*\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
SQL_OBJECT_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\s+([\[\]\w.]+)",
    re.IGNORECASE,
)
SQL_OBJECT_KIND_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\b",
    re.IGNORECASE,
)
SQL_EXEC_RE = re.compile(r"\bEXEC(?:UTE)?\s+([\[\]\w.]+)", re.IGNORECASE)
SQL_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([\[\]\w.]+)", re.IGNORECASE)


@dataclass
class ScanResult:
    entities: list[Entity] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: ScanResult) -> None:
        self.entities.extend(other.entities)
        self.edges.extend(other.edges)
        self.errors.extend(other.errors)


def build_graph(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    strict: bool = False,
) -> Graph:
    sources = sync_sources(config) if sync_first else resolve_sources(config)
    graph = Graph(scope_name=config.name, sources=[source_to_dict(source) for source in sources])
    for source in sources:
        scan_source(config, graph, source, max_file_bytes=max_file_bytes)
    if strict and graph.errors:
        error_summary = "; ".join(graph.errors[:5])
        raise RuntimeError(f"Graph build failed with {len(graph.errors)} scanner errors: {error_summary}")
    graph.resolve_edges()
    return graph


def scan_source(config: RepoGraphConfig, graph: Graph, source: ResolvedSource, max_file_bytes: int) -> None:
    if not source.path.exists():
        graph.errors.append(f"Missing source path: {source.path}")
        return

    repo_entity = graph.add_entity(
        Entity(
            entity_type="repository",
            name=source.name,
            source_name=source.name,
            properties={
                "path": str(source.path),
                "url": source.url,
                "ref": source.ref,
                "commit": source.commit,
            },
        )
    )

    for file_path in iter_scannable_files(config, source.path, max_file_bytes=max_file_bytes):
        scan_file_path(graph, source, repo_entity, file_path)


def scan_file_path(graph: Graph, source: ResolvedSource, repo_entity: Entity, file_path: Path) -> None:
    rel_path = str(file_path.relative_to(source.path))
    file_entity = graph.add_entity(
        Entity(
            entity_type="file",
            name=rel_path,
            source_name=source.name,
            file_path=rel_path,
            properties={"extension": file_path.suffix.lower()},
        )
    )
    graph.add_edge(contains_file_edge(repo_entity, file_entity, source.name, rel_path))
    graph.files_scanned += 1

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        graph.errors.append(f"Could not read {file_path}: {exc}")
        return

    apply_scan_result(graph, scan_file_content(source, file_entity, rel_path, content))


def contains_file_edge(repo_entity: Entity, file_entity: Entity, source_name: str, rel_path: str) -> Edge:
    return Edge(
        from_entity_id=repo_entity.entity_id,
        from_name=repo_entity.name,
        from_type=repo_entity.entity_type,
        to_name=file_entity.name,
        to_type=file_entity.entity_type,
        to_entity_id=file_entity.entity_id,
        resolved=True,
        edge_type="CONTAINS_FILE",
        source_name=source_name,
        file_path=rel_path,
        confidence="high",
        parser="filesystem",
    )


def scan_file_content(source: ResolvedSource, file_entity: Entity, rel_path: str, content: str) -> ScanResult:
    result = ScanResult()
    suffix = Path(rel_path).suffix.lower()
    if Path(rel_path).name == "package.json":
        result.extend(scan_package_json(source, file_entity, rel_path, content))
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        result.extend(scan_javascript(source, file_entity, rel_path, content))
    if suffix == ".sql":
        result.extend(scan_sql(source, file_entity, rel_path, content))
    elif suffix in {".cs", ".js", ".jsx", ".ts", ".tsx", ".vb"}:
        result.extend(scan_sql_references(source, file_entity, rel_path, content))
    return result


def scan_package_json(source: ResolvedSource, file_entity: Entity, rel_path: str, content: str) -> ScanResult:
    result = ScanResult()
    try:
        package = json.loads(content)
    except json.JSONDecodeError as exc:
        result.errors.append(f"Invalid package.json {source.name}/{rel_path}: {exc}")
        return result

    package_name = package.get("name")
    if isinstance(package_name, str) and package_name:
        package_entity = Entity(
            entity_type="package",
            name=package_name,
            source_name=source.name,
            file_path=rel_path,
            aliases={package_name},
            properties={"version": package.get("version")},
        )
        result.entities.append(package_entity)
        result.edges.append(
            edge(
                file_entity,
                package_entity.name,
                "DECLARES_PACKAGE",
                source,
                rel_path,
                "package_json",
                "package",
                package_entity.entity_id,
            )
        )

    for dep_name in sorted(iter_package_dependencies(package)):
        result.edges.append(
            edge(file_entity, dep_name, "DEPENDS_ON_PACKAGE", source, rel_path, "package_json", "package")
        )

    return result


def iter_package_dependencies(package: dict[str, object]) -> Iterable[str]:
    for dependency_field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = package.get(dependency_field)
        if isinstance(deps, dict):
            for dep_name in deps:
                if isinstance(dep_name, str):
                    yield dep_name


def scan_javascript(source: ResolvedSource, file_entity: Entity, rel_path: str, content: str) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.edges.extend(import_edges(file_entity, source, rel_path, line, line_number))
        result.extend(route_entities_and_edges(file_entity, source, rel_path, line, line_number))
    return result


def import_edges(
    file_entity: Entity,
    source: ResolvedSource,
    rel_path: str,
    line: str,
    line_number: int,
) -> list[Edge]:
    return [
        edge(
            file_entity,
            match.group(1),
            "IMPORTS",
            source,
            rel_path,
            "javascript",
            "module",
            line_number=line_number,
        )
        for match in IMPORT_RE.finditer(line)
    ]


def route_entities_and_edges(
    file_entity: Entity,
    source: ResolvedSource,
    rel_path: str,
    line: str,
    line_number: int,
) -> ScanResult:
    result = ScanResult()
    for match in ROUTE_RE.finditer(line):
        method = match.group(1).upper()
        path = match.group(2)
        route_entity = Entity(
            entity_type="api_route",
            name=f"{method} {path}",
            source_name=source.name,
            file_path=rel_path,
            line_number=line_number,
            properties={"method": method, "path": path},
        )
        result.entities.append(route_entity)
        result.edges.append(
            edge(
                file_entity,
                route_entity.name,
                "DECLARES_ROUTE",
                source,
                rel_path,
                "javascript",
                "api_route",
                route_entity.entity_id,
                line_number,
            )
        )
    return result


def scan_sql(source: ResolvedSource, file_entity: Entity, rel_path: str, content: str) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.extend(sql_definition_entities_and_edges(file_entity, source, rel_path, line, line_number))

    result.extend(scan_sql_references(source, file_entity, rel_path, content))
    return result


def sql_definition_entities_and_edges(
    file_entity: Entity,
    source: ResolvedSource,
    rel_path: str,
    line: str,
    line_number: int,
) -> ScanResult:
    result = ScanResult()
    kind_match = SQL_OBJECT_KIND_RE.search(line)
    object_match = SQL_OBJECT_RE.search(line)
    if not kind_match or not object_match:
        return result

    entity_type = sql_entity_type(kind_match.group(1))
    name = normalize_sql_name(object_match.group(1))
    schema, short_name = split_schema_name(name)
    entity = Entity(
        entity_type=entity_type,
        name=name,
        source_name=source.name,
        file_path=rel_path,
        line_number=line_number,
        aliases={short_name},
        properties={"schema": schema, "full_name": name},
    )
    result.entities.append(entity)
    result.edges.append(
        edge(
            file_entity,
            entity.name,
            "DEFINES",
            source,
            rel_path,
            "sql",
            entity_type,
            entity.entity_id,
            line_number,
        )
    )
    return result


def scan_sql_references(source: ResolvedSource, file_entity: Entity, rel_path: str, content: str) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.edges.extend(sql_call_edges(file_entity, source, rel_path, line, line_number))
        result.edges.extend(sql_object_reference_edges(file_entity, source, rel_path, line, line_number))
    return result


def sql_call_edges(
    file_entity: Entity,
    source: ResolvedSource,
    rel_path: str,
    line: str,
    line_number: int,
) -> list[Edge]:
    return [
        edge(
            file_entity,
            normalize_sql_name(match.group(1)),
            "CALLS_SQL",
            source,
            rel_path,
            "sql_reference",
            "stored_procedure",
            line_number=line_number,
        )
        for match in SQL_EXEC_RE.finditer(line)
    ]


def sql_object_reference_edges(
    file_entity: Entity,
    source: ResolvedSource,
    rel_path: str,
    line: str,
    line_number: int,
) -> list[Edge]:
    return [
        edge(
            file_entity,
            normalize_sql_name(match.group(1)),
            "READS_SQL_OBJECT",
            source,
            rel_path,
            "sql_reference",
            "sql_object",
            line_number=line_number,
        )
        for match in SQL_TABLE_REF_RE.finditer(line)
    ]


def apply_scan_result(graph: Graph, result: ScanResult) -> None:
    for entity in result.entities:
        graph.add_entity(entity)
    for edge_item in result.edges:
        graph.add_edge(edge_item)
    graph.errors.extend(result.errors)


def edge(
    file_entity: Entity,
    to_name: str,
    edge_type: str,
    source: ResolvedSource,
    rel_path: str,
    parser: str,
    to_type: str | None = None,
    to_entity_id: str | None = None,
    line_number: int | None = None,
) -> Edge:
    return Edge(
        from_entity_id=file_entity.entity_id,
        from_name=file_entity.name,
        from_type=file_entity.entity_type,
        to_name=to_name,
        to_type=to_type,
        to_entity_id=to_entity_id,
        resolved=to_entity_id is not None,
        edge_type=edge_type,
        source_name=source.name,
        file_path=rel_path,
        line_number=line_number,
        parser=parser,
        confidence="high" if to_entity_id else "medium",
    )


def iter_scannable_files(config: RepoGraphConfig, root: Path, max_file_bytes: int) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in config.exclude.directories and not dirname.startswith(".")
        ]
        for filename in filenames:
            if filename in config.exclude.files:
                continue
            file_path = current / filename
            if file_path.suffix.lower() not in config.include.file_extensions:
                continue
            try:
                if file_path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield file_path


def source_to_dict(source: ResolvedSource) -> dict[str, str | None]:
    return {
        "name": source.name,
        "type": source.source_type,
        "path": str(source.path),
        "url": source.url,
        "ref": source.ref,
        "commit": source.commit,
    }


def sql_entity_type(kind: str) -> str:
    normalized = kind.upper()
    if normalized in {"PROCEDURE", "PROC"}:
        return "stored_procedure"
    if normalized == "TABLE":
        return "sql_table"
    if normalized == "VIEW":
        return "sql_view"
    if normalized == "FUNCTION":
        return "sql_function"
    return "sql_object"


def normalize_sql_name(value: str) -> str:
    return value.strip().replace("[", "").replace("]", "")


def split_schema_name(value: str) -> tuple[str | None, str]:
    parts = value.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, value
