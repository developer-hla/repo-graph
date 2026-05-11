from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.config import load_config
from repo_graph.scanner import build_graph


class ScannerTests(unittest.TestCase):
    def test_build_graph_from_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"name": "@example/service", "dependencies": {"@example/lib": "1.0.0"}}',
                encoding="utf-8",
            )
            (repo / "api.ts").write_text(
                """
import { helper } from '@example/lib';
router.get('/health', handler);
const sql = 'EXEC dbo.get_things';
""",
                encoding="utf-8",
            )
            (repo / "schema.sql").write_text(
                """
CREATE PROCEDURE dbo.get_things AS
SELECT * FROM dbo.things
CREATE TABLE dbo.things (id int)
""",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: service
    path: service
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 3)
        self.assertGreaterEqual(graph_data["summary"]["entity_count"], 6)
        self.assertIn("DECLARES_ROUTE", graph_data["edge_counts"])
        self.assertIn("DEPENDS_ON_PACKAGE", graph_data["edge_counts"])
        self.assertIn("CALLS_SQL", graph_data["edge_counts"])
        self.assertIn("DEFINES", graph_data["edge_counts"])
        self.assertGreater(graph_data["summary"]["resolved_edge_count"], 0)

    def test_strict_build_raises_on_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: missing
    path: missing
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            with self.assertRaisesRegex(RuntimeError, "scanner errors"):
                build_graph(config, strict=True)

        self.assertEqual(graph.errors, ["Missing source path: {}".format((root / "missing").resolve())])


if __name__ == "__main__":
    unittest.main()
