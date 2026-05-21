from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "service"
            source_dir.mkdir()
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test
cache_dir: cache/repos
sources:
  - type: local_path
    name: service
    path: service
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.name, "test")
        self.assertEqual(len(config.sources), 1)
        self.assertEqual(config.sources[0].name, "service")

    def test_load_config_rejects_duplicate_source_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: git
    name: service
    url: https://github.com/example/service.git
  - type: git
    name: service
    url: https://github.com/example/other.git
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Duplicate source name"):
                load_config(config_path)

    def test_load_config_reads_github_org_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: github_org
    name: example-org
    org: example
    visibility: all
    ref: default
    limit: 25
    include:
      archived: false
      forks: false
      name_patterns:
        - "^api-"
    exclude:
      name_patterns:
        - "-experiment$"
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.sources[0].source_type, "github_org")
        self.assertEqual(config.sources[0].org, "example")
        self.assertEqual(config.sources[0].visibility, "all")
        self.assertEqual(config.sources[0].limit, 25)
        self.assertEqual(config.sources[0].include_name_patterns, ("^api-",))
        self.assertEqual(config.sources[0].exclude_name_patterns, ("-experiment$",))

    def test_load_config_reads_database_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: database
    name: current-db
    engine: sqlserver
    connection_env: REPO_GRAPH_EXAMPLE_SQLSERVER_URL
    schemas:
      - dbo
    include_object_types:
      - table
      - view
      - stored_procedure
    query_timeout_seconds: 10
    max_metadata_rows: 50000
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        source = config.sources[0]
        self.assertEqual(source.source_type, "database")
        self.assertEqual(source.engine, "sqlserver")
        self.assertEqual(source.connection_env, "REPO_GRAPH_EXAMPLE_SQLSERVER_URL")
        self.assertEqual(source.schemas, ("dbo",))
        self.assertEqual(source.include_object_types, ("table", "view", "stored_procedure"))
        self.assertEqual(source.query_timeout_seconds, 10)
        self.assertEqual(source.max_metadata_rows, 50000)
        self.assertIsNone(source.path)
        self.assertIsNone(source.url)

    def test_load_config_rejects_database_connection_string_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: database
    name: current-db
    engine: sqlserver
    connection_string: Server=example;Database=example
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "connection_env"):
                load_config(config_path)

    def test_load_config_rejects_unsupported_database_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: database
    name: current-db
    engine: mysql
    connection_env: REPO_GRAPH_EXAMPLE_MYSQL_URL
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "unsupported engine"):
                load_config(config_path)

    def test_load_config_reads_postgres_database_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
sources:
  - type: database
    name: current-pg
    engine: postgres
    connection_env: REPO_GRAPH_EXAMPLE_POSTGRES_URL
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.sources[0].source_type, "database")
        self.assertEqual(config.sources[0].engine, "postgres")
        self.assertEqual(config.sources[0].connection_env, "REPO_GRAPH_EXAMPLE_POSTGRES_URL")

    def test_load_config_reads_dependency_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
dependency_filter:
  package_include_patterns:
    - "^@example/"
  package_exclude_patterns:
    - "-test$"
  include_relative_imports: false
sources: []
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.dependency_filter.package_include_patterns, ("^@example/",))
        self.assertEqual(config.dependency_filter.package_exclude_patterns, ("-test$",))
        self.assertFalse(config.dependency_filter.include_relative_imports)

    def test_load_config_rejects_invalid_dependency_filter_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
name: test
dependency_filter:
  package_include_patterns:
    - "["
sources: []
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid regex"):
                load_config(config_path)


if __name__ == "__main__":
    unittest.main()
