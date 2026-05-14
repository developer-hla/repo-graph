from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.config import load_config
from repo_graph.snapshots import snapshot_status, source_snapshot, write_snapshots
from repo_graph.sources import resolve_sources


class SnapshotTests(unittest.TestCase):
    def test_snapshot_status_reports_new_then_unchanged_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
            config = load_config(write_config(root))

            before = snapshot_status(config)
            written = write_snapshots(config)
            after = snapshot_status(config)

        self.assertEqual(before["changed_count"], 1)
        self.assertEqual(before["items"][0]["status"], "new")
        self.assertIn("snapshot_missing", before["items"][0]["reasons"])
        self.assertEqual(before["items"][0]["added_files"], ["package.json"])
        self.assertEqual(written["count"], 1)
        self.assertEqual(after["changed_count"], 0)
        self.assertEqual(after["items"][0]["status"], "unchanged")

    def test_snapshot_status_detects_added_modified_and_removed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
            (repo / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
            config = load_config(write_config(root))
            write_snapshots(config)

            (repo / "index.ts").write_text("export const value = 2;\n", encoding="utf-8")
            (repo / "new.ts").write_text("export const next = 3;\n", encoding="utf-8")
            (repo / "package.json").unlink()
            status = snapshot_status(config)

        item = status["items"][0]
        self.assertTrue(item["changed"])
        self.assertEqual(item["status"], "changed")
        self.assertIn("files_added", item["reasons"])
        self.assertIn("files_modified", item["reasons"])
        self.assertIn("files_removed", item["reasons"])
        self.assertEqual(item["added_files"], ["new.ts"])
        self.assertEqual(item["modified_files"], ["index.ts"])
        self.assertEqual(item["removed_files"], ["package.json"])

    def test_source_snapshot_uses_scannable_file_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            (repo / "node_modules").mkdir(parents=True)
            (repo / "src").mkdir()
            (repo / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
            (repo / "node_modules" / "ignored.ts").write_text("export const ignored = true;\n", encoding="utf-8")
            (repo / "notes.md").write_text("# Notes\n", encoding="utf-8")
            config = load_config(write_config(root))
            source = resolve_sources(config)[0]

            snapshot = source_snapshot(config, source)

        self.assertEqual(snapshot["file_count"], 1)
        self.assertEqual(snapshot["files"][0]["path"], "src/index.ts")
        self.assertEqual(len(snapshot["files"][0]["sha256"]), 64)


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
