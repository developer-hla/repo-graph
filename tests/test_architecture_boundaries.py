"""Architecture boundary check tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from scripts.check_architecture_boundaries import BoundaryFinding, scan_file, scanner_helper_path_findings


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_reports_scanner_internal_import_outside_scanner_package(self) -> None:
        finding = self.scan_source(
            "src/repo_graph/api.py",
            "from repo_graph.extraction.scanners.code.python.imports import python_import_fact\n",
        )

        self.assertEqual(len(finding), 1)
        self.assertEqual(finding[0].module, "repo_graph.extraction.scanners.code.python.imports")

    def test_allows_public_scanner_package_import_outside_scanner_package(self) -> None:
        finding = self.scan_source(
            "src/repo_graph/extraction/registry.py",
            "from repo_graph.extraction.scanners.code.python import PythonCodeExtractor\n",
        )

        self.assertEqual(finding, [])

    def test_allows_scanner_package_internal_import(self) -> None:
        finding = self.scan_source(
            "src/repo_graph/extraction/scanners/code/python/scanner.py",
            "from repo_graph.extraction.scanners.code.python.imports import python_import_fact\n",
        )

        self.assertEqual(finding, [])

    def test_reports_import_statement_for_scanner_internal_module(self) -> None:
        finding = self.scan_source(
            "src/repo_graph/api.py",
            "import repo_graph.extraction.scanners.manifests.pyproject\n",
        )

        self.assertEqual(len(finding), 1)
        self.assertEqual(finding[0].module, "repo_graph.extraction.scanners.manifests.pyproject")

    def test_reports_new_scanner_helper_facade_path(self) -> None:
        finding = self.scan_helper_path("src/repo_graph/extraction/scanners/cache_helpers.py")

        self.assertEqual(len(finding), 1)
        self.assertIn("focused scanner package module", finding[0].message)

    def test_allows_existing_shared_helper_path(self) -> None:
        finding = self.scan_helper_path("src/repo_graph/extraction/scanners/package_helpers.py")

        self.assertEqual(finding, [])

    def test_reports_package_helpers_file_without_allowlist(self) -> None:
        finding = self.scan_helper_path("src/repo_graph/extraction/scanners/code/python/helpers.py")

        self.assertEqual(len(finding), 1)
        self.assertEqual(finding[0].module, "src/repo_graph/extraction/scanners/code/python/helpers.py")

    def scan_source(self, relative_path: str, content: str) -> list[BoundaryFinding]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            with working_directory(Path(directory)):
                return list(scan_file(Path(relative_path)))

    def scan_helper_path(self, relative_path: str) -> list[BoundaryFinding]:
        return list(scanner_helper_path_findings(Path(relative_path)))


@contextmanager
def working_directory(path: Path) -> Iterator[None]:
    current = Path.cwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(current)
