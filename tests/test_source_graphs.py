from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.config import load_config
from repo_graph.source_graphs import source_graph_data, source_graph_path, write_source_graphs
from repo_graph.sources import resolve_sources


class SourceGraphTests(unittest.TestCase):
    def test_source_graph_data_defers_global_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_service(root)
            config = load_config(write_config(root))
            source = resolve_sources(config)[0]

            graph_data = source_graph_data(config, source)

        self.assertEqual(graph_data["metadata"]["artifact_type"], "source_graph")
        self.assertEqual(graph_data["metadata"]["parent_scope_name"], "test-scope")
        self.assertEqual(graph_data["metadata"]["source_name"], "service")
        self.assertEqual(graph_data["metadata"]["resolution_status"], "deferred_global")
        self.assertEqual(graph_data["sources"][0]["name"], "service")
        self.assertEqual(graph_data["summary"]["files_scanned"], 2)
        self.assertGreaterEqual(graph_data["summary"]["entity_count"], 4)
        self.assertGreaterEqual(graph_data["summary"]["edge_count"], 3)
        self.assertTrue(any(edge["edge_type"] == "IMPORTS" for edge in graph_data["edges"]))

    def test_write_source_graphs_writes_graph_and_snapshot_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_service(root)
            config = load_config(write_config(root))
            source = resolve_sources(config)[0]

            written = write_source_graphs(config)
            graph_path = source_graph_path(config, source)
            snapshot_path = graph_path.with_name("snapshot.json")

            self.assertEqual(written["count"], 1)
            self.assertEqual(written["items"][0]["source_name"], "service")
            self.assertEqual(written["items"][0]["graph_path"], str(graph_path))
            self.assertEqual(written["items"][0]["snapshot_path"], str(snapshot_path))
            self.assertTrue(graph_path.exists())
            self.assertTrue(snapshot_path.exists())


def write_service(root: Path) -> None:
    repo = root / "service"
    (repo / "src").mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"name": "@example/service", "dependencies": {"@example/shared": "1.0.0"}}',
        encoding="utf-8",
    )
    (repo / "src" / "index.ts").write_text(
        'import { shared } from "@example/shared";\nexport const value = shared;\n',
        encoding="utf-8",
    )


def write_config(root: Path) -> Path:
    config_path = root / "sources.yaml"
    config_path.write_text(
        """
name: test-scope
output_dir: .repo-graph/output
sources:
  - type: local_path
    name: service
    path: service
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
