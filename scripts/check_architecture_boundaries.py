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
        scan_files(python_files(Path("."), SCAN_ROOTS)),
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


def scan_files(paths: Iterable[Path]) -> Iterable[BoundaryFinding]:
    for path in paths:
        yield from scan_file(path)


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


def normalize_path(path: Path | str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
