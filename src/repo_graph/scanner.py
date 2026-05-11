"""Repository scanners for RepoGraph."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

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
NEST_ROUTE_RE = re.compile(
    r"@(Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*(?:[\"']([^\"']+)[\"'])?",
    re.IGNORECASE,
)
EXPORT_FUNCTION_RE = re.compile(r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")
EXPORT_CLASS_RE = re.compile(r"\bexport\s+class\s+([A-Za-z_$][\w$]*)")
EXPORT_CONST_RE = re.compile(
    r"\bexport\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)?\s*=>"
)
FETCH_RE = re.compile(r"\bfetch\s*\(\s*([\"'`])([^\"'`]+)\1(?P<args>[^)]*)", re.IGNORECASE)
AXIOS_RE = re.compile(
    r"\baxios\.(get|post|put|patch|delete|head|options)\s*\(\s*([\"'`])([^\"'`]+)\2",
    re.IGNORECASE,
)
ENV_URL_RE = re.compile(r"(?:process\.env\.|import\.meta\.env\.)([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))")
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


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    path: Path
    entity: Entity


@dataclass(frozen=True)
class FileScanContext:
    source: ResolvedSource
    repo_entity: Entity
    file_entity: Entity
    file_path: Path
    rel_path: str
    project: ProjectInfo | None = None


class FileExtractor(Protocol):
    name: str

    def can_process(self, rel_path: str) -> bool:
        """Return whether this extractor can scan a relative file path."""
        ...

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        """Extract entities and edges from a file."""
        ...


def build_graph(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
    strict: bool = False,
) -> Graph:
    sources = sync_sources(config) if sync_first else resolve_sources(config)
    graph = Graph(scope_name=config.name, sources=[source_to_dict(source) for source in sources])
    extractors = default_extractors()
    for source in sources:
        scan_source(config, graph, source, max_file_bytes=max_file_bytes, extractors=extractors)
    if strict and graph.errors:
        error_summary = "; ".join(graph.errors[:5])
        raise RuntimeError(f"Graph build failed with {len(graph.errors)} scanner errors: {error_summary}")
    graph.resolve_edges()
    return graph


def default_extractors() -> list[FileExtractor]:
    return [
        PackageJsonExtractor(),
        JavaScriptExtractor(),
        SqlExtractor(),
        SqlReferenceExtractor(),
    ]


def scan_source(
    config: RepoGraphConfig,
    graph: Graph,
    source: ResolvedSource,
    max_file_bytes: int,
    extractors: Sequence[FileExtractor] | None = None,
) -> None:
    if not source.path.exists():
        graph.errors.append(f"Missing source path: {source.path}")
        return

    repo_entity = graph.add_entity(repository_entity(source))
    projects = discover_projects(source, repo_entity)
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
        scan_file_path(graph, source, repo_entity, projects, file_path, extractors or default_extractors())


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


def discover_projects(source: ResolvedSource, repo_entity: Entity) -> list[ProjectInfo]:
    root_package = read_json_object(source.path / "package.json")
    workspace_dirs = discover_workspace_dirs(source.path, root_package or {})
    projects: list[ProjectInfo] = []

    if root_package:
        root_name = string_value(root_package.get("name")) or source.name
        projects.append(project_info(source, repo_entity, root_name, source.path, root_package, "root"))

    for workspace_dir in workspace_dirs:
        package = read_json_object(workspace_dir / "package.json") or {}
        name = string_value(package.get("name")) or workspace_dir.name
        projects.append(project_info(source, repo_entity, name, workspace_dir, package, "workspace"))

    return dedupe_projects(projects)


def project_info(
    source: ResolvedSource,
    repo_entity: Entity,
    name: str,
    path: Path,
    package: dict[str, Any],
    project_type: str,
) -> ProjectInfo:
    rel_path = safe_relative_path(source.path, path)
    aliases = {name, path.name}
    package_name = string_value(package.get("name"))
    if package_name:
        aliases.add(package_name)
    entity = Entity(
        entity_type="project",
        name=name,
        source_name=source.name,
        aliases=aliases,
        properties={
            "path": rel_path,
            "package_name": package_name,
            "version": package.get("version"),
            "project_type": project_type,
            "repository_entity_id": repo_entity.entity_id,
        },
    )
    return ProjectInfo(name=name, path=path, entity=entity)


def dedupe_projects(projects: list[ProjectInfo]) -> list[ProjectInfo]:
    deduped: dict[Path, ProjectInfo] = {}
    for project in projects:
        deduped[project.path] = project
    return list(deduped.values())


def discover_workspace_dirs(root: Path, package: dict[str, Any]) -> list[Path]:
    raw_workspaces = package.get("workspaces")
    patterns: list[str] = []
    if isinstance(raw_workspaces, list):
        patterns = [item for item in raw_workspaces if isinstance(item, str)]
    elif isinstance(raw_workspaces, dict):
        raw_packages = raw_workspaces.get("packages")
        if isinstance(raw_packages, list):
            patterns = [item for item in raw_packages if isinstance(item, str)]

    dirs: list[Path] = []
    for pattern in patterns:
        if pattern.startswith("!"):
            continue
        for path in root.glob(pattern):
            if path.is_dir() and (path / "package.json").exists():
                dirs.append(path)
    return sorted(set(dirs))


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


def scan_file_content(context: FileScanContext, content: str, extractors: Sequence[FileExtractor]) -> ScanResult:
    result = ScanResult()
    for extractor in extractors:
        if extractor.can_process(context.rel_path):
            try:
                result.extend(extractor.extract(context, content))
            except Exception as exc:
                result.errors.append(f"{extractor.name} failed for {context.source.name}/{context.rel_path}: {exc}")
    return result


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


class PackageJsonExtractor:
    name = "package_json"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "package.json"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            package = json.loads(content)
        except json.JSONDecodeError as exc:
            result.errors.append(f"Invalid package.json {context.source.name}/{context.rel_path}: {exc}")
            return result
        if not isinstance(package, dict):
            result.errors.append(f"Invalid package.json {context.source.name}/{context.rel_path}: root must be object")
            return result

        package_name = string_value(package.get("name"))
        package_entity: Entity | None = None
        if package_name:
            package_entity = Entity(
                entity_type="package",
                name=package_name,
                source_name=context.source.name,
                file_path=context.rel_path,
                aliases={package_name, package_name.removeprefix("@").split("/")[-1]},
                properties={
                    "version": package.get("version"),
                    "private": package.get("private"),
                    "scripts": sorted((package.get("scripts") or {}).keys())
                    if isinstance(package.get("scripts"), dict)
                    else [],
                },
            )
            result.entities.append(package_entity)
            result.edges.append(
                resolved_edge(
                    context.file_entity,
                    package_entity,
                    "DECLARES_PACKAGE",
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
            if context.project:
                result.edges.append(
                    resolved_edge(
                        context.project.entity,
                        package_entity,
                        "DECLARES_PACKAGE",
                        context.source.name,
                        context.rel_path,
                        self.name,
                    )
                )

        dependency_source = package_entity or context.file_entity
        for dependency in package_dependencies(package):
            result.edges.append(
                unresolved_edge(
                    dependency_source,
                    dependency["name"],
                    "DEPENDS_ON_PACKAGE",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    to_type="package",
                    properties={
                        "dependency_type": dependency["dependency_type"],
                        "version": dependency["version"],
                        "raw_target": dependency["name"],
                        "normalized_target": package_root(dependency["name"]),
                    },
                )
            )

        return result


class JavaScriptExtractor:
    name = "javascript"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.edges.extend(import_edges(context, line, line_number))
            result.extend(route_entities_and_edges(context, line, line_number))
            result.extend(export_entities_and_edges(context, line, line_number))
            result.edges.extend(http_call_edges(context, line, line_number))
        return result


class SqlExtractor:
    name = "sql"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sql"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.extend(sql_definition_entities_and_edges(context, line, line_number))
        result.extend(scan_sql_references(context, content))
        return result


class SqlReferenceExtractor:
    name = "sql_reference"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".cs", ".js", ".jsx", ".ts", ".tsx", ".vb"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        return scan_sql_references(context, content)


def package_dependencies(package: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for dependency_type in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = package.get(dependency_type)
        if isinstance(deps, dict):
            for dep_name, version in deps.items():
                if isinstance(dep_name, str):
                    yield {"name": package_root(dep_name), "version": version, "dependency_type": dependency_type}


def import_edges(context: FileScanContext, line: str, line_number: int) -> list[Edge]:
    edges: list[Edge] = []
    for match in IMPORT_RE.finditer(line):
        raw_target = match.group(1)
        target_name = import_target_name(raw_target)
        is_package = not raw_target.startswith(".")
        edges.append(
            unresolved_edge(
                context.file_entity,
                target_name,
                "IMPORTS",
                context.source.name,
                context.rel_path,
                "javascript_import",
                to_type="package" if is_package else "module",
                line_number=line_number,
                properties={
                    "raw_target": raw_target,
                    "normalized_target": target_name,
                    "import_kind": "package" if is_package else "relative",
                },
            )
        )
    return edges


def route_entities_and_edges(context: FileScanContext, line: str, line_number: int) -> ScanResult:
    result = ScanResult()
    for match in ROUTE_RE.finditer(line):
        result.extend(add_route(context, match.group(1).upper(), match.group(2), line_number, "javascript_route"))
    for match in NEST_ROUTE_RE.finditer(line):
        result.extend(add_route(context, match.group(1).upper(), match.group(2) or "/", line_number, "nestjs_route"))
    return result


def add_route(context: FileScanContext, method: str, path: str, line_number: int, parser: str) -> ScanResult:
    result = ScanResult()
    normalized_path = normalize_route_path(path)
    route_entity = Entity(
        entity_type="api_route",
        name=f"{method} {path}",
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases={f"{method} {normalized_path}", normalized_path, path},
        properties={
            "method": method,
            "path": path,
            "normalized_path": normalized_path,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(route_entity)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            route_entity,
            "DECLARES_ROUTE",
            context.source.name,
            context.rel_path,
            parser,
            line_number,
        )
    )
    if context.project:
        result.edges.append(
            resolved_edge(
                context.project.entity,
                route_entity,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                parser,
                line_number,
            )
        )
    return result


def export_entities_and_edges(context: FileScanContext, line: str, line_number: int) -> ScanResult:
    result = ScanResult()
    for entity_type, name in exported_symbols(line):
        symbol = Entity(
            entity_type=entity_type,
            name=name,
            source_name=context.source.name,
            file_path=context.rel_path,
            line_number=line_number,
            aliases={name},
            properties={"project": context.project.name if context.project else None},
        )
        result.entities.append(symbol)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                symbol,
                "DECLARES_SYMBOL",
                context.source.name,
                context.rel_path,
                "javascript_export",
                line_number,
            )
        )
    return result


def exported_symbols(line: str) -> Iterable[tuple[str, str]]:
    for match in EXPORT_FUNCTION_RE.finditer(line):
        yield "function", match.group(1)
    for match in EXPORT_CLASS_RE.finditer(line):
        yield "class", match.group(1)
    for match in EXPORT_CONST_RE.finditer(line):
        yield "function", match.group(1)


def http_call_edges(context: FileScanContext, line: str, line_number: int) -> list[Edge]:
    edges: list[Edge] = []
    for match in FETCH_RE.finditer(line):
        method = fetch_method(match.group("args"))
        edges.extend(http_edges_for_target(context, method, match.group(2), line_number, "javascript_http"))
    for match in AXIOS_RE.finditer(line):
        edges.extend(http_edges_for_target(context, match.group(1).upper(), match.group(3), line_number, "axios_http"))
    return edges


def http_edges_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str,
    line_number: int,
    parser: str,
) -> list[Edge]:
    target = http_target(raw_target, method)
    if target["service_name"]:
        return [
            unresolved_edge(
                context.file_entity,
                target["service_name"],
                "CALLS_SERVICE",
                context.source.name,
                context.rel_path,
                parser,
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return [
        unresolved_edge(
            context.file_entity,
            target["route_name"],
            "CALLS_HTTP",
            context.source.name,
            context.rel_path,
            parser,
            to_type="api_route",
            line_number=line_number,
            properties=target,
        )
    ]


def http_target(raw_target: str, method: str) -> dict[str, Any]:
    env_match = ENV_URL_RE.search(raw_target)
    endpoint = extract_endpoint(raw_target)
    normalized_path = normalize_route_path(endpoint or raw_target)
    parsed = urlparse(raw_target)
    host = parsed.netloc or None
    service_name = service_name_from_env(env_match.group(1)) if env_match else None
    return {
        "raw_target": raw_target,
        "normalized_target": f"{method} {normalized_path}",
        "route_name": f"{method} {normalized_path}",
        "http_method": method,
        "target_host": host,
        "target_path": normalized_path,
        "target_env_var": env_match.group(1) if env_match else None,
        "service_name": service_name,
    }


def fetch_method(args: str) -> str:
    match = re.search(r"method\s*:\s*[\"'](get|post|put|patch|delete|head|options)[\"']", args, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "GET"


def extract_endpoint(raw_target: str) -> str:
    if raw_target.startswith("${"):
        after_base = raw_target.split("}", 1)[-1]
        if after_base.startswith("/"):
            return after_base
    if "}" in raw_target:
        after_template = raw_target.rsplit("}", 1)[-1]
        if after_template.startswith("/"):
            return after_template
    parsed = urlparse(raw_target)
    if parsed.path:
        return parsed.path
    if raw_target.startswith("/"):
        return raw_target
    return raw_target


def service_name_from_env(env_var: str) -> str:
    name = env_var.lower()
    for suffix in ("_base_url", "_api_url", "_url", "_uri", "_endpoint", "_host"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", "-")


def scan_sql_references(context: FileScanContext, content: str) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.edges.extend(sql_call_edges(context, line, line_number))
        result.edges.extend(sql_object_reference_edges(context, line, line_number))
    return result


def sql_definition_entities_and_edges(context: FileScanContext, line: str, line_number: int) -> ScanResult:
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
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases={short_name},
        properties={"schema": schema, "full_name": name, "project": context.project.name if context.project else None},
    )
    result.entities.append(entity)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            entity,
            "DEFINES",
            context.source.name,
            context.rel_path,
            "sql",
            line_number,
        )
    )
    return result


def sql_call_edges(context: FileScanContext, line: str, line_number: int) -> list[Edge]:
    return [
        unresolved_edge(
            context.file_entity,
            normalize_sql_name(match.group(1)),
            "CALLS_SQL",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="stored_procedure",
            line_number=line_number,
            properties={
                "raw_target": match.group(1),
                "normalized_target": normalize_sql_name(match.group(1)),
            },
        )
        for match in SQL_EXEC_RE.finditer(line)
    ]


def sql_object_reference_edges(context: FileScanContext, line: str, line_number: int) -> list[Edge]:
    return [
        unresolved_edge(
            context.file_entity,
            normalize_sql_name(match.group(1)),
            "READS_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties={
                "raw_target": match.group(1),
                "normalized_target": normalize_sql_name(match.group(1)),
            },
        )
        for match in SQL_TABLE_REF_RE.finditer(line)
    ]


def resolved_edge(
    from_entity: Entity,
    to_entity: Entity,
    edge_type: str,
    source_name: str,
    file_path: str | None = None,
    parser: str = "unknown",
    line_number: int | None = None,
) -> Edge:
    return Edge(
        from_entity_id=from_entity.entity_id,
        from_name=from_entity.name,
        from_type=from_entity.entity_type,
        to_name=to_entity.name,
        to_type=to_entity.entity_type,
        to_entity_id=to_entity.entity_id,
        resolved=True,
        edge_type=edge_type,
        source_name=source_name,
        file_path=file_path,
        line_number=line_number,
        parser=parser,
        confidence="high",
    )


def unresolved_edge(
    from_entity: Entity,
    to_name: str,
    edge_type: str,
    source_name: str,
    file_path: str,
    parser: str,
    to_type: str | None = None,
    line_number: int | None = None,
    properties: dict[str, Any] | None = None,
) -> Edge:
    return Edge(
        from_entity_id=from_entity.entity_id,
        from_name=from_entity.name,
        from_type=from_entity.entity_type,
        to_name=to_name,
        to_type=to_type,
        edge_type=edge_type,
        source_name=source_name,
        file_path=file_path,
        line_number=line_number,
        parser=parser,
        confidence="medium",
        properties=properties or {},
    )


def apply_scan_result(graph: Graph, result: ScanResult) -> None:
    for entity in result.entities:
        graph.add_entity(entity)
    for edge_item in result.edges:
        graph.add_edge(edge_item)
    graph.errors.extend(result.errors)


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


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def package_root(value: str) -> str:
    if value.startswith("@"):
        parts = value.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else value
    return value.split("/")[0]


def import_target_name(raw_target: str) -> str:
    if raw_target.startswith("."):
        return raw_target
    return package_root(raw_target)


def normalize_route_path(value: str) -> str:
    path = extract_endpoint(value)
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"\$\{[^}]+\}", ":param", path)
    path = re.sub(r"\{[^}]+\}", ":param", path)
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        if part.startswith(":") or part.isdigit():
            parts.append(":param")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"


def safe_relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


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
