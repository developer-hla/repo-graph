from __future__ import annotations

import unittest
from pathlib import Path
from typing import get_type_hints

from repo_graph.extraction.contracts import FileScanContext, ProjectInfo
from repo_graph.extraction.facts import EntityFact


class ExtractionContractTests(unittest.TestCase):
    def test_source_context_uses_fact_entities(self) -> None:
        self.assertIs(get_type_hints(ProjectInfo)["entity"], EntityFact)
        self.assertIs(get_type_hints(FileScanContext)["repo_entity"], EntityFact)
        self.assertIs(get_type_hints(FileScanContext)["file_entity"], EntityFact)

    def test_scanner_modules_do_not_import_graph_model(self) -> None:
        scanner_root = Path(__file__).resolve().parents[1] / "src" / "repo_graph" / "extraction" / "scanners"
        offenders = [
            path.relative_to(scanner_root).as_posix()
            for path in scanner_root.glob("*.py")
            if "repo_graph.graph" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])
