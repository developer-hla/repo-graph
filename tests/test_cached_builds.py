from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_graph.config import load_config
from repo_graph.database import DatabaseGraphFacts
from repo_graph.extraction.cached_builds import build_cached_graph
from repo_graph.graph import Entity


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

    def test_cached_build_refreshes_database_sources_each_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root, include_database=True))
            facts = DatabaseGraphFacts(
                entities=[
                    Entity(
                        entity_type="sql_table",
                        name="dbo.Customers",
                        source_name="current-db",
                        properties={"schema_state": "current_database"},
                    )
                ]
            )

            with patch("repo_graph.extraction.cached_builds.graph_from_database_source", return_value=facts):
                first = build_cached_graph(config)
                second = build_cached_graph(config)

        first_statuses = {item["source_name"]: item["status"] for item in first.cache_summary["items"]}
        second_statuses = {item["source_name"]: item["status"] for item in second.cache_summary["items"]}
        self.assertEqual(first.cache_summary["rebuilt_count"], 3)
        self.assertEqual(second.cache_summary["rebuilt_count"], 1)
        self.assertEqual(second.cache_summary["reused_count"], 2)
        self.assertEqual(first_statuses["current-db"], "rebuilt")
        self.assertEqual(second_statuses["current-db"], "rebuilt")
        self.assertTrue(any(source["name"] == "current-db" for source in second.graph.to_dict()["sources"]))
        self.assertTrue(any(entity["name"] == "dbo.Customers" for entity in second.graph.to_dict()["entities"]))


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


def write_config(root: Path, include_database: bool = False) -> Path:
    config_path = root / "sources.yaml"
    database_source = (
        """
  - type: database
    name: current-db
    engine: sqlserver
    connection_env: REPO_GRAPH_EXAMPLE_SQLSERVER_URL
"""
        if include_database
        else ""
    )
    config_path.write_text(
        f"""
name: test-scope
output_dir: .repo-graph/output
sources:
  - type: local_path
    name: shared
    path: shared
  - type: local_path
    name: service
    path: service
{database_source}
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
