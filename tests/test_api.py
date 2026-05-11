"""Tests for the Repo Graph API runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from repo_graph.api import (
    BuildLoadRequest,
    BuildRequest,
    LoadRequest,
    RuntimeSettings,
    SyncRequest,
    build_load_response,
    build_response,
    config_response,
    configured_sources_response,
    create_app,
    entity_response,
    health_payload,
    job_response,
    jobs_response,
    load_response,
    manifest_payload,
    neighbors_response,
    scope_response,
    search_entities_response,
    sources_response,
    submit_build_job,
    submit_build_load_job,
    submit_sync_job,
    sync_response,
    unresolved_edges_response,
)
from repo_graph.config import RepoGraphConfig, Source
from repo_graph.jobs import JobRegistry
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
        self.assertIn({"method": "GET", "path": "/config", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/sources/configured", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/sync", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/build", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/build-load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/sync", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/build", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/build-load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/jobs", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/jobs/{job_id}", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/scope", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/sources", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/stats", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/entities/search", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/entities/{entity_id}", "available": True}, payload["endpoints"])
        self.assertIn(
            {"method": "GET", "path": "/entities/{entity_id}/neighbors", "available": True},
            payload["endpoints"],
        )
        self.assertIn({"method": "GET", "path": "/edges/unresolved", "available": True}, payload["endpoints"])
        self.assertNotIn("password", str(payload).lower())

    def test_app_exposes_runtime_routes(self) -> None:
        app = create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None))
        route_paths = {route.path for route in app.routes}

        self.assertIn("/health", route_paths)
        self.assertIn("/manifest", route_paths)
        self.assertIn("/config", route_paths)
        self.assertIn("/sources/configured", route_paths)
        self.assertIn("/sync", route_paths)
        self.assertIn("/build", route_paths)
        self.assertIn("/build-load", route_paths)
        self.assertIn("/jobs/sync", route_paths)
        self.assertIn("/jobs/build", route_paths)
        self.assertIn("/jobs/build-load", route_paths)
        self.assertIn("/jobs", route_paths)
        self.assertIn("/jobs/{job_id}", route_paths)
        self.assertIn("/load", route_paths)
        self.assertIn("/scope", route_paths)
        self.assertIn("/sources", route_paths)
        self.assertIn("/stats", route_paths)
        self.assertIn("/entities/search", route_paths)
        self.assertIn("/entities/{entity_id}", route_paths)
        self.assertIn("/entities/{entity_id}/neighbors", route_paths)
        self.assertIn("/edges/unresolved", route_paths)

    def test_config_response_returns_summary(self) -> None:
        root = Path("/repo")
        config = RepoGraphConfig(
            name="test",
            config_path=root / "repo-graph.yaml",
            cache_dir=root / ".repo-graph/cache/repos",
            output_dir=root / ".repo-graph/output",
            sources=(Source(name="service", source_type="local_path", path=root / "service"),),
        )
        with patch("repo_graph.api.load_config", return_value=config) as load_config:
            payload = config_response(RuntimeSettings(config_path=root / "repo-graph.yaml"))

        self.assertEqual(payload["name"], "test")
        self.assertEqual(payload["source_count"], 1)
        load_config.assert_called_once()

    def test_configured_sources_response_wraps_source_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "service"
            source_dir.mkdir()
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(Source(name="service", source_type="local_path", path=source_dir),),
            )
            with patch("repo_graph.api.load_config", return_value=config):
                payload = configured_sources_response(RuntimeSettings(config_path=config.config_path))

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["ready_count"], 1)
        self.assertEqual(payload["problem_count"], 0)
        self.assertEqual(payload["items"][0]["name"], "service")
        self.assertTrue(payload["items"][0]["ready"])

    def test_sync_response_reports_source_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(Source(name="missing", source_type="local_path", path=root / "missing"),),
            )
            with patch("repo_graph.api.load_config", return_value=config):
                payload = sync_response(RuntimeSettings(config_path=config.config_path), SyncRequest())

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["failed_count"], 1)
        self.assertEqual(payload["items"][0]["sync"]["status"], "failed")
        self.assertIn("path_missing", payload["items"][0]["problems"])

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
            source_count=1,
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

    def test_build_response_writes_graph_output(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        graph_data = {"summary": {"entity_count": 1}, "entities": [], "edges": []}
        with (
            patch("repo_graph.api.load_config") as load_config,
            patch("repo_graph.api.build_graph") as build_graph,
            patch("pathlib.Path.write_text") as write_text,
            patch("pathlib.Path.mkdir") as mkdir,
        ):
            config = load_config.return_value
            config.config_path = Path("/repo/config/local-example.yaml")
            config.output_dir = Path("/repo/.repo-graph/output")
            build_graph.return_value.to_dict.return_value = graph_data

            payload = build_response(settings, BuildRequest(output_path="graph.json", strict=True))

        self.assertEqual(payload["status"], "built")
        self.assertEqual(payload["summary"], {"entity_count": 1})
        build_graph.assert_called_once()
        mkdir.assert_called_once()
        write_text.assert_called_once()

    def test_build_load_response_builds_then_loads_output(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        build_payload = {"status": "built", "output_path": "/repo/.repo-graph/output/graph.json", "summary": {}}
        load_payload = {"status": "loaded", "graph_path": "/repo/.repo-graph/output/graph.json", "summary": {}}
        with (
            patch("repo_graph.api.build_response", return_value=build_payload) as build,
            patch("repo_graph.api.load_response", return_value=load_payload) as load,
        ):
            payload = build_load_response(settings, BuildLoadRequest(clear_existing=False))

        self.assertEqual(payload["status"], "built_and_loaded")
        self.assertEqual(payload["build"], build_payload)
        self.assertEqual(payload["load"], load_payload)
        build.assert_called_once()
        load.assert_called_once()

    def test_submit_build_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api.build_response", return_value={"status": "built"}):
            job = submit_build_job(registry, settings, BuildRequest(strict=True))

        self.assertEqual(job["kind"], "build")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["strict"], True)
        self.assertEqual(job["result"], {"status": "built"})

    def test_submit_sync_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api.sync_response", return_value={"status": "synced"}):
            job = submit_sync_job(registry, settings, SyncRequest(config_path="config/local-example.yaml"))

        self.assertEqual(job["kind"], "sync")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["config_path"], "config/local-example.yaml")
        self.assertEqual(job["result"], {"status": "synced"})

    def test_submit_build_load_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api.build_load_response", return_value={"status": "built_and_loaded"}):
            job = submit_build_load_job(registry, settings, BuildLoadRequest(clear_existing=False))

        self.assertEqual(job["kind"], "build-load")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["clear_existing"], False)
        self.assertEqual(job["result"], {"status": "built_and_loaded"})

    def test_job_response_reads_registry_job(self) -> None:
        registry = JobRegistry(run_inline=True)
        created = registry.submit("build", {}, lambda: {"status": "built"})

        self.assertEqual(job_response(registry, created["job_id"]), created)

    def test_jobs_response_wraps_registry_jobs(self) -> None:
        registry = JobRegistry(run_inline=True)
        registry.submit("build", {}, lambda: {"status": "built"})

        payload = jobs_response(registry, "succeeded", "build", 10)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["kind"], "build")

    def test_scope_response_returns_loaded_scope(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        scope = {"loaded": True, "scope_name": "example", "sources": [{"name": "api-service"}]}
        with patch("repo_graph.api.read_graph_scope", return_value=scope):
            self.assertEqual(scope_response(settings), scope)

    def test_sources_response_wraps_scope_sources(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        scope = {
            "loaded": True,
            "scope_name": "example",
            "generated_at": "2026-05-11T00:00:00+00:00",
            "sources": [{"name": "api-service"}],
        }
        with patch("repo_graph.api.read_graph_scope", return_value=scope):
            payload = sources_response(settings)

        self.assertEqual(payload["items"], [{"name": "api-service"}])
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["loaded"])

    def test_search_entities_response_wraps_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {"entity_id": "entity-1", "name": "GET /accounts"}
        with patch("repo_graph.api.search_entities", return_value=[item]) as search:
            payload = search_entities_response(settings, "accounts", "api_route", "api-service", 10)

        self.assertEqual(payload, {"items": [item], "count": 1})
        search.assert_called_once()

    def test_entity_response_raises_for_missing_entity(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        with patch("repo_graph.api.get_entity", return_value=None), self.assertRaises(KeyError):
            entity_response(settings, "missing")

    def test_neighbors_response_rejects_depth_above_one(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with self.assertRaises(ValueError):
            neighbors_response(settings, "entity-1", "both", None, 2, 25)

    def test_unresolved_edges_response_wraps_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {"edge": {"edge_id": "edge-1"}}
        with patch("repo_graph.api.list_unresolved_edges", return_value=[item]) as unresolved:
            payload = unresolved_edges_response(settings, "api-service", "CALLS_SQL", 10)

        self.assertEqual(payload, {"items": [item], "count": 1})
        unresolved.assert_called_once()


if __name__ == "__main__":
    unittest.main()
