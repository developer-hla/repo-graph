"""Repository scanners for RepoGraph."""

from __future__ import annotations

import ast
import json
import os
import re
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.contracts import FileExtractor, FileScanContext, ProjectInfo, ScanResult
from repo_graph.extraction.legacy_graph_helpers import interaction_properties, resolved_edge, unresolved_edge
from repo_graph.graph import Edge, Entity, Graph
from repo_graph.sources import ResolvedSource
from repo_graph.validation import positive_int

DOTNET_PROJECT_SUFFIXES = {".csproj", ".fsproj", ".vbproj"}
DOTNET_BUILD_SUFFIXES = {".props", ".targets"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
MANIFEST_FILENAMES = {
    "App.config",
    "Directory.Build.props",
    "Web.config",
    "package.json",
    "packages.config",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "requirements.txt",
}

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
ENV_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))\b")
REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
SLN_PROJECT_RE = re.compile(r'^Project\("[^"]+"\)\s*=\s*"([^"]+)",\s*"([^"]+)"')
CS_ATTRIBUTE_LINE_RE = re.compile(r"^\s*\[(?P<body>.+)\]\s*$")
CS_ATTRIBUTE_ITEM_RE = re.compile(r"(?P<name>[A-Za-z_][\w.]*)(?:Attribute)?\s*(?:\((?P<args>[^)]*)\))?")
CS_NAMESPACE_RE = re.compile(r"^\s*namespace\s+([A-Za-z_][\w.]*)(?:\s*;|\s*\{)?")
CS_TYPE_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial)\s+)*"
    r"(class|record|interface|struct)\s+([A-Za-z_]\w*)"
)
CS_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|async|sealed|new|partial|extern|unsafe)"
    r"\s+)+(?:[\w<>\[\],.?]+\s+)+([A-Za-z_]\w*)\s*(?:<[^>]+>)?\s*\("
)
CS_MINIMAL_ROUTE_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*\.\s*Map(Get|Post|Put|Patch|Delete|Head|Options)\s*\(\s*"
    r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)
CS_HTTP_CALL_RE = re.compile(
    r"\.\s*(Get|Post|Put|Patch|Delete)Async\s*\(\s*(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)
CS_NEW_METHOD_CALL_RE = re.compile(r"\bnew\s+(?P<class>[A-Za-z_]\w*)\s*\([^)]*\)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")
CS_QUALIFIED_METHOD_CALL_RE = re.compile(r"\b(?P<receiver>this|[A-Za-z_]\w*)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(")
CS_DIRECT_METHOD_CALL_RE = re.compile(r"(?<![\.\w])(?P<method>[A-Za-z_]\w*)\s*\(")
VB_ATTRIBUTE_RE = re.compile(r"^\s*<\s*([A-Za-z_][\w.]*)", re.IGNORECASE)
VB_NAMESPACE_RE = re.compile(r"^\s*Namespace\s+([A-Za-z_][\w.]*)", re.IGNORECASE)
VB_TYPE_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Friend|Protected|Partial|MustInherit|NotInheritable)\s+)*"
    r"(Class|Module|Interface)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)
