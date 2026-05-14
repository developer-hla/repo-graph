from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.cached_builds import build_cached_graph
from repo_graph.config import load_config


class CachedBuildTests(unittest.TestCase):
    def test_cached_build_reuses_unchanged_source_graphs_and_resolves_globally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))

            first = build_cached_graph(config)
            first_data = first.graph.to_dict()
            second = build_cached_graph(config)

        self.assertEqual(first.cache_summary["rebuilt_count"], 2)
        self.assertEqual(first.cache_summary["reused_count"], 0)
        self.assertEqual(second.cache_summary["rebuilt_count"], 0)
        self.assertEqual(second.cache_summary["reused_count"], 2)
        self.assertGreater(first_data["summary"]["resolved_edge_count"], 0)
        self.assertTrue(
            any(
                edge["source_name"] == "service"
                and edge["to_name"] == "@example/shared"
                and edge["resolved"]
                and edge["to_type"] == "package"
                for edge in first_data["edges"]
            )
        )

    def test_cached_build_rebuilds_only_changed_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            build_cached_graph(config)

            (root / "service" / "src" / "index.ts").write_text(
                'import { shared } from "@example/shared";\nexport const value = shared + "-changed";\n',
                encoding="utf-8",
            )
            result = build_cached_graph(config)

        statuses = {item["source_name"]: item["status"] for item in result.cache_summary["items"]}
        self.assertEqual(result.cache_summary["rebuilt_count"], 1)
        self.assertEqual(result.cache_summary["reused_count"], 1)
        self.assertEqual(statuses["service"], "rebuilt")
        self.assertEqual(statuses["shared"], "reused")


def write_workspace(root: Path) -> None:
    shared = root / "shared"
    shared.mkdir()
    (shared / "package.json").write_text('{"name": "@example/shared"}', encoding="utf-8")
    (shared / "index.ts").write_text("export const shared = 'shared';\n", encoding="utf-8")

    service = root / "service"
    (service / "src").mkdir(parents=True)
    (service / "package.json").write_text(
        '{"name": "@example/service", "dependencies": {"@example/shared": "1.0.0"}}',
        encoding="utf-8",
    )
    (service / "src" / "index.ts").write_text(
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
    name: shared
    path: shared
  - type: local_path
    name: service
    path: service
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
