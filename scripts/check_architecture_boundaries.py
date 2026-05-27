"""Check import boundaries that keep package internals private."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SCAN_ROOTS = (
    Path("src"),
    Path("scripts"),
)

EXCLUDED_DIRS = {
    "__pycache__",
}

PUBLIC_SCANNER_PACKAGES = (
    "repo_graph.extraction.scanners.code.dotnet",
    "repo_graph.extraction.scanners.code.javascript",
    "repo_graph.extraction.scanners.code.python",
    "repo_graph.extraction.scanners.deployment",
    "repo_graph.extraction.scanners.manifests",
    "repo_graph.extraction.scanners.sql",
)

SCANNER_PACKAGE_ROOT = "src/repo_graph/extraction/scanners"
ALLOWED_SCANNER_HELPER_PATHS = frozenset(
    {
        f"{SCANNER_PACKAGE_ROOT}/code/javascript/helpers.py",
        f"{SCANNER_PACKAGE_ROOT}/manifest_helpers.py",
        f"{SCANNER_PACKAGE_ROOT}/package_helpers.py",
        f"{SCANNER_PACKAGE_ROOT}/symbol_helpers.py",
    }
)
INTERACTION_PROPERTIES_MODULE = "repo_graph.extraction.interaction_properties"
SQL_PROPERTIES_MODULE = "repo_graph.extraction.scanners.sql.properties"
DATABASE_METADATA_EDGES_MODULE = "repo_graph.database._metadata_edges"
DATABASE_METADATA_EDGES_PATH = "src/repo_graph/database/_metadata_edges.py"
RAW_DATABASE_METADATA_EDGE_NAMES = frozenset(
    {
        "database_interaction_properties",
        "database_metadata_edge",
    }
)
ALLOWED_INTERACTION_PROPERTY_IMPORT_PATHS = frozenset(
    {
        "src/repo_graph/extraction/interaction_properties.py",
        f"{SCANNER_PACKAGE_ROOT}/cache/facts.py",
        f"{SCANNER_PACKAGE_ROOT}/interactions/http.py",
        f"{SCANNER_PACKAGE_ROOT}/interactions/services.py",
        f"{SCANNER_PACKAGE_ROOT}/messaging/facts.py",
        f"{SCANNER_PACKAGE_ROOT}/sql/properties.py",
        f"{SCANNER_PACKAGE_ROOT}/storage/facts.py",
    }
)
ALLOWED_SQL_INTERACTION_PROPERTY_IMPORT_PATHS = frozenset(
    {
        f"{SCANNER_PACKAGE_ROOT}/sql/facts.py",
        f"{SCANNER_PACKAGE_ROOT}/sql/properties.py",
    }
)


@dataclass(frozen=True)
class ImportReference:
    module: str
    line_number: int


@dataclass(frozen=True)
class BoundaryFinding:
    path: str
    line_number: int
    module: str
    message: str


def main() -> int:
    findings = sorted(
        scan_paths(python_files(Path("."), SCAN_ROOTS)),
        key=lambda finding: (finding.path, finding.line_number, finding.module),
    )
    if not findings:
        print("Architecture boundary check passed.")
        return 0

    print("Architecture boundary check failed.")
    for finding in findings:
        print(f"  - {finding.path}:{finding.line_number} imports {finding.module}: {finding.message}")
    return 1


def python_files(root: Path, scan_roots: Iterable[Path]) -> Iterable[Path]:
    for scan_root in scan_roots:
        path = root / scan_root
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        for child in path.rglob("*.py"):
            if not any(part in EXCLUDED_DIRS for part in child.parts):
                yield child


def scan_paths(paths: Iterable[Path]) -> Iterable[BoundaryFinding]:
    for path in paths:
        yield from scanner_helper_path_findings(path)
        yield from interaction_property_import_findings(path)
        yield from sql_interaction_property_import_findings(path)
        yield from database_metadata_edge_import_findings(path)
        yield from scan_file(path)


def scanner_helper_path_findings(path: Path) -> Iterable[BoundaryFinding]:
    relative_path = normalize_path(path)
    if not scanner_helper_module_path(relative_path):
        return
    if relative_path in ALLOWED_SCANNER_HELPER_PATHS:
        return
    yield BoundaryFinding(
        relative_path,
        1,
        relative_path,
        "use a focused scanner package module instead of adding a new scanner helper facade",
    )


def scanner_helper_module_path(relative_path: str) -> bool:
    if not relative_path.startswith(f"{SCANNER_PACKAGE_ROOT}/"):
        return False
    name = Path(relative_path).name
    return name == "helpers.py" or name.endswith("_helpers.py")


def interaction_property_import_findings(path: Path) -> Iterable[BoundaryFinding]:
    relative_path = normalize_path(path)
    if relative_path in ALLOWED_INTERACTION_PROPERTY_IMPORT_PATHS:
        return

    for reference in import_references(path):
        if reference.module == INTERACTION_PROPERTIES_MODULE:
            yield BoundaryFinding(
                relative_path,
                reference.line_number,
                reference.module,
                "use the owning interaction fact builder instead of importing the raw interaction property helper",
            )


def sql_interaction_property_import_findings(path: Path) -> Iterable[BoundaryFinding]:
    relative_path = normalize_path(path)
    if relative_path in ALLOWED_SQL_INTERACTION_PROPERTY_IMPORT_PATHS:
        return

    for reference in import_from_name_references(path):
        if reference.module == SQL_PROPERTIES_MODULE and reference.name == "sql_interaction_properties":
            yield BoundaryFinding(
                relative_path,
                reference.line_number,
                reference.module,
                "use repo_graph.extraction.scanners.sql.facts instead of importing sql_interaction_properties",
            )


def database_metadata_edge_import_findings(path: Path) -> Iterable[BoundaryFinding]:
    relative_path = normalize_path(path)
    if relative_path == DATABASE_METADATA_EDGES_PATH:
        return

    for reference in import_from_name_references(path):
        if reference.module == DATABASE_METADATA_EDGES_MODULE and reference.name in RAW_DATABASE_METADATA_EDGE_NAMES:
            yield BoundaryFinding(
                relative_path,
                reference.line_number,
                reference.module,
                "use a semantic database metadata edge builder instead of importing raw edge/property helpers",
            )


def scan_file(path: Path) -> Iterable[BoundaryFinding]:
    relative_path = normalize_path(path)
    if scanner_internal_imports_allowed(relative_path):
        return

    for reference in import_references(path):
        if scanner_internal_module(reference.module):
            yield BoundaryFinding(
                relative_path,
                reference.line_number,
                reference.module,
                "import the scanner family package root instead of an internal module",
            )


def scanner_internal_imports_allowed(relative_path: str) -> bool:
    return relative_path.startswith(f"{SCANNER_PACKAGE_ROOT}/")


def scanner_internal_module(module: str) -> bool:
    return any(module.startswith(f"{public_package}.") for public_package in PUBLIC_SCANNER_PACKAGES)


def import_references(path: Path) -> Iterable[ImportReference]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportReference(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield ImportReference(node.module, node.lineno)


@dataclass(frozen=True)
class ImportFromNameReference:
    module: str
    name: str
    line_number: int


def import_from_name_references(path: Path) -> Iterable[ImportFromNameReference]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield ImportFromNameReference(node.module, alias.name, node.lineno)


def normalize_path(path: Path | str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