VB_METHOD_RE = re.compile(
    r"^\s*(?:(?:Public|Private|Protected|Friend|Shared|Overrides|Overridable|Async|Static)\s+)*"
    r"(Function|Sub)\s+([A-Za-z_]\w*)",
    re.IGNORECASE,
)
VB_END_METHOD_RE = re.compile(r"^\s*End\s+(Function|Sub)\b", re.IGNORECASE)
VB_CONFIG_SETTING_RE = re.compile(r"ConfigurationManager\.AppSettings\s*\(\s*\"([^\"]+)\"\s*\)", re.IGNORECASE)
VB_COMMAND_TEXT_RE = re.compile(r"\.CommandText\s*=\s*\"([^\"]+)\"", re.IGNORECASE)
VB_SQL_COMMAND_RE = re.compile(r"New\s+SqlCommand\s*\(\s*\"([^\"]+)\"", re.IGNORECASE)
VB_HTTP_LITERAL_RE = re.compile(
    r"(?:WebRequest\.Create|WebClient\(\)\.(?:DownloadString|OpenRead|UploadString)|\.DownloadString|\.OpenRead)"
    r"\s*\(\s*\"([^\"]+)\"",
    re.IGNORECASE,
)
VB_NEW_METHOD_CALL_RE = re.compile(
    r"\bNew\s+(?P<class>[A-Za-z_]\w*)\s*\([^)]*\)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
    re.IGNORECASE,
)
VB_QUALIFIED_METHOD_CALL_RE = re.compile(
    r"\b(?P<receiver>Me|[A-Za-z_]\w*)\s*\.\s*(?P<method>[A-Za-z_]\w*)\s*\(",
    re.IGNORECASE,
)
VB_DIRECT_METHOD_CALL_RE = re.compile(r"(?<![\.\w])(?P<method>[A-Za-z_]\w*)\s*\(", re.IGNORECASE)
SQL_OBJECT_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\s+([\[\]\w.]+)",
    re.IGNORECASE,
)
SQL_OBJECT_KIND_RE = re.compile(
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?(PROCEDURE|PROC|TABLE|VIEW|FUNCTION)\b",
    re.IGNORECASE,
)
SQL_EXEC_RE = re.compile(r"\bEXEC(?:UTE)?\s+([\[\]\w.]+)", re.IGNORECASE)
SQL_READ_REF_RE = re.compile(
    r"\b(?P<operation>FROM|JOIN)\s+(?P<target>[\[\]\w.]+)(?![\w.]|\s+import\b)",
    re.IGNORECASE,
)
SQL_WRITE_REF_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("INSERT", re.compile(r"\bINSERT\s+(?:INTO\s+)?(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("UPDATE", re.compile(r"\bUPDATE\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("DELETE", re.compile(r"\bDELETE\s+FROM\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("MERGE", re.compile(r"\bMERGE\s+(?:INTO\s+)?(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\bTRUNCATE\s+TABLE\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
    ("SELECT_INTO", re.compile(r"\bSELECT\b.*?\bINTO\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)),
)
SQL_SCHEMA_REF_RE = re.compile(r"\bREFERENCES\s+(?P<target>[\[\]\w.]+)(?![\w.])", re.IGNORECASE)
SQL_REFERENCE_STOPWORDS = frozenset(
    {
        "ACTION",
        "AS",
        "CASCADE",
        "DEFAULT",
        "FROM",
        "NO",
        "NULL",
        "ON",
        "OUTPUT",
        "REFERENCES",
        "SELECT",
        "SET",
        "TABLE",
        "VALUES",
        "WHERE",
    }
)
SQL_BATCH_SEPARATOR_RE = re.compile(r"^\s*GO(?:\s+\d+)?\s*;?\s*$", re.IGNORECASE)


def first_entity(result: ScanResult) -> Entity | None:
    return result.entities[0] if result.entities else None


@dataclass(frozen=True)
class CSharpAttribute:
    name: str
    args: str | None
    line_number: int


@dataclass(frozen=True)
class KubernetesService:
    entity: Entity
    selector: dict[str, str]


@dataclass(frozen=True)
class KubernetesDeployment:
    entity: Entity
    pod_labels: dict[str, str]


@dataclass(frozen=True)
class PythonCallableIndex:
    functions: frozenset[str]
    class_methods: dict[str, frozenset[str]]

    def has_function(self, name: str) -> bool:
        return name in self.functions

    def has_method(self, class_name: str, method_name: str) -> bool:
        return method_name in self.class_methods.get(class_name, frozenset())


@dataclass(frozen=True)
class TypeMethodIndex:
    type_methods: dict[str, frozenset[str]]

    def has_method(self, type_name: str | None, method_name: str) -> bool:
        return bool(type_name) and method_name in self.type_methods.get(type_name, frozenset())


@dataclass(frozen=True)
class SymbolCallTarget:
    name: str
    raw_target: str
    call_kind: str
    receiver: str | None = None


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

    if extractors is None:
        from repo_graph.extraction.registry import default_extractors

        extractors = default_extractors()

    for file_path in iter_scannable_files(config, source.path, max_file_bytes=max_file_bytes):
        scan_file_path(graph, source, repo_entity, projects, file_path, extractors)


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


def discover_projects(config: RepoGraphConfig, source: ResolvedSource, repo_entity: Entity) -> list[ProjectInfo]:
    projects: list[ProjectInfo] = []

    for manifest_path in iter_project_manifest_paths(config, source.path):
        project = project_info_for_manifest(source, repo_entity, manifest_path)
        if project:
            projects.append(project)

    return dedupe_projects(projects)


def iter_project_manifest_paths(config: RepoGraphConfig, root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [
            dirname for dirname in dirnames if dirname not in config.exclude.directories and not dirname.startswith(".")
        ]
        for filename in filenames:
            file_path = current / filename
            if is_project_manifest(file_path):
                yield file_path


def project_info_for_manifest(
    source: ResolvedSource,
    repo_entity: Entity,
    manifest_path: Path,
) -> ProjectInfo | None:
    if manifest_path.name == "package.json":
        return javascript_project_info(source, repo_entity, manifest_path)
    if manifest_path.name == "pyproject.toml":
        return python_project_info(source, repo_entity, manifest_path)
    if is_requirements_file(manifest_path) and not (manifest_path.parent / "pyproject.toml").exists():
        return requirements_project_info(source, repo_entity, manifest_path)
    if manifest_path.suffix.lower() in DOTNET_PROJECT_SUFFIXES:
        return dotnet_project_info(source, repo_entity, manifest_path)
    if manifest_path.suffix.lower() == ".sln":
        return dotnet_solution_project_info(source, repo_entity, manifest_path)
    if manifest_path.name in {"App.config", "Web.config", "packages.config"}:
        return None
    return None


def javascript_project_info(source: ResolvedSource, repo_entity: Entity, manifest_path: Path) -> ProjectInfo | None:
    package = read_json_object(manifest_path) or {}
    package_name = string_value(package.get("name"))
    name = package_name or project_name_from_path(source, manifest_path.parent)
    project_type = "javascript_root" if manifest_path.parent == source.path else "javascript_package"
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        project_type,
        "javascript",
        package_name=package_name,
        version=string_value(package.get("version")),
        manifest_path=manifest_path,
        aliases={package_name} if package_name else set(),
    )


def python_project_info(source: ResolvedSource, repo_entity: Entity, manifest_path: Path) -> ProjectInfo | None:
    pyproject = read_toml_object(manifest_path) or {}
    metadata = pyproject_metadata(pyproject)
    name = metadata["name"] or project_name_from_path(source, manifest_path.parent)
    package_name = metadata["name"] or None
    project_aliases = (
        {normalize_python_package_name(package_name), python_import_name(package_name)} if package_name else set()
    )
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "python_project",
        "python",
        package_name=package_name,
        version=metadata["version"],
        manifest_path=manifest_path,
        aliases=project_aliases,
    )


def requirements_project_info(source: ResolvedSource, repo_entity: Entity, manifest_path: Path) -> ProjectInfo:
    name = project_name_from_path(source, manifest_path.parent)
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "python_requirements",
        "python",
        manifest_path=manifest_path,
    )


def dotnet_project_info(source: ResolvedSource, repo_entity: Entity, manifest_path: Path) -> ProjectInfo:
    try:
        content = manifest_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""
    metadata = dotnet_project_metadata(content)
    name = metadata["package_id"] or metadata["assembly_name"] or manifest_path.stem
    aliases = {manifest_path.stem}
    for value in (metadata["package_id"], metadata["assembly_name"], metadata["root_namespace"]):
        if value:
            aliases.add(value)
    return project_info(
        source,
        repo_entity,
        name,
        manifest_path.parent,
        "dotnet_project",
        "dotnet",
        package_name=metadata["package_id"] or metadata["assembly_name"],
        version=metadata["version"],
        manifest_path=manifest_path,
        aliases=aliases,
    )


def dotnet_solution_project_info(source: ResolvedSource, repo_entity: Entity, manifest_path: Path) -> ProjectInfo:
    return project_info(
        source,
        repo_entity,
        manifest_path.stem,
        manifest_path.parent,
        "dotnet_solution",
        "dotnet",
        manifest_path=manifest_path,
        aliases={manifest_path.stem},
    )


def project_info(
    source: ResolvedSource,
    repo_entity: Entity,
    name: str,
    path: Path,
    project_type: str,
    ecosystem: str,
    package_name: str | None = None,
    version: str | None = None,
    manifest_path: Path | None = None,
    aliases: set[str] | None = None,
) -> ProjectInfo:
    rel_path = safe_relative_path(source.path, path)
    manifest_rel_path = safe_relative_path(source.path, manifest_path) if manifest_path else None
    project_aliases = {name, path.name, *(aliases or set())}
    if package_name:
        project_aliases.add(package_name)
    entity = Entity(
        entity_type="project",
        name=name,
        source_name=source.name,
        file_path=manifest_rel_path,
        aliases=project_aliases,
        properties={
            "path": rel_path,
            "manifest_path": manifest_rel_path,
            "package_name": package_name,
            "version": version,
            "ecosystem": ecosystem,
            "project_type": project_type,
            "repository_entity_id": repo_entity.entity_id,
        },
    )
    return ProjectInfo(name=name, path=path, entity=entity, ecosystem=ecosystem)


def dedupe_projects(projects: list[ProjectInfo]) -> list[ProjectInfo]:
    deduped: dict[str, ProjectInfo] = {}
    for project in projects:
        deduped[project.entity.entity_id] = project
    return list(deduped.values())


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

        dependency_source = dependency_source_entity(context, package_entity)
        for dependency in package_dependencies(package):
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "javascript",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )

        return result


class PythonProjectExtractor:
    name = "pyproject"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pyproject.toml"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            pyproject = tomllib.loads(content)
        except tomllib.TOMLDecodeError as exc:
            result.errors.append(f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: {exc}")
            return result
        if not isinstance(pyproject, dict):
            result.errors.append(
                f"Invalid pyproject.toml {context.source.name}/{context.rel_path}: root must be object"
            )
            return result

        metadata = pyproject_metadata(pyproject)
        package_entity = python_package_entity(context, metadata["name"], metadata["version"])
        if package_entity:
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

        dependency_source = dependency_source_entity(context, package_entity)
        for dependency in pyproject_dependencies(pyproject):
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "python",
                    dependency["dependency_type"],
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
        return result


class PythonRequirementsExtractor:
    name = "requirements"

    def can_process(self, rel_path: str) -> bool:
        return is_requirements_file(Path(rel_path))

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        dependency_source = context.project.entity if context.project else context.file_entity
        for line_number, line in enumerate(content.splitlines(), start=1):
            dependency = requirement_dependency(line)
            if not dependency:
                continue
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "python",
                    "requirements",
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                    line_number=line_number,
                )
            )
        return result


class PythonCodeExtractor:
    name = "python"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".py"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            result.errors.append(f"Invalid Python {context.source.name}/{context.rel_path}: {exc}")
            return result

        visitor = PythonAstVisitor(context, python_callable_index(tree))
        visitor.visit(tree)
        return visitor.result


class PythonAstVisitor(ast.NodeVisitor):
    def __init__(self, context: FileScanContext, callable_index: PythonCallableIndex) -> None:
        self.context = context
        self.callable_index = callable_index
        self.result = ScanResult()
        self.class_stack: list[str] = []
        self.function_stack: list[Entity] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.result.edges.append(python_import_edge(self.context, alias.name, 0, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raw_target = "." * node.level + (node.module or "")
        self.result.edges.append(python_import_edge(self.context, raw_target, node.level, node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.result.extend(python_symbol_result(self.context, "class", node.name, node.lineno, self.class_stack))
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_python_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_python_function(node, "async_function")

    def visit_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, symbol_kind: str) -> None:
        symbol_result = python_symbol_result(self.context, symbol_kind, node.name, node.lineno, self.class_stack)
        function_entity = first_entity(symbol_result)
        self.result.extend(symbol_result)
        self.result.extend(
            python_route_result(self.context, node.name, node.decorator_list, node.lineno, function_entity)
        )
        if function_entity:
            self.function_stack.append(function_entity)
        self.generic_visit(node)
        if function_entity:
            self.function_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        self.result.edges.extend(python_http_call_edges(self.context, node))
        self.result.edges.extend(python_sql_call_edges(self.context, node))
        if self.function_stack:
            function_entity = self.function_stack[-1]
            self.result.edges.extend(python_http_call_edges(self.context, node, from_entity=function_entity))
            self.result.edges.extend(python_sql_call_edges(self.context, node, from_entity=function_entity))
            self.result.edges.extend(
                python_symbol_call_edges(
                    self.context,
                    node,
                    from_entity=function_entity,
                    class_stack=self.class_stack,
                    callable_index=self.callable_index,
                )
            )
        self.generic_visit(node)


class PythonCallableCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: set[str] = set()
        self.class_methods: dict[str, set[str]] = {}
        self.class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.visit_python_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_python_function(node)

    def visit_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.class_stack:
            class_name = ".".join(self.class_stack)
            self.class_methods.setdefault(class_name, set()).add(node.name)
            self.generic_visit(node)
            return
        self.functions.add(node.name)
        self.generic_visit(node)


class DotnetProjectExtractor:
    name = "dotnet_project"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in DOTNET_PROJECT_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        if root is None:
            return result

        metadata = dotnet_project_metadata_from_root(root, Path(context.rel_path).stem)
        package_entity = dotnet_package_entity(context, metadata)
        if package_entity:
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

        dependency_source = dependency_source_entity(context, package_entity)
        for dependency in dotnet_package_references(root):
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "dotnet",
                    "PackageReference",
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
        for reference in dotnet_project_references(root):
            result.edges.append(
                unresolved_edge(
                    context.project.entity if context.project else context.file_entity,
                    reference["name"],
                    "DEPENDS_ON_PROJECT",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    to_type="project",
                    properties=reference,
                )
            )
        return result


class DotnetPackagesConfigExtractor:
    name = "packages_config"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "packages.config"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        dependency_source = context.project.entity if context.project else context.file_entity
        config_entity = config_file_entity(context, "packages_config")
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_CONFIG_FILE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for dependency in packages_config_references(root):
            result.edges.append(
                package_dependency_edge(
                    dependency_source,
                    dependency["name"],
                    "dotnet",
                    "packages.config",
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
        return result


class DotnetFrameworkConfigExtractor:
    name = "dotnet_framework_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.suffix.lower() == ".config" and path.name != "packages.config"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        config_entity = config_file_entity(context, "dotnet_framework_config")
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_CONFIG_FILE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for config_value in framework_config_values(context, root):
            result.entities.append(config_value)
            result.edges.append(
                resolved_edge(
                    config_entity,
                    config_value,
                    "DECLARES_CONFIG",
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
            service_edge = config_service_edge(config_value, context, self.name)
            if service_edge:
                result.edges.append(service_edge)
        return result


class DotnetBuildConfigExtractor:
    name = "dotnet_build_config"

    def can_process(self, rel_path: str) -> bool:
        path = Path(rel_path)
        return path.name == "Directory.Build.props" or path.suffix.lower() in DOTNET_BUILD_SUFFIXES

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        root = xml_root(content, context)
        if root is None:
            return result

        config_entity = Entity(
            entity_type="build_config",
            name=Path(context.rel_path).name,
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={Path(context.rel_path).name},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        result.entities.append(config_entity)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                config_entity,
                "DECLARES_BUILD_CONFIG",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for dependency in dotnet_package_references(root):
            result.edges.append(
                package_dependency_edge(
                    config_entity,
                    dependency["name"],
                    "dotnet",
                    "PackageReference",
                    dependency["version"],
                    dependency["raw_target"],
                    context.source.name,
                    context.rel_path,
                    self.name,
                )
            )
        return result


class DotnetSolutionExtractor:
    name = "dotnet_solution"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".sln"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        solution = Entity(
            entity_type="solution",
            name=Path(context.rel_path).stem,
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={Path(context.rel_path).stem},
            properties={
                "ecosystem": "dotnet",
                "path": context.rel_path,
                "project": context.project.name if context.project else None,
            },
        )
        result.entities.append(solution)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                solution,
                "DECLARES_SOLUTION",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        for line_number, line in enumerate(content.splitlines(), start=1):
            reference = solution_project_reference(line)
            if not reference:
                continue
            result.edges.append(
                unresolved_edge(
                    solution,
                    reference["name"],
                    "CONTAINS_PROJECT",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    to_type="project",
                    line_number=line_number,
                    properties=reference,
                )
            )
        return result


class PnpmWorkspaceExtractor:
    name = "pnpm_workspace"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).name == "pnpm-workspace.yaml"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        data = read_yaml_object(content)
        package_patterns = data.get("packages") if data else None
        workspace = Entity(
            entity_type="workspace",
            name=f"{context.source.name} workspace",
            source_name=context.source.name,
            file_path=context.rel_path,
            aliases={context.source.name},
            properties={
                "ecosystem": "javascript",
                "path": context.rel_path,
                "package_patterns": package_patterns if isinstance(package_patterns, list) else [],
            },
        )
        result.entities.append(workspace)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                workspace,
                "DECLARES_WORKSPACE",
                context.source.name,
                context.rel_path,
                self.name,
            )
        )
        return result


class KubernetesManifestExtractor:
    name = "kubernetes"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".yaml", ".yml"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        if "apiVersion:" not in content or "kind:" not in content:
            return result

        try:
            documents = [document for document in yaml.safe_load_all(content) if isinstance(document, dict)]
        except yaml.YAMLError as exc:
            result.errors.append(f"Invalid Kubernetes YAML {context.source.name}/{context.rel_path}: {exc}")
            return result

        services: list[KubernetesService] = []
        deployments: list[KubernetesDeployment] = []
        for document in documents:
            kind = string_value(document.get("kind"))
            if kind == "Service":
                service = kubernetes_service_result(context, document)
                if service:
                    result.extend(service[0])
                    services.append(service[1])
            elif kind == "Deployment":
                deployment = kubernetes_deployment_result(context, document)
                if deployment:
                    result.extend(deployment[0])
                    deployments.append(deployment[1])
            elif kind == "Ingress":
                result.extend(kubernetes_ingress_result(context, document))

        result.edges.extend(kubernetes_selector_edges(context, services, deployments))
        return result


class LegacyDotnetEndpointExtractor:
    name = "legacy_dotnet_endpoint"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".asmx", ".svc"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        suffix = Path(context.rel_path).suffix.lower()
        framework = "asmx" if suffix == ".asmx" else "wcf"
        path = "/" + context.rel_path.replace("\\", "/")
        route = route_entity(context, "POST", path, 1, framework, operation_name=None)
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                self.name,
                1,
            )
        )
        if context.project:
            result.edges.append(
                resolved_edge(
                    context.project.entity,
                    route,
                    "EXPOSES_ROUTE",
                    context.source.name,
                    context.rel_path,
                    self.name,
                    1,
                )
            )
        return result


class CSharpCodeExtractor:
    name = "csharp_code"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".cs"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        method_index = csharp_method_index(content)
        namespace: str | None = None
        current_type: str | None = None
        current_route_prefix: str | None = None
        current_function: Entity | None = None
        current_function_brace_depth = 0
        current_function_seen_body = False
        pending_attributes: list[CSharpAttribute] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            result.extend(csharp_minimal_route_result(context, line, line_number))
            result.edges.extend(csharp_http_call_edges(context, line, line_number))
            if current_function:
                result.edges.extend(csharp_http_call_edges(context, line, line_number, from_entity=current_function))
                result.edges.extend(
                    sql_reference_edges_for_line(context, line, line_number, from_entity=current_function)
                )
                result.edges.extend(
                    csharp_symbol_call_edges(
                        context,
                        line,
                        line_number,
                        from_entity=current_function,
                        current_type=current_type,
                        method_index=method_index,
                    )
                )

            attributes = csharp_attributes(line, line_number)
            if attributes:
                pending_attributes.extend(attributes)
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(
                    line,
                    current_function_brace_depth,
                    current_function_seen_body,
                )
                continue

            namespace_match = CS_NAMESPACE_RE.match(line)
            if namespace_match:
                namespace = namespace_match.group(1)

            type_match = CS_TYPE_RE.match(line)
            if type_match:
                current_function = None
                current_function_brace_depth = 0
                current_function_seen_body = False
                current_type = type_match.group(2)
                current_route_prefix = csharp_route_prefix(pending_attributes, current_type, None)
                result.extend(
                    csharp_symbol_result(
                        context,
                        type_match.group(1).lower(),
                        current_type,
                        namespace,
                        line_number,
                    )
                )
                pending_attributes = []
                continue

            method_match = CS_METHOD_RE.match(line)
            if method_match:
                method_name = method_match.group(1)
                symbol_result = csharp_symbol_result(
                    context,
                    "method",
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = first_entity(symbol_result)
                result.extend(symbol_result)
                result.extend(
                    csharp_controller_route_result(
                        context,
                        method_name,
                        pending_attributes,
                        current_route_prefix,
                        current_type,
                        line_number,
                        current_function,
                    )
                )
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(line, 0, False)
                pending_attributes = []
                continue

            if csharp_should_clear_attributes(line):
                pending_attributes = []
            if current_function:
                current_function_brace_depth, current_function_seen_body = csharp_function_scope_state(
                    line,
                    current_function_brace_depth,
                    current_function_seen_body,
                )
                if current_function_seen_body and current_function_brace_depth <= 0 and "}" in line:
                    current_function = None
                    current_function_brace_depth = 0
                    current_function_seen_body = False

        return result


class VbCodeExtractor:
    name = "vb_code"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() == ".vb"

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        method_index = vb_method_index(content)
        namespace: str | None = None
        current_type: str | None = None
        current_function: Entity | None = None
        pending_attributes: list[str] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            attribute_match = VB_ATTRIBUTE_RE.match(line)
            if attribute_match:
                pending_attributes.append(attribute_match.group(1).lower())
                continue

            namespace_match = VB_NAMESPACE_RE.match(line)
            if namespace_match:
                namespace = namespace_match.group(1)

            type_match = VB_TYPE_RE.match(line)
            if type_match:
                current_type = type_match.group(2)
                current_function = None
                result.extend(
                    vb_symbol_result(context, type_match.group(1).lower(), current_type, namespace, line_number)
                )
                pending_attributes = []
                continue

            method_match = VB_METHOD_RE.match(line)
            if method_match:
                method_name = method_match.group(2)
                symbol_result = vb_symbol_result(
                    context,
                    method_match.group(1).lower(),
                    method_name,
                    namespace,
                    line_number,
                    parent_name=current_type,
                )
                current_function = first_entity(symbol_result)
                result.extend(symbol_result)
                result.extend(
                    vb_contract_route_result(context, method_name, pending_attributes, line_number, current_function)
                )
                pending_attributes = []

            result.edges.extend(vb_service_call_edges(context, line, line_number))
            result.edges.extend(vb_sql_command_edges(context, line, line_number))
            if current_function:
                result.edges.extend(vb_service_call_edges(context, line, line_number, from_entity=current_function))
                result.edges.extend(vb_sql_command_edges(context, line, line_number, from_entity=current_function))
                if not method_match:
                    result.edges.extend(
                        vb_symbol_call_edges(
                            context,
                            line,
                            line_number,
                            from_entity=current_function,
                            current_type=current_type,
                            method_index=method_index,
                        )
                    )

            if not attribute_match and line.strip():
                pending_attributes = []
            if VB_END_METHOD_RE.match(line):
                current_function = None
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
        current_sql_entity: Entity | None = None
        for line_number, line in enumerate(content.splitlines(), start=1):
            if SQL_BATCH_SEPARATOR_RE.match(line):
                current_sql_entity = None
                continue
            definition_result = sql_definition_entities_and_edges(context, line, line_number)
            result.extend(definition_result)
            if definition_result.entities:
                current_sql_entity = definition_result.entities[-1]
            result.edges.extend(sql_call_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(sql_object_read_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(sql_object_write_edges(context, line, line_number, from_entity=current_sql_entity))
            result.edges.extend(
                sql_object_schema_reference_edges(context, line, line_number, from_entity=current_sql_entity)
            )
        return result


class SqlReferenceExtractor:
    name = "sql_reference"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".cs", ".js", ".jsx", ".py", ".ts", ".tsx", ".vb"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        return scan_sql_references(context, content)


def package_dependencies(package: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for dependency_type in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        deps = package.get(dependency_type)
        if isinstance(deps, dict):
            for dep_name, version in deps.items():
                if isinstance(dep_name, str):
                    yield {
                        "name": package_root(dep_name),
                        "version": version if isinstance(version, str) else None,
                        "dependency_type": dependency_type,
                        "raw_target": dep_name,
                    }


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
    route = route_entity(context, method, path, line_number, parser, operation_name=None)
    result.entities.append(route)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            route,
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
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                parser,
                line_number,
            )
        )
    return result


def route_handler_edge(
    context: FileScanContext,
    route: Entity,
    handler: Entity,
    parser: str,
    line_number: int,
) -> Edge:
    return resolved_edge(
        route,
        handler,
        "HANDLES_ROUTE",
        context.source.name,
        context.rel_path,
        parser,
        line_number,
        properties={
            key: value
            for key, value in {
                "route_method": route.properties.get("method"),
                "route_path": route.properties.get("path"),
                "normalized_route_path": route.properties.get("normalized_path"),
                "operation_name": route.properties.get("operation_name"),
                "handler_name": handler.name,
                "handler_type": handler.entity_type,
                "project": route.properties.get("project"),
            }.items()
            if value is not None
        },
    )


def route_entity(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    parser: str,
    operation_name: str | None,
) -> Entity:
    normalized_path = normalize_route_path(path)
    properties = {
        "method": method,
        "path": path,
        "normalized_path": normalized_path,
        "project": context.project.name if context.project else None,
        "parser": parser,
    }
    if operation_name:
        properties["operation_name"] = operation_name
    return Entity(
        entity_type="api_route",
        name=f"{method} {path}",
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases={f"{method} {normalized_path}", normalized_path, path},
        properties=properties,
    )


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
        edges.extend(
            http_edges_for_target(context, method, match.group(2), line_number, "javascript_http", client="fetch")
        )
    for match in AXIOS_RE.finditer(line):
        edges.extend(
            http_edges_for_target(
                context,
                match.group(1).upper(),
                match.group(3),
                line_number,
                "javascript_http",
                client="axios",
            )
        )
    return edges


def http_edges_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str | None = None,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    target = http_target(raw_target, method)
    if client:
        target["client"] = client
    if extra_properties:
        target.update(extra_properties)
    if target.get("service_name"):
        return [
            unresolved_edge(
                source_entity,
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
            source_entity,
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
    env_match = ENV_URL_RE.search(raw_target) or ENV_NAME_RE.search(raw_target)
    endpoint = extract_endpoint(raw_target)
    normalized_path = normalize_route_path(endpoint or raw_target)
    parsed = urlparse(raw_target)
    host = parsed.netloc or None
    service_name = service_name_from_env(env_match.group(1)) if env_match else None
    return interaction_properties(
        "application",
        "runtime",
        "http_call",
        protocol=parsed.scheme if parsed.scheme in {"http", "https"} else "http",
        raw_target=raw_target,
        normalized_target=f"{method} {normalized_path}",
        route_name=f"{method} {normalized_path}",
        http_method=method,
        target_host=host,
        target_path=normalized_path,
        target_env_var=env_match.group(1) if env_match else None,
        service_name=service_name,
    )


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


def scan_sql_references(context: FileScanContext, content: str, from_entity: Entity | None = None) -> ScanResult:
    result = ScanResult()
    for line_number, line in enumerate(content.splitlines(), start=1):
        result.edges.extend(sql_reference_edges_for_line(context, line, line_number, from_entity=from_entity))
    return result


def sql_reference_edges_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    extra_properties = source_context_properties(from_entity)
    return [
        *sql_call_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_read_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_write_edges(context, line, line_number, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_schema_reference_edges(
            context,
            line,
            line_number,
            from_entity=from_entity,
            extra_properties=extra_properties,
        ),
    ]


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
        properties={
            "schema": schema,
            "full_name": name,
            "project": context.project.name if context.project else None,
            **sql_source_provenance(context.rel_path),
        },
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


def sql_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group(1)),
            "CALLS_SQL",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="stored_procedure",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group(1),
                "EXECUTE",
                "stored_procedure",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_EXEC_RE.finditer(line)
    ]


def sql_object_read_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "READS_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                match.group("operation"),
                "sql_object",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_READ_REF_RE.finditer(line)
    ]


def sql_object_write_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "WRITES_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                operation,
                "sql_object",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for operation, match in sql_write_reference_matches(line)
    ]


def sql_object_schema_reference_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    return [
        unresolved_edge(
            source_entity,
            normalize_sql_name(match.group("target")),
            "REFERENCES_SQL_OBJECT",
            context.source.name,
            context.rel_path,
            "sql_reference",
            to_type="sql_object",
            line_number=line_number,
            properties=sql_interaction_properties(
                match.group("target"),
                "REFERENCES",
                "sql_object",
                dependency_scope="schema",
                interaction_kind="sql_schema_reference",
                extra_properties=sql_reference_properties(context, extra_properties),
            ),
        )
        for match in SQL_SCHEMA_REF_RE.finditer(line)
        if sql_reference_target_is_valid(match.group("target"))
    ]


def sql_interaction_properties(
    raw_target: str,
    operation: str,
    database_object_type: str,
    dependency_scope: str = "runtime",
    interaction_kind: str = "sql_reference",
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties = interaction_properties(
        "database",
        dependency_scope,
        interaction_kind,
        protocol="sql",
        raw_target=raw_target,
        normalized_target=normalize_sql_name(raw_target),
        sql_operation=operation.upper(),
        database_object_type=database_object_type,
    )
    if extra_properties:
        properties.update(extra_properties)
    return properties


def sql_write_reference_matches(line: str) -> Iterable[tuple[str, re.Match[str]]]:
    for operation, pattern in SQL_WRITE_REF_PATTERNS:
        for match in pattern.finditer(line):
            if sql_reference_target_is_valid(match.group("target")):
                yield operation, match


def sql_reference_target_is_valid(target: str) -> bool:
    return normalize_sql_name(target).upper() not in SQL_REFERENCE_STOPWORDS


def sql_source_provenance(rel_path: str) -> dict[str, str]:
    path = Path(rel_path)
    lower_parts = {part.lower() for part in path.parts}
    filename = path.name.lower()
    if lower_parts.intersection({"migration", "migrations", "revision", "revisions", "rev", "revs", "alembic"}):
        return {"schema_state": "historical", "sql_source_kind": "migration_file"}
    if lower_parts.intersection({"flyway", "liquibase"}) or re.match(r"v\d+__", filename, re.IGNORECASE):
        return {"schema_state": "historical", "sql_source_kind": "migration_file"}
    if filename in {"schema.sql", "tables.sql", "views.sql", "functions.sql", "procedures.sql"}:
        return {"schema_state": "current_schema", "sql_source_kind": "schema_file"}
    return {"schema_state": "unknown", "sql_source_kind": "sql_file"}


def sql_reference_extra_properties(context: FileScanContext) -> dict[str, str]:
    if Path(context.rel_path).suffix.lower() == ".sql":
        return sql_source_provenance(context.rel_path)
    return {}


def sql_reference_properties(
    context: FileScanContext,
    extra_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    properties: dict[str, Any] = sql_reference_extra_properties(context)
    if extra_properties:
        properties.update(extra_properties)
    return properties


def source_context_properties(from_entity: Entity | None) -> dict[str, str]:
    if not from_entity or from_entity.entity_type == "file":
        return {}
    return {
        "source_context_type": from_entity.entity_type,
        "source_context_name": from_entity.name,
    }


def apply_scan_result(graph: Graph, result: ScanResult) -> None:
    for entity in result.entities:
        graph.add_entity(entity)
    for edge_item in result.edges:
        graph.add_edge(edge_item)
    graph.errors.extend(result.errors)


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


def read_toml_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def read_yaml_object(content: str) -> dict[str, Any] | None:
    data = yaml.safe_load(content) or {}
    return data if isinstance(data, dict) else None


def is_project_manifest(path: Path) -> bool:
    return (
        path.name in MANIFEST_FILENAMES
        or is_requirements_file(path)
        or path.suffix.lower() in DOTNET_PROJECT_SUFFIXES
        or path.suffix.lower() in DOTNET_BUILD_SUFFIXES
        or path.suffix.lower() == ".sln"
    )


def is_requirements_file(path: Path) -> bool:
    return path.name == "requirements.txt" or (path.name.startswith("requirements-") and path.suffix == ".txt")


def is_scannable_file(config: RepoGraphConfig, path: Path) -> bool:
    return path.suffix.lower() in config.include.file_extensions or is_project_manifest(path)


def project_name_from_path(source: ResolvedSource, path: Path) -> str:
    return source.name if path == source.path else path.name


def string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def pyproject_metadata(pyproject: dict[str, Any]) -> dict[str, str | None]:
    project = object_mapping(pyproject.get("project"))
    poetry = object_mapping(object_mapping(pyproject.get("tool")).get("poetry"))
    name = string_value(project.get("name")) or string_value(poetry.get("name"))
    version = string_value(project.get("version")) or string_value(poetry.get("version"))
    return {"name": name, "version": version}


def pyproject_dependencies(pyproject: dict[str, Any]) -> Iterable[dict[str, str | None]]:
    project = object_mapping(pyproject.get("project"))
    raw_dependencies = project.get("dependencies")
    if isinstance(raw_dependencies, list):
        for raw_dependency in raw_dependencies:
            if isinstance(raw_dependency, str):
                dependency = requirement_dependency(raw_dependency)
                if dependency:
                    dependency["dependency_type"] = "project.dependencies"
                    yield dependency

    optional_dependencies = object_mapping(project.get("optional-dependencies"))
    for group_name, dependencies in optional_dependencies.items():
        if not isinstance(dependencies, list):
            continue
        for raw_dependency in dependencies:
            if isinstance(raw_dependency, str):
                dependency = requirement_dependency(raw_dependency)
                if dependency:
                    dependency["dependency_type"] = f"project.optional-dependencies.{group_name}"
                    yield dependency

    poetry = object_mapping(object_mapping(pyproject.get("tool")).get("poetry"))
    for dependency_type, dependencies in poetry_dependency_groups(poetry):
        for package_name, version in dependencies.items():
            if not isinstance(package_name, str) or package_name.lower() == "python":
                continue
            yield {
                "name": normalize_python_package_name(package_name),
                "version": dependency_version(version),
                "dependency_type": dependency_type,
                "raw_target": package_name,
            }


def poetry_dependency_groups(poetry: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    dependencies = object_mapping(poetry.get("dependencies"))
    if dependencies:
        yield "tool.poetry.dependencies", dependencies

    dev_dependencies = object_mapping(poetry.get("dev-dependencies"))
    if dev_dependencies:
        yield "tool.poetry.dev-dependencies", dev_dependencies

    groups = object_mapping(poetry.get("group"))
    for group_name, group_data in groups.items():
        group_dependencies = object_mapping(object_mapping(group_data).get("dependencies"))
        if group_dependencies:
            yield f"tool.poetry.group.{group_name}.dependencies", group_dependencies


def dependency_version(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        version = value.get("version")
        return version if isinstance(version, str) else None
    return None


def requirement_dependency(line: str) -> dict[str, str | None] | None:
    raw_target = line.strip()
    if not raw_target or raw_target.startswith("#") or raw_target.startswith(("-", "--")):
        return None
    raw_target = raw_target.split(" #", 1)[0].strip()
    match = REQUIREMENT_NAME_RE.match(raw_target)
    if not match:
        return None
    name = normalize_python_package_name(match.group(1))
    version = raw_target[match.end() :].strip() or None
    return {
        "name": name,
        "version": version,
        "dependency_type": None,
        "raw_target": raw_target,
    }


def normalize_python_package_name(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def python_package_entity(context: FileScanContext, name: str | None, version: str | None) -> Entity | None:
    if not name:
        return None
    normalized = normalize_python_package_name(name)
    import_name = python_import_name(name)
    return Entity(
        entity_type="package",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={name, normalized, import_name},
        properties={
            "ecosystem": "python",
            "version": version,
            "project": context.project.name if context.project else None,
        },
    )


def python_import_name(value: str) -> str:
    return normalize_python_package_name(value).replace("-", "_")


def python_import_edge(context: FileScanContext, raw_target: str, level: int, line_number: int) -> Edge:
    is_relative = level > 0 or raw_target.startswith(".")
    target_name = raw_target if is_relative else normalize_python_package_name(raw_target.split(".", 1)[0])
    return unresolved_edge(
        context.file_entity,
        target_name,
        "IMPORTS",
        context.source.name,
        context.rel_path,
        "python_import",
        to_type="module" if is_relative else "package",
        line_number=line_number,
        properties={
            "raw_target": raw_target,
            "normalized_target": target_name,
            "import_kind": "relative" if is_relative else "package",
        },
    )


def python_callable_index(tree: ast.AST) -> PythonCallableIndex:
    collector = PythonCallableCollector()
    collector.visit(tree)
    return PythonCallableIndex(
        functions=frozenset(collector.functions),
        class_methods={class_name: frozenset(methods) for class_name, methods in collector.class_methods.items()},
    )


def python_symbol_result(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    line_number: int,
    class_stack: Sequence[str],
) -> ScanResult:
    result = ScanResult()
    module_name = python_module_name(context.rel_path)
    parent_name = ".".join(class_stack) or None
    full_name = ".".join(part for part in (module_name, parent_name, name) if part)
    entity_type = "function" if symbol_kind in {"function", "async_function"} else symbol_kind
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = Entity(
        entity_type=entity_type,
        name=full_name or name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "module": module_name or None,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(symbol)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            symbol,
            "DECLARES_SYMBOL",
            context.source.name,
            context.rel_path,
            "python_symbol",
            line_number,
        )
    )
    return result


def python_module_name(rel_path: str) -> str:
    path = Path(rel_path).with_suffix("")
    parts = list(path.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def python_route_result(
    context: FileScanContext,
    operation_name: str,
    decorators: Sequence[ast.expr],
    line_number: int,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        path = python_string_arg(decorator, 0) or python_keyword_string(decorator, "path")
        if not path:
            continue
        for method in python_route_methods(decorator):
            result.extend(python_add_route(context, method, path, line_number, operation_name, handler))
    return result


def python_route_methods(decorator: ast.Call) -> list[str]:
    callee = python_attribute_name(decorator.func)
    if callee in HTTP_METHODS:
        return [callee.upper()]
    if callee not in {"route", "api_route"}:
        return []
    methods = python_keyword_strings(decorator, "methods")
    return [method.upper() for method in methods] if methods else ["GET"]


def python_add_route(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    operation_name: str,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    route = route_entity(context, method, path, line_number, "python_route", operation_name)
    result.entities.append(route)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            route,
            "DECLARES_ROUTE",
            context.source.name,
            context.rel_path,
            "python_route",
            line_number,
        )
    )
    if context.project:
        result.edges.append(
            resolved_edge(
                context.project.entity,
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                "python_route",
                line_number,
            )
        )
    if handler:
        result.edges.append(route_handler_edge(context, route, handler, "python_route", line_number))
    return result


def python_http_call_edges(
    context: FileScanContext,
    call: ast.Call,
    from_entity: Entity | None = None,
) -> list[Edge]:
    callee = python_attribute_name(call.func)
    root_name = python_call_root_name(call.func)
    if root_name not in {"httpx", "requests"}:
        return []
    if callee in HTTP_METHODS:
        raw_target = python_string_arg(call, 0) or python_keyword_string(call, "url")
        return python_http_edges_for_target(context, callee.upper(), raw_target, call.lineno, root_name, from_entity)
    if callee == "request":
        method = python_string_arg(call, 0) or python_keyword_string(call, "method") or "GET"
        raw_target = python_string_arg(call, 1) or python_keyword_string(call, "url")
        return python_http_edges_for_target(context, method.upper(), raw_target, call.lineno, root_name, from_entity)
    return []


def python_http_edges_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str | None,
    line_number: int,
    client: str,
    from_entity: Entity | None = None,
) -> list[Edge]:
    if not raw_target:
        return []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, method)
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        target.update(extra_properties)
        return [
            unresolved_edge(
                source_entity,
                target["service_name"],
                "CALLS_SERVICE",
                context.source.name,
                context.rel_path,
                "python_http",
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_edges_for_target(
        context,
        method,
        raw_target,
        line_number,
        "python_http",
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
    )


def python_sql_call_edges(
    context: FileScanContext,
    call: ast.Call,
    from_entity: Entity | None = None,
) -> list[Edge]:
    callee = python_attribute_name(call.func)
    if callee not in {"execute", "executemany", "exec_driver_sql", "text"}:
        return []
    raw_sql = python_string_arg(call, 0)
    if not raw_sql:
        return []
    extra_properties = source_context_properties(from_entity)
    return [
        *sql_call_edges(context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties),
        *sql_object_read_edges(
            context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties
        ),
        *sql_object_write_edges(
            context, raw_sql, call.lineno, from_entity=from_entity, extra_properties=extra_properties
        ),
        *sql_object_schema_reference_edges(
            context,
            raw_sql,
            call.lineno,
            from_entity=from_entity,
            extra_properties=extra_properties,
        ),
    ]


def python_symbol_call_edges(
    context: FileScanContext,
    call: ast.Call,
    from_entity: Entity,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> list[Edge]:
    target = python_symbol_call_target(call.func, class_stack, callable_index)
    if not target:
        return []
    return symbol_call_edges(context, from_entity, [target], "python_call", call.lineno)


def python_symbol_call_target(
    func: ast.expr,
    class_stack: Sequence[str],
    callable_index: PythonCallableIndex,
) -> SymbolCallTarget | None:
    if isinstance(func, ast.Name) and callable_index.has_function(func.id):
        return SymbolCallTarget(func.id, func.id, "direct")
    if not isinstance(func, ast.Attribute):
        return None

    receiver = python_call_receiver_name(func.value)
    class_name = python_receiver_class_name(func.value)
    if class_name and callable_index.has_method(class_name, func.attr):
        return SymbolCallTarget(f"{class_name}.{func.attr}", python_call_raw_target(func), "class_method", receiver)
    if receiver in {"self", "cls"} and class_stack:
        current_class = ".".join(class_stack)
        if callable_index.has_method(current_class, func.attr):
            return SymbolCallTarget(
                f"{current_class}.{func.attr}", python_call_raw_target(func), "instance_method", receiver
            )
    return None


def symbol_call_edges(
    context: FileScanContext,
    from_entity: Entity,
    targets: Sequence[SymbolCallTarget],
    parser: str,
    line_number: int,
) -> list[Edge]:
    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (target.name, target.raw_target)
        if key in seen or target.name == from_entity.name or target.name in from_entity.aliases:
            continue
        seen.add(key)
        properties = {
            "raw_target": target.raw_target,
            "normalized_target": target.name,
            "call_kind": target.call_kind,
            **source_context_properties(from_entity),
        }
        if target.receiver:
            properties["receiver"] = target.receiver
        edges.append(
            unresolved_edge(
                from_entity,
                target.name,
                "CALLS_SYMBOL",
                context.source.name,
                context.rel_path,
                parser,
                to_type="function",
                line_number=line_number,
                properties=properties,
            )
        )
    return edges


def python_attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr.lower()
    if isinstance(node, ast.Name):
        return node.id.lower()
    return None


def python_call_root_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return python_call_root_name(node.value)
    if isinstance(node, ast.Call):
        return python_call_root_name(node.func)
    return None


def python_call_receiver_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return python_call_receiver_name(node.func)
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def python_receiver_class_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return python_call_receiver_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return None


def python_call_raw_target(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except ValueError:
        return "unknown"


def python_string_arg(call: ast.Call, index: int) -> str | None:
    if index >= len(call.args):
        return None
    return python_string_value(call.args[index])


def python_keyword_string(call: ast.Call, keyword_name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return python_string_value(keyword.value)
    return None


def python_keyword_strings(call: ast.Call, keyword_name: str) -> list[str]:
    for keyword in call.keywords:
        if keyword.arg == keyword_name:
            return python_string_values(keyword.value)
    return []


def python_string_values(node: ast.AST) -> list[str]:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return [value for item in node.elts if (value := python_string_value(item))]
    value = python_string_value(node)
    return [value] if value else []


def python_string_value(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(python_joined_string_part(value) for value in node.values)
    return None


def python_joined_string_part(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.FormattedValue):
        try:
            return "${" + ast.unparse(node.value).strip() + "}"
        except ValueError:
            return "${expr}"
    return ""


def dotnet_project_metadata(content: str) -> dict[str, str | None]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return dotnet_metadata_defaults()
    return dotnet_project_metadata_from_root(root)


def dotnet_project_metadata_from_root(root: ET.Element, default_name: str | None = None) -> dict[str, str | None]:
    package_id = first_xml_text(root, "PackageId")
    assembly_name = first_xml_text(root, "AssemblyName") or default_name
    root_namespace = first_xml_text(root, "RootNamespace")
    version = first_xml_text(root, "Version")
    return {
        "package_id": package_id,
        "assembly_name": assembly_name,
        "root_namespace": root_namespace,
        "version": version,
        "target_framework": first_xml_text(root, "TargetFramework"),
        "target_frameworks": first_xml_text(root, "TargetFrameworks"),
        "output_type": first_xml_text(root, "OutputType"),
    }


def dotnet_metadata_defaults() -> dict[str, str | None]:
    return {
        "package_id": None,
        "assembly_name": None,
        "root_namespace": None,
        "version": None,
        "target_framework": None,
        "target_frameworks": None,
        "output_type": None,
    }


def dotnet_package_entity(context: FileScanContext, metadata: dict[str, str | None]) -> Entity | None:
    package_name = metadata["package_id"] or metadata["assembly_name"]
    if not package_name:
        return None
    aliases = {package_name}
    if metadata["assembly_name"]:
        aliases.add(metadata["assembly_name"])
    return Entity(
        entity_type="package",
        name=package_name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=aliases,
        properties={
            "ecosystem": "dotnet",
            "version": metadata["version"],
            "target_framework": metadata["target_framework"],
            "target_frameworks": metadata["target_frameworks"],
            "output_type": metadata["output_type"],
            "project": context.project.name if context.project else None,
        },
    )


def dotnet_package_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "PackageReference":
            continue
        package_name = string_value(element.attrib.get("Include")) or string_value(element.attrib.get("Update"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("Version")) or first_child_text(element, "Version"),
            "raw_target": package_name,
        }


def dotnet_project_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "ProjectReference":
            continue
        raw_target = string_value(element.attrib.get("Include"))
        if not raw_target:
            continue
        yield {
            "name": Path(raw_target).stem,
            "raw_target": raw_target,
            "normalized_target": Path(raw_target).stem,
        }


def packages_config_references(root: ET.Element) -> Iterable[dict[str, str | None]]:
    for element in root.iter():
        if xml_local_name(element.tag) != "package":
            continue
        package_name = string_value(element.attrib.get("id"))
        if not package_name:
            continue
        yield {
            "name": package_name,
            "version": string_value(element.attrib.get("version")),
            "raw_target": package_name,
        }


def solution_project_reference(line: str) -> dict[str, str | None] | None:
    match = SLN_PROJECT_RE.match(line)
    if not match:
        return None
    raw_path = match.group(2)
    if Path(raw_path).suffix.lower() not in DOTNET_PROJECT_SUFFIXES:
        return None
    return {
        "name": Path(raw_path).stem,
        "display_name": match.group(1),
        "raw_target": raw_path,
        "normalized_target": Path(raw_path).stem,
    }


def kubernetes_service_result(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[ScanResult, KubernetesService] | None:
    name = kubernetes_resource_name(document)
    if not name:
        return None
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    selector = string_dict(spec.get("selector"))
    service = Entity(
        entity_type="service",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Service",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "selector": selector,
            "ports": kubernetes_service_ports(spec.get("ports")),
            "project": context.project.name if context.project else None,
        },
    )
    result = ScanResult(
        entities=[service],
        edges=[
            resolved_edge(
                context.file_entity,
                service,
                "DECLARES_SERVICE",
                context.source.name,
                context.rel_path,
                "kubernetes_service",
            )
        ],
    )
    return result, KubernetesService(service, selector)


def kubernetes_deployment_result(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[ScanResult, KubernetesDeployment] | None:
    name = kubernetes_resource_name(document)
    if not name:
        return None
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    template = object_mapping(spec.get("template"))
    pod_metadata = object_mapping(template.get("metadata"))
    pod_spec = object_mapping(template.get("spec"))
    namespace = kubernetes_namespace(metadata)
    pod_labels = string_dict(pod_metadata.get("labels"))
    deployment = Entity(
        entity_type="deployment",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Deployment",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "selector": kubernetes_match_labels(spec.get("selector")),
            "pod_labels": pod_labels,
            "replicas": spec.get("replicas"),
            "project": context.project.name if context.project else None,
        },
    )
    result = ScanResult(
        entities=[deployment],
        edges=[
            resolved_edge(
                context.file_entity,
                deployment,
                "DECLARES_DEPLOYMENT",
                context.source.name,
                context.rel_path,
                "kubernetes_deployment",
            )
        ],
    )
    for container in mapping_list(pod_spec.get("containers")):
        result.extend(kubernetes_container_result(context, deployment, namespace, container))
    return result, KubernetesDeployment(deployment, pod_labels)


def kubernetes_container_result(
    context: FileScanContext,
    deployment: Entity,
    namespace: str,
    container: dict[str, Any],
) -> ScanResult:
    result = ScanResult()
    container_name = string_value(container.get("name"))
    if not container_name:
        return result
    image = string_value(container.get("image"))
    container_entity = Entity(
        entity_type="container",
        name=f"{deployment.name}:{container_name}",
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={container_name, *(set() if not image else {image})},
        properties={
            "ecosystem": "kubernetes",
            "namespace": namespace,
            "deployment": deployment.name,
            "image": image,
            "env_names": [
                env_name
                for env in mapping_list(container.get("env"))
                if (env_name := string_value(env.get("name"))) is not None
            ],
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(container_entity)
    result.edges.append(
        resolved_edge(
            deployment,
            container_entity,
            "RUNS_CONTAINER",
            context.source.name,
            context.rel_path,
            "kubernetes_container",
        )
    )
    for env in mapping_list(container.get("env")):
        result.extend(kubernetes_env_result(context, container_entity, deployment.name, env))
    return result


def kubernetes_env_result(
    context: FileScanContext,
    container: Entity,
    deployment_name: str,
    env: dict[str, Any],
) -> ScanResult:
    result = ScanResult()
    env_name = string_value(env.get("name"))
    if not env_name:
        return result
    env_value = string_value(env.get("value"))
    target_url = url_value(env_value)
    config_value = Entity(
        entity_type="config_value",
        name=f"env:{deployment_name}:{container.name.rsplit(':', 1)[-1]}:{env_name}",
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={env_name},
        properties={
            "display_name": env_name,
            "value_kind": "environment_variable",
            "key": env_name,
            "has_value": env_value is not None,
            "target_url": target_url,
            "project": context.project.name if context.project else None,
            "container": container.name,
            "deployment": deployment_name,
        },
    )
    result.entities.append(config_value)
    result.edges.append(
        resolved_edge(
            container,
            config_value,
            "DECLARES_CONFIG",
            context.source.name,
            context.rel_path,
            "kubernetes_env",
        )
    )
    service_edge = kubernetes_env_service_edge(config_value, context)
    if service_edge:
        result.edges.append(service_edge)
    return result


def kubernetes_env_service_edge(config_value: Entity, context: FileScanContext) -> Edge | None:
    key = config_value.properties.get("key")
    raw_target = config_value.properties.get("target_url")
    service_name: str | None = None
    if isinstance(raw_target, str):
        service_name = service_name_from_url(raw_target)
    elif isinstance(key, str) and ENV_NAME_RE.fullmatch(key):
        raw_target = key
        service_name = service_name_from_env(key)
    if not service_name or not isinstance(raw_target, str):
        return None
    target = http_target(raw_target, "GET")
    target["dependency_scope"] = "configuration"
    target["interaction_kind"] = "service_configuration"
    target["config_key"] = key
    target["service_name"] = service_name
    return unresolved_edge(
        config_value,
        service_name,
        "CONFIGURES_SERVICE",
        context.source.name,
        context.rel_path,
        "kubernetes_env",
        to_type="service",
        properties=target,
    )


def kubernetes_ingress_result(context: FileScanContext, document: dict[str, Any]) -> ScanResult:
    result = ScanResult()
    name = kubernetes_resource_name(document)
    if not name:
        return result
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    ingress = Entity(
        entity_type="ingress",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Ingress",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(ingress)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            ingress,
            "DECLARES_INGRESS",
            context.source.name,
            context.rel_path,
            "kubernetes_ingress",
        )
    )
    for rule in mapping_list(spec.get("rules")):
        result.extend(kubernetes_ingress_rule_result(context, ingress, rule))
    return result


def kubernetes_ingress_rule_result(context: FileScanContext, ingress: Entity, rule: dict[str, Any]) -> ScanResult:
    result = ScanResult()
    host = string_value(rule.get("host"))
    http = object_mapping(rule.get("http"))
    for path_item in mapping_list(http.get("paths")):
        path = string_value(path_item.get("path")) or "/"
        route = route_entity(context, "ANY", path, 1, "kubernetes_ingress_route", operation_name=None)
        if host:
            route.aliases.add(f"{host}{path}")
            route.properties["host"] = host
        route.properties["path_type"] = string_value(path_item.get("pathType"))
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                "kubernetes_ingress_route",
                1,
            )
        )
        result.edges.append(
            resolved_edge(
                ingress,
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                "kubernetes_ingress_route",
                1,
            )
        )
        service_name = kubernetes_ingress_backend_service_name(path_item.get("backend"))
        if service_name:
            result.edges.append(
                unresolved_edge(
                    route,
                    service_name,
                    "ROUTES_TO_SERVICE",
                    context.source.name,
                    context.rel_path,
                    "kubernetes_ingress_route",
                    to_type="service",
                    line_number=1,
                    properties=interaction_properties(
                        "application",
                        "deployment",
                        "ingress_route",
                        protocol="http",
                        raw_target=service_name,
                        normalized_target=service_name,
                        service_name=service_name,
                    ),
                )
            )
    return result


def kubernetes_selector_edges(
    context: FileScanContext,
    services: Sequence[KubernetesService],
    deployments: Sequence[KubernetesDeployment],
) -> list[Edge]:
    edges: list[Edge] = []
    for service in services:
        if not service.selector:
            continue
        for deployment in deployments:
            if labels_match_selector(deployment.pod_labels, service.selector):
                edges.append(
                    resolved_edge(
                        service.entity,
                        deployment.entity,
                        "SELECTS_DEPLOYMENT",
                        context.source.name,
                        context.rel_path,
                        "kubernetes_selector",
                    )
                )
    return edges


def labels_match_selector(labels: dict[str, str], selector: dict[str, str]) -> bool:
    return bool(selector) and all(labels.get(key) == value for key, value in selector.items())


def kubernetes_ingress_backend_service_name(value: object) -> str | None:
    backend = object_mapping(value)
    service = object_mapping(backend.get("service"))
    service_name = string_value(service.get("name"))
    if service_name:
        return service_name
    return string_value(backend.get("serviceName"))


def kubernetes_resource_name(document: dict[str, Any]) -> str | None:
    metadata = object_mapping(document.get("metadata"))
    return string_value(metadata.get("name"))


def kubernetes_namespace(metadata: dict[str, Any]) -> str:
    return string_value(metadata.get("namespace")) or "default"


def kubernetes_scoped_aliases(name: str, namespace: str) -> set[str]:
    return {
        name,
        f"{name}.{namespace}",
        f"{name}.{namespace}.svc",
        f"{name}.{namespace}.svc.cluster.local",
    }


def kubernetes_service_ports(value: object) -> list[dict[str, Any]]:
    ports = []
    for port in mapping_list(value):
        ports.append(
            {
                "name": string_value(port.get("name")),
                "port": port.get("port"),
                "target_port": port.get("targetPort"),
                "protocol": string_value(port.get("protocol")),
            }
        )
    return ports


def kubernetes_match_labels(value: object) -> dict[str, str]:
    return string_dict(object_mapping(value).get("matchLabels"))


def mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def csharp_attributes(line: str, line_number: int) -> list[CSharpAttribute]:
    match = CS_ATTRIBUTE_LINE_RE.match(line)
    if not match:
        return []
    return [
        CSharpAttribute(
            name=csharp_attribute_name(attribute_match.group("name")),
            args=attribute_match.group("args"),
            line_number=line_number,
        )
        for attribute_match in CS_ATTRIBUTE_ITEM_RE.finditer(match.group("body"))
    ]


def csharp_attribute_name(name: str) -> str:
    return name.rsplit(".", 1)[-1].removesuffix("Attribute").lower()


def csharp_method_index(content: str) -> TypeMethodIndex:
    current_type: str | None = None
    type_methods: dict[str, set[str]] = {}
    for line in content.splitlines():
        type_match = CS_TYPE_RE.match(line)
        if type_match:
            current_type = type_match.group(2)
            continue
        method_match = CS_METHOD_RE.match(line)
        if current_type and method_match:
            type_methods.setdefault(current_type, set()).add(method_match.group(1))
    return TypeMethodIndex(type_methods={type_name: frozenset(methods) for type_name, methods in type_methods.items()})


def csharp_symbol_result(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> ScanResult:
    result = ScanResult()
    entity_type = csharp_entity_type(symbol_kind)
    full_name = ".".join(part for part in (namespace, parent_name, name) if part)
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = Entity(
        entity_type=entity_type,
        name=full_name or name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "namespace": namespace,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(symbol)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            symbol,
            "DECLARES_SYMBOL",
            context.source.name,
            context.rel_path,
            "dotnet_symbol",
            line_number,
        )
    )
    return result


def csharp_entity_type(symbol_kind: str) -> str:
    if symbol_kind == "interface":
        return "interface"
    if symbol_kind == "method":
        return "function"
    return "class"


def csharp_route_prefix(
    attributes: Sequence[CSharpAttribute],
    type_name: str | None,
    method_name: str | None,
) -> str | None:
    route_attribute = next((attribute for attribute in attributes if attribute.name == "route"), None)
    if not route_attribute:
        return None
    route = csharp_first_string(route_attribute.args)
    if route is None:
        return None
    return csharp_replace_route_tokens(route, type_name, method_name)


def csharp_controller_route_result(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[CSharpAttribute],
    route_prefix: str | None,
    type_name: str | None,
    line_number: int,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    route_path = csharp_route_prefix(attributes, type_name, method_name)
    for attribute in attributes:
        method = csharp_http_attribute_method(attribute)
        if not method:
            continue
        attribute_path = csharp_first_string(attribute.args) or route_path or ""
        path = csharp_join_route_paths(
            route_prefix, csharp_replace_route_tokens(attribute_path, type_name, method_name)
        )
        route = route_entity(context, method, path, line_number, "dotnet_controller_route", method_name)
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                "dotnet_controller_route",
                line_number,
            )
        )
        if context.project:
            result.edges.append(
                resolved_edge(
                    context.project.entity,
                    route,
                    "EXPOSES_ROUTE",
                    context.source.name,
                    context.rel_path,
                    "dotnet_controller_route",
                    line_number,
                )
            )
        if handler:
            result.edges.append(route_handler_edge(context, route, handler, "dotnet_controller_route", line_number))
    return result


def csharp_http_attribute_method(attribute: CSharpAttribute) -> str | None:
    methods = {
        "httpget": "GET",
        "httppost": "POST",
        "httpput": "PUT",
        "httppatch": "PATCH",
        "httpdelete": "DELETE",
        "httphead": "HEAD",
        "httpoptions": "OPTIONS",
    }
    return methods.get(attribute.name)


def csharp_minimal_route_result(context: FileScanContext, line: str, line_number: int) -> ScanResult:
    result = ScanResult()
    for match in CS_MINIMAL_ROUTE_RE.finditer(line):
        result.extend(
            add_route(
                context,
                match.group(1).upper(),
                csharp_unescape_string(match.group(2)),
                line_number,
                "dotnet_minimal_route",
            )
        )
    return result


def csharp_symbol_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[Edge]:
    code = csharp_scope_code(line)
    targets = [
        *csharp_new_method_call_targets(code, method_index),
        *csharp_qualified_method_call_targets(code, current_type, method_index),
        *csharp_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_edges(context, from_entity, targets, "dotnet_call", line_number)


def csharp_new_method_call_targets(code: str, method_index: TypeMethodIndex) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(
            f"{match.group('class')}.{match.group('method')}",
            f"new {match.group('class')}().{match.group('method')}",
            "class_method",
            receiver=match.group("class"),
        )
        for match in CS_NEW_METHOD_CALL_RE.finditer(code)
        if method_index.has_method(match.group("class"), match.group("method"))
    ]


def csharp_qualified_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    targets: list[SymbolCallTarget] = []
    for match in CS_QUALIFIED_METHOD_CALL_RE.finditer(code):
        receiver = match.group("receiver")
        method_name = match.group("method")
        if receiver == "this" and method_index.has_method(current_type, method_name):
            targets.append(
                SymbolCallTarget(f"{current_type}.{method_name}", f"this.{method_name}", "instance_method", receiver)
            )
        elif method_index.has_method(receiver, method_name):
            targets.append(
                SymbolCallTarget(f"{receiver}.{method_name}", f"{receiver}.{method_name}", "class_method", receiver)
            )
    return targets


def csharp_direct_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(f"{current_type}.{method_name}", method_name, "direct")
        for match in CS_DIRECT_METHOD_CALL_RE.finditer(code)
        if (method_name := match.group("method")) and method_index.has_method(current_type, method_name)
    ]


def csharp_http_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    for match in CS_HTTP_CALL_RE.finditer(line):
        method = match.group(1).upper()
        raw_target = csharp_unescape_string(match.group(2))
        parsed = urlparse(raw_target)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            target = http_target(raw_target, method)
            target["service_name"] = service_name_from_url(raw_target)
            target["client"] = "HttpClient"
            target.update(extra_properties)
            edges.append(
                unresolved_edge(
                    source_entity,
                    target["service_name"],
                    "CALLS_SERVICE",
                    context.source.name,
                    context.rel_path,
                    "dotnet_http",
                    to_type="service",
                    line_number=line_number,
                    properties=target,
                )
            )
        else:
            edges.extend(
                http_edges_for_target(
                    context,
                    method,
                    raw_target,
                    line_number,
                    "dotnet_http",
                    client="HttpClient",
                    from_entity=from_entity,
                    extra_properties=extra_properties,
                )
            )
    return edges


def csharp_first_string(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"", value)
    if not match:
        return None
    return csharp_unescape_string(match.group(1))


def csharp_unescape_string(value: str) -> str:
    return value.replace('""', '"').replace(r"\"", '"').replace(r"\\", "\\")


def csharp_replace_route_tokens(value: str, type_name: str | None, method_name: str | None) -> str:
    controller_name = type_name.removesuffix("Controller") if type_name else ""
    route = re.sub(r"\[controller\]", controller_name, value, flags=re.IGNORECASE)
    return re.sub(r"\[action\]", method_name or "", route, flags=re.IGNORECASE)


def csharp_join_route_paths(prefix: str | None, path: str) -> str:
    if path.startswith("/"):
        return path
    parts = [part.strip("/") for part in (prefix, path) if part and part.strip("/")]
    return "/" + "/".join(parts) if parts else "/"


def csharp_should_clear_attributes(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("//"))


def csharp_function_scope_state(line: str, brace_depth: int, seen_body: bool) -> tuple[int, bool]:
    code = csharp_scope_code(line)
    seen_body = seen_body or "{" in code
    brace_depth += code.count("{") - code.count("}")
    return brace_depth, seen_body


def csharp_scope_code(line: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', line)


def config_file_entity(context: FileScanContext, config_kind: str) -> Entity:
    name = Path(context.rel_path).name
    return Entity(
        entity_type="config_file",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={name, context.rel_path},
        properties={
            "config_kind": config_kind,
            "ecosystem": "dotnet",
            "path": context.rel_path,
            "project": context.project.name if context.project else None,
        },
    )


def framework_config_values(context: FileScanContext, root: ET.Element) -> Iterable[Entity]:
    for section in root.iter():
        section_name = xml_local_name(section.tag)
        if section_name == "appSettings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    key = string_value(child.attrib.get("key"))
                    if key:
                        yield config_value_entity(
                            context,
                            key,
                            "app_setting",
                            {
                                "key": key,
                                "has_value": string_value(child.attrib.get("value")) is not None,
                                "target_url": url_value(child.attrib.get("value")),
                            },
                        )
        elif section_name == "connectionStrings":
            for child in section:
                if xml_local_name(child.tag) == "add":
                    name = string_value(child.attrib.get("name"))
                    if name:
                        yield config_value_entity(
                            context,
                            name,
                            "connection_string",
                            {
                                "key": name,
                                "provider_name": string_value(child.attrib.get("providerName")),
                                "has_value": string_value(child.attrib.get("connectionString")) is not None,
                            },
                        )
        elif section_name == "client":
            for child in section:
                if xml_local_name(child.tag) == "endpoint":
                    name = string_value(child.attrib.get("name")) or string_value(child.attrib.get("contract"))
                    address = url_value(child.attrib.get("address"))
                    if name or address:
                        yield config_value_entity(
                            context,
                            name or address or "endpoint",
                            "wcf_endpoint",
                            {
                                "key": name,
                                "contract": string_value(child.attrib.get("contract")),
                                "binding": string_value(child.attrib.get("binding")),
                                "target_url": address,
                            },
                        )


def config_value_entity(
    context: FileScanContext,
    name: str,
    value_kind: str,
    properties: dict[str, Any],
) -> Entity:
    entity_name = f"{value_kind}:{name}"
    return Entity(
        entity_type="config_value",
        name=entity_name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={name, entity_name},
        properties={
            "display_name": name,
            "value_kind": value_kind,
            "project": context.project.name if context.project else None,
            **{key: value for key, value in properties.items() if value is not None},
        },
    )


def config_service_edge(config_value: Entity, context: FileScanContext, parser: str) -> Edge | None:
    raw_target = config_value.properties.get("target_url")
    if not isinstance(raw_target, str):
        return None
    key = config_value.properties.get("key")
    contract = config_value.properties.get("contract")
    service_name = service_name_from_identifier(key or contract or service_name_from_url(raw_target))
    target = http_target(raw_target, "GET")
    target["dependency_scope"] = "configuration"
    target["interaction_kind"] = "service_configuration"
    target["service_name"] = service_name
    return unresolved_edge(
        config_value,
        service_name,
        "CONFIGURES_SERVICE",
        context.source.name,
        context.rel_path,
        parser,
        to_type="service",
        properties=target,
    )


def url_value(value: object) -> str | None:
    raw_value = string_value(value)
    if not raw_value:
        return None
    parsed = urlparse(raw_value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw_value
    return None


def service_name_from_url(raw_target: str) -> str:
    host = urlparse(raw_target).hostname
    if not host:
        return "external-service"
    first_label = host.split(".", 1)[0]
    return service_name_from_identifier(first_label)


def service_name_from_identifier(value: object) -> str:
    raw_value = string_value(value) or "external-service"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", raw_value)
    normalized = re.sub(r"(?:Base)?(?:Url|Uri|Endpoint|Host)$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return normalized or "external-service"


def vb_symbol_result(
    context: FileScanContext,
    symbol_kind: str,
    name: str,
    namespace: str | None,
    line_number: int,
    parent_name: str | None = None,
) -> ScanResult:
    result = ScanResult()
    entity_type = "function" if symbol_kind in {"function", "sub"} else symbol_kind
    full_name = ".".join(part for part in (namespace, parent_name, name) if part)
    aliases = {name, full_name or name}
    if parent_name:
        aliases.add(f"{parent_name}.{name}")
    symbol = Entity(
        entity_type=entity_type,
        name=full_name or name,
        source_name=context.source.name,
        file_path=context.rel_path,
        line_number=line_number,
        aliases=aliases,
        properties={
            "symbol_kind": symbol_kind,
            "namespace": namespace,
            "parent": parent_name,
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(symbol)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            symbol,
            "DECLARES_SYMBOL",
            context.source.name,
            context.rel_path,
            "vb_symbol",
            line_number,
        )
    )
    return result


def vb_method_index(content: str) -> TypeMethodIndex:
    current_type: str | None = None
    type_methods: dict[str, set[str]] = {}
    for line in content.splitlines():
        type_match = VB_TYPE_RE.match(line)
        if type_match:
            current_type = type_match.group(2)
            continue
        method_match = VB_METHOD_RE.match(line)
        if current_type and method_match:
            type_methods.setdefault(current_type, set()).add(method_match.group(2))
    return TypeMethodIndex(type_methods={type_name: frozenset(methods) for type_name, methods in type_methods.items()})


def vb_contract_route_result(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[str],
    line_number: int,
    handler: Entity | None = None,
) -> ScanResult:
    result = ScanResult()
    framework = legacy_contract_framework(attributes)
    if not framework:
        return result
    service_path = legacy_dotnet_service_path(context.rel_path, framework)
    route = route_entity(
        context,
        "POST",
        f"{service_path}/{method_name}",
        line_number,
        "vb_contract_route",
        operation_name=method_name,
    )
    result.entities.append(route)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            route,
            "DECLARES_ROUTE",
            context.source.name,
            context.rel_path,
            "vb_contract_route",
            line_number,
        )
    )
    if context.project:
        result.edges.append(
            resolved_edge(
                context.project.entity,
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                "vb_contract_route",
                line_number,
            )
        )
    if handler:
        result.edges.append(route_handler_edge(context, route, handler, "vb_contract_route", line_number))
    return result


def legacy_contract_framework(attributes: Sequence[str]) -> str | None:
    names = {attribute.rsplit(".", 1)[-1].lower() for attribute in attributes}
    if "webmethod" in names:
        return "asmx"
    if "operationcontract" in names:
        return "wcf"
    return None


def legacy_dotnet_service_path(rel_path: str, framework: str) -> str:
    path = rel_path.replace("\\", "/")
    lower_path = path.lower()
    if (framework == "asmx" and lower_path.endswith(".asmx.vb")) or (
        framework == "wcf" and lower_path.endswith(".svc.vb")
    ):
        path = path[:-3]
    elif lower_path.endswith(".vb"):
        suffix = ".asmx" if framework == "asmx" else ".svc"
        path = f"{path[:-3]}{suffix}"
    return "/" + path


def vb_symbol_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[Edge]:
    code = vb_scope_code(line)
    targets = [
        *vb_new_method_call_targets(code, method_index),
        *vb_qualified_method_call_targets(code, current_type, method_index),
        *vb_direct_method_call_targets(code, current_type, method_index),
    ]
    return symbol_call_edges(context, from_entity, targets, "vb_call", line_number)


def vb_new_method_call_targets(code: str, method_index: TypeMethodIndex) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(
            f"{match.group('class')}.{match.group('method')}",
            f"New {match.group('class')}().{match.group('method')}",
            "class_method",
            receiver=match.group("class"),
        )
        for match in VB_NEW_METHOD_CALL_RE.finditer(code)
        if method_index.has_method(match.group("class"), match.group("method"))
    ]


def vb_qualified_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    targets: list[SymbolCallTarget] = []
    for match in VB_QUALIFIED_METHOD_CALL_RE.finditer(code):
        receiver = match.group("receiver")
        method_name = match.group("method")
        if receiver.lower() == "me" and method_index.has_method(current_type, method_name):
            targets.append(
                SymbolCallTarget(f"{current_type}.{method_name}", f"Me.{method_name}", "instance_method", receiver)
            )
        elif method_index.has_method(receiver, method_name):
            targets.append(
                SymbolCallTarget(f"{receiver}.{method_name}", f"{receiver}.{method_name}", "class_method", receiver)
            )
    return targets


def vb_direct_method_call_targets(
    code: str,
    current_type: str | None,
    method_index: TypeMethodIndex,
) -> list[SymbolCallTarget]:
    return [
        SymbolCallTarget(f"{current_type}.{method_name}", method_name, "direct")
        for match in VB_DIRECT_METHOD_CALL_RE.finditer(code)
        if (method_name := match.group("method")) and method_index.has_method(current_type, method_name)
    ]


def vb_scope_code(line: str) -> str:
    return re.sub(r'"(?:[^"]|"")*"', '""', line)


def vb_service_call_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    for match in VB_HTTP_LITERAL_RE.finditer(line):
        edges.extend(
            legacy_http_edges_for_target(
                context,
                match.group(1),
                line_number,
                "vb_http",
                client=legacy_http_client(match.group(0)),
                from_entity=from_entity,
                extra_properties=extra_properties,
            )
        )
    for match in VB_CONFIG_SETTING_RE.finditer(line):
        key = match.group(1)
        service_name = service_name_from_identifier(key)
        properties = interaction_properties(
            "application",
            "runtime",
            "service_call",
            raw_target=key,
            normalized_target=service_name,
            config_key=key,
            service_name=service_name,
        )
        properties.update(extra_properties)
        edges.append(
            unresolved_edge(
                source_entity,
                service_name,
                "CALLS_SERVICE",
                context.source.name,
                context.rel_path,
                "vb_config_service",
                to_type="service",
                line_number=line_number,
                properties=properties,
            )
        )
    return edges


def legacy_http_edges_for_target(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str,
    from_entity: Entity | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[Edge]:
    source_entity = from_entity or context.file_entity
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, "GET")
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        if extra_properties:
            target.update(extra_properties)
        return [
            unresolved_edge(
                source_entity,
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
    return http_edges_for_target(
        context,
        "GET",
        raw_target,
        line_number,
        parser,
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
    )


def legacy_http_client(evidence: str) -> str:
    if "WebRequest" in evidence:
        return "WebRequest"
    if "WebClient" in evidence:
        return "WebClient"
    return "legacy_http_client"


def vb_sql_command_edges(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: Entity | None = None,
) -> list[Edge]:
    targets = [match.group(1) for match in VB_COMMAND_TEXT_RE.finditer(line)]
    targets.extend(match.group(1) for match in VB_SQL_COMMAND_RE.finditer(line))
    edges: list[Edge] = []
    source_entity = from_entity or context.file_entity
    extra_properties = source_context_properties(from_entity)
    for target in targets:
        normalized = stored_procedure_target(target)
        if not normalized:
            continue
        edges.append(
            unresolved_edge(
                source_entity,
                normalized,
                "CALLS_SQL",
                context.source.name,
                context.rel_path,
                "vb_sql_command",
                to_type="stored_procedure",
                line_number=line_number,
                properties=sql_interaction_properties(
                    target,
                    "EXECUTE",
                    "stored_procedure",
                    extra_properties=extra_properties,
                ),
            )
        )
    return edges


def stored_procedure_target(value: str) -> str | None:
    exec_match = SQL_EXEC_RE.search(value)
    if exec_match:
        return normalize_sql_name(exec_match.group(1))
    stripped = value.strip()
    if re.fullmatch(r"[\[\]\w]+(?:\.[\[\]\w]+)+", stripped):
        return normalize_sql_name(stripped)
    return None


def xml_root(content: str, context: FileScanContext) -> ET.Element:
    try:
        return ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML {context.source.name}/{context.rel_path}: {exc}") from exc


def first_xml_text(root: ET.Element, name: str) -> str | None:
    for element in root.iter():
        if xml_local_name(element.tag) == name:
            value = string_value(element.text)
            if value:
                return value
    return None


def first_child_text(root: ET.Element, name: str) -> str | None:
    for child in root:
        if xml_local_name(child.tag) == name:
            return string_value(child.text)
    return None


def xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def object_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dependency_source_entity(context: FileScanContext, package_entity: Entity | None = None) -> Entity:
    if package_entity:
        return package_entity
    if context.project:
        return context.project.entity
    return context.file_entity


def package_dependency_edge(
    from_entity: Entity,
    name: str | None,
    ecosystem: str,
    dependency_type: str | None,
    version: str | None,
    raw_target: str | None,
    source_name: str,
    file_path: str,
    parser: str,
    line_number: int | None = None,
) -> Edge:
    target_name = name or raw_target or ""
    return unresolved_edge(
        from_entity,
        target_name,
        "DEPENDS_ON_PACKAGE",
        source_name,
        file_path,
        parser,
        to_type="package",
        line_number=line_number,
        properties={
            "ecosystem": ecosystem,
            "dependency_type": dependency_type,
            "version": version,
            "raw_target": raw_target,
            "normalized_target": target_name,
        },
    )


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
