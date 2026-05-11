"""Tests for the Repo Graph API runtime."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from repo_graph.api import LoadRequest, RuntimeSettings, create_app, health_payload, load_response, manifest_payload
from repo_graph.storage.neo4j import LoadSummary


class ApiTests(unittest.TestCase):
    def test_health_payload_identifies_service(self) -> None:
        payload = health_payload()

        self.assertEqual(payload["service"], "repo-graph")
        self.assertEqual(payload["status"], "ok")
        self.assertIn("version", payload)

    def test_manifest_describes_runtime_without_secrets(self) -> None:
        settings = RuntimeSettings(
            config_path=Path("config/local-example.yaml"),
            neo4j_uri="bolt://neo4j:7687",
            neo4j_user="neo4j",
        )
        payload = manifest_payload(settings)

        self.assertEqual(payload["service"], "repo-graph")
        self.assertEqual(payload["config"]["path"], "config/local-example.yaml")
        self.assertEqual(payload["graph_store"]["type"], "neo4j")
        self.assertIsNone(payload["graph_store"]["database"])
        self.assertIn({"method": "POST", "path": "/load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/stats", "available": True}, payload["endpoints"])
        self.assertNotIn("password", str(payload).lower())

    def test_app_exposes_runtime_routes(self) -> None:
        app = create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None))
        route_paths = {route.path for route in app.routes}

        self.assertIn("/health", route_paths)
        self.assertIn("/manifest", route_paths)
        self.assertIn("/load", route_paths)
        self.assertIn("/stats", route_paths)

    def test_load_response_uses_requested_graph_path(self) -> None:
        settings = RuntimeSettings(
            config_path=None,
            neo4j_uri="bolt://neo4j:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )
        summary = LoadSummary(
            scope_name="example",
            schema_version="0.1",
            entity_count=1,
            edge_count=1,
            resolved_edge_count=1,
            unresolved_edge_count=0,
            unresolved_target_count=0,
            clear_existing=True,
        )
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("repo_graph.api.load_graph_path", return_value=summary) as load_graph,
        ):
            payload = load_response(settings, LoadRequest(graph_path="graph.json"))

        self.assertEqual(payload["status"], "loaded")
        self.assertEqual(payload["summary"]["scope_name"], "example")
        load_graph.assert_called_once()


if __name__ == "__main__":
    unittest.main()
