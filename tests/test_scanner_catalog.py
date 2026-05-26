"""Scanner catalog metadata tests."""

from __future__ import annotations

import unittest

from repo_graph.extraction.registry import default_extractors


class ScannerCatalogTests(unittest.TestCase):
    def test_default_extractors_expose_catalog_metadata(self) -> None:
        for extractor in default_extractors():
            with self.subTest(scanner=extractor.name):
                self.assertTrue(extractor.target_patterns)
                self.assertTrue(extractor.parser_ids)
                self.assertTrue(all(pattern.strip() for pattern in extractor.target_patterns))
                self.assertTrue(all(parser_id.strip() for parser_id in extractor.parser_ids))
