from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from repo_graph.cli import agent_instructions_markdown, build_parser


class CliTests(unittest.TestCase):
    def assert_rejects_invalid_max_file_bytes(self, args: list[str]) -> None:
        parser = build_parser()
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as raised:
            parser.parse_args(args)

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("max-file-bytes must be at least 1", errors.getvalue())

    def test_agent_instructions_markdown_points_to_manifest(self) -> None:
        markdown = agent_instructions_markdown("http://repo-graph:8000", Path("repo-graph.yaml"))

        self.assertIn("## Repo Graph", markdown)
        self.assertIn("`http://repo-graph:8000/manifest`", markdown)
        self.assertIn("`repo-graph.yaml`", markdown)
        self.assertIn("runtime manifest as the source of truth", markdown)
        self.assertIn("do not treat them as unused code by default", markdown)

    def test_agent_instructions_command_prints_markdown(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "agent-instructions",
                "--api-url",
                "http://repo-graph:8000",
                "--config",
                "repo-graph.yaml",
            ]
        )
        output = io.StringIO()

        with redirect_stdout(output):
            result = args.func(args)

        self.assertEqual(result, 0)
        self.assertIn("http://repo-graph:8000/sources/configured", output.getvalue())

    def test_unresolved_report_command_prints_grouped_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_path = Path(tmpdir) / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "metadata": {"scope_name": "test-scope"},
                        "edges": [
                            {
                                "edge_id": "edge-1",
                                "edge_type": "CALLS_SERVICE",
                                "to_type": "service",
                                "to_name": "inventory-service",
                                "source_name": "api-service",
                                "resolved": False,
                                "properties": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            parser = build_parser()
            args = parser.parse_args(["report", "unresolved", "--graph", str(graph_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["scope_name"], "test-scope")
        self.assertEqual(payload["items"][0]["classification"], "likely_missing_source")

    def test_interactions_report_command_prints_grouped_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_path = Path(tmpdir) / "graph.json"
            graph_path.write_text(
                json.dumps(
                    {
                        "metadata": {"scope_name": "test-scope"},
                        "entities": [
                            {
                                "entity_id": "entity-1",
                                "entity_type": "service",
                                "name": "inventory-service",
                                "source_name": "inventory-service",
                            }
                        ],
                        "edges": [
                            {
                                "edge_id": "edge-1",
                                "edge_type": "CALLS_SERVICE",
                                "to_type": "service",
                                "to_name": "inventory-service",
                                "to_entity_id": "entity-1",
                                "source_name": "api-service",
                                "resolved": True,
                                "properties": {
                                    "target_boundary": "application",
                                    "dependency_scope": "runtime",
                                    "interaction_kind": "http_call",
                                    "protocol": "http",
                                    "raw_target": "http://inventory-service/orders",
                                    "normalized_target": "GET /orders",
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            parser = build_parser()
            args = parser.parse_args(["report", "interactions", "--graph", str(graph_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["scope_name"], "test-scope")
        self.assertEqual(payload["items"][0]["from_source"], "api-service")
        self.assertEqual(payload["items"][0]["target_source"], "inventory-service")

    def test_snapshot_status_command_reports_changed_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
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
            parser = build_parser()
            args = parser.parse_args(["snapshot", "status", "--config", str(config_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["changed_count"], 1)
        self.assertEqual(payload["items"][0]["status"], "new")

    def test_commands_reject_non_positive_max_file_bytes(self) -> None:
        commands = [
            ["build", "--config", "sources.yaml", "--max-file-bytes", "0"],
            ["refresh", "--config", "sources.yaml", "--max-file-bytes", "0"],
            ["snapshot", "status", "--config", "sources.yaml", "--max-file-bytes", "0"],
            ["snapshot", "write", "--config", "sources.yaml", "--max-file-bytes", "0"],
            ["source-graphs", "write", "--config", "sources.yaml", "--max-file-bytes", "0"],
        ]

        for command in commands:
            with self.subTest(command=command):
                self.assert_rejects_invalid_max_file_bytes(command)

    def test_source_graphs_write_command_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
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
            parser = build_parser()
            args = parser.parse_args(["source-graphs", "write", "--config", str(config_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

            payload = json.loads(output.getvalue())
            graph_path = root / ".repo-graph" / "sources" / "service" / "graph.json"
            snapshot_path = root / ".repo-graph" / "sources" / "service" / "snapshot.json"

            self.assertEqual(result, 0)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["source_name"], "service")
            self.assertTrue(graph_path.exists())
            self.assertTrue(snapshot_path.exists())

    def test_build_cached_command_prints_cache_summary_and_writes_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
            config_path = root / "sources.yaml"
            output_path = root / "graph.json"
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
            parser = build_parser()
            args = parser.parse_args(["build", "--cached", "--config", str(config_path), "--output", str(output_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

            payload = json.loads(output.getvalue())
            graph_data = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(result, 0)
            self.assertEqual(payload["cache"]["rebuilt_count"], 1)
            self.assertEqual(payload["cache"]["reused_count"], 0)
            self.assertEqual(graph_data["metadata"]["build_mode"], "cached")
            self.assertTrue(output_path.exists())

    def test_refresh_command_prints_refresh_summary_and_writes_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text('{"name": "@example/service"}', encoding="utf-8")
            config_path = root / "sources.yaml"
            output_path = root / "graph.json"
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
            parser = build_parser()
            args = parser.parse_args(["refresh", "--config", str(config_path), "--output", str(output_path)])
            output = io.StringIO()

            with redirect_stdout(output):
                result = args.func(args)

            payload = json.loads(output.getvalue())
            graph_data = json.loads(output_path.read_text(encoding="utf-8"))

            self.assertEqual(result, 0)
            self.assertEqual(payload["status"], "refreshed")
            self.assertEqual(payload["changes"]["changed_sources"], ["service"])
            self.assertEqual(payload["load"]["action"], "not_requested")
            self.assertEqual(graph_data["metadata"]["build_mode"], "cached")


if __name__ == "__main__":
    unittest.main()
