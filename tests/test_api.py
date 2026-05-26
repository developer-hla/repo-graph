"""Tests for the Repo Graph API runtime."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from repo_graph.api import (
    BuildLoadRequest,
    BuildRequest,
    LoadRequest,
    RefreshChangedRequest,
    RefreshRequest,
    RuntimeSettings,
    SnapshotStatusRequest,
    SyncRequest,
    build_load_response,
    build_response,
    config_response,
    configured_sources_response,
    create_app,
    database_reconciliation_report_response,
    entity_overview_response,
    entity_response,
    explore_response,
    health_payload,
    impact_response,
    interactions_report_response,
    job_response,
    jobs_response,
    load_response,
    manifest_payload,
    neighbors_response,
    refresh_changed_response,
    refresh_response,
    relationship_search_response,
    scope_response,
    search_entities_response,
    snapshot_status_response,
    source_file_snippet_response,
    source_overview_response,
    sources_response,
    submit_build_job,
    submit_build_load_job,
    submit_refresh_changed_job,
    submit_refresh_job,
    submit_snapshot_status_job,
    submit_sync_job,
    sync_response,
    ui_index_path,
    unresolved_edges_response,
    unresolved_report_response,
)
from repo_graph.config import RepoGraphConfig, Source
from repo_graph.jobs import JobRegistry
from repo_graph.storage import LoadSummary


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
        self.assertIn({"method": "GET", "path": "/ui", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/config", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/sources/configured", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/sync", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/build", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/build-load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/snapshot/status", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/refresh", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/sync", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/build", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/build-load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/snapshot-status", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/refresh", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/jobs/refresh-changed", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/jobs", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/jobs/{job_id}", "available": True}, payload["endpoints"])
        self.assertIn({"method": "POST", "path": "/load", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/scope", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/sources", "available": True}, payload["endpoints"])
        self.assertIn(
            {"method": "GET", "path": "/sources/{source_name}/overview", "available": True}, payload["endpoints"]
        )
        self.assertIn(
            {"method": "GET", "path": "/sources/{source_name}/files/snippet", "available": True},
            payload["endpoints"],
        )
        self.assertIn({"method": "GET", "path": "/stats", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/explore", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/entities/search", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/relationships/search", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/entities/{entity_id}", "available": True}, payload["endpoints"])
        self.assertIn(
            {"method": "GET", "path": "/entities/{entity_id}/overview", "available": True},
            payload["endpoints"],
        )
        self.assertIn(
            {"method": "GET", "path": "/entities/{entity_id}/neighbors", "available": True},
            payload["endpoints"],
        )
        self.assertIn(
            {"method": "GET", "path": "/entities/{entity_id}/impact", "available": True},
            payload["endpoints"],
        )
        self.assertIn({"method": "GET", "path": "/edges/unresolved", "available": True}, payload["endpoints"])
        self.assertIn({"method": "GET", "path": "/reports/interactions", "available": True}, payload["endpoints"])
        self.assertIn(
            {"method": "GET", "path": "/reports/database-reconciliation", "available": True}, payload["endpoints"]
        )
        self.assertIn({"method": "GET", "path": "/reports/unresolved", "available": True}, payload["endpoints"])
        self.assertNotIn("password", str(payload).lower())

    def test_app_exposes_runtime_routes(self) -> None:
        app = create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None))
        route_paths = {route.path for route in app.routes}

        self.assertIn("/ui/assets", route_paths)
        self.assertIn("/ui", route_paths)
        self.assertIn("/ui/", route_paths)
        self.assertIn("/health", route_paths)
        self.assertIn("/manifest", route_paths)
        self.assertIn("/config", route_paths)
        self.assertIn("/sources/configured", route_paths)
        self.assertIn("/sync", route_paths)
        self.assertIn("/build", route_paths)
        self.assertIn("/build-load", route_paths)
        self.assertIn("/snapshot/status", route_paths)
        self.assertIn("/refresh", route_paths)
        self.assertIn("/jobs/sync", route_paths)
        self.assertIn("/jobs/build", route_paths)
        self.assertIn("/jobs/build-load", route_paths)
        self.assertIn("/jobs/snapshot-status", route_paths)
        self.assertIn("/jobs/refresh", route_paths)
        self.assertIn("/jobs/refresh-changed", route_paths)
        self.assertIn("/jobs", route_paths)
        self.assertIn("/jobs/{job_id}", route_paths)
        self.assertIn("/load", route_paths)
        self.assertIn("/scope", route_paths)
        self.assertIn("/sources", route_paths)
        self.assertIn("/sources/{source_name}/overview", route_paths)
        self.assertIn("/sources/{source_name}/files/snippet", route_paths)
        self.assertIn("/stats", route_paths)
        self.assertIn("/explore", route_paths)
        self.assertIn("/entities/search", route_paths)
        self.assertIn("/relationships/search", route_paths)
        self.assertIn("/entities/{entity_id}", route_paths)
        self.assertIn("/entities/{entity_id}/overview", route_paths)
        self.assertIn("/entities/{entity_id}/neighbors", route_paths)
        self.assertIn("/entities/{entity_id}/impact", route_paths)
        self.assertIn("/edges/unresolved", route_paths)
        self.assertIn("/reports/interactions", route_paths)
        self.assertIn("/reports/database-reconciliation", route_paths)
        self.assertIn("/reports/unresolved", route_paths)

    def test_ui_shell_and_static_assets_are_served(self) -> None:
        client = TestClient(create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None)))

        shell = client.get("/ui")
        script = client.get("/ui/assets/app.js")
        styles = client.get("/ui/assets/styles.css")

        self.assertEqual(shell.status_code, 200)
        self.assertIn("Repo Graph", shell.text)
        self.assertIn("#overview", shell.text)
        self.assertIn("#search", shell.text)
        self.assertIn("#impact", shell.text)
        self.assertIn("Blast Radius", shell.text)
        self.assertIn("#unresolved", shell.text)
        self.assertIn("#database", shell.text)
        self.assertIn("#jobs", shell.text)
        self.assertIn('data-form="global-search"', shell.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("renderOverview", script.text)
        self.assertIn("renderDashboard", script.text)
        self.assertIn("renderExplore", script.text)
        self.assertIn("renderSource", script.text)
        self.assertIn("renderEntity", script.text)
        self.assertIn("renderRelationships", script.text)
        self.assertIn("renderDatabaseReconciliation", script.text)
        self.assertIn("/reports/database-reconciliation", script.text)
        self.assertIn("databaseClassificationGroupsTable", script.text)
        self.assertIn("data-database-code-source", script.text)
        self.assertIn("data-database-source", script.text)
        self.assertIn("impactPathEvidenceTable", script.text)
        self.assertIn("impactStartResultsTable", script.text)
        self.assertIn('data-form="impact-search"', script.text)
        self.assertIn("data-impact-start-type", script.text)
        self.assertIn("data-impact-start-id", script.text)
        self.assertIn("advancedControls", script.text)
        self.assertIn("data-impact-direction", script.text)
        self.assertIn("unresolvedClassificationSections", script.text)
        self.assertIn("unresolvedSourceHotspotsTable", script.text)
        self.assertIn("data-search-query", script.text)
        self.assertIn("coverageWarningsPanel", script.text)
        self.assertIn("data-unresolved-filter", script.text)
        self.assertIn("parseHashRoute", script.text)
        self.assertIn("hydrateRouteState", script.text)
        self.assertIn("writeHashRoute", script.text)
        self.assertIn("hashForRoute", script.text)
        self.assertIn("routeParams", script.text)
        self.assertIn("data-source-name", script.text)
        self.assertIn("data-entity-source-type", script.text)
        self.assertIn("data-relationship-filter", script.text)
        self.assertIn("data-snippet-source", script.text)
        self.assertIn("/relationships/search", script.text)
        self.assertIn("/files/snippet", script.text)
        self.assertIn("/overview", script.text)
        self.assertIn("data-search-type", script.text)
        self.assertIn('data-snapshot-action="status"', script.text)
        self.assertIn("/snapshot/status", script.text)
        self.assertIn('data-job-action="refresh"', script.text)
        self.assertIn('data-job-action="refresh-changed"', script.text)
        self.assertIn("pollJob", script.text)
        self.assertEqual(styles.status_code, 200)
        self.assertIn(".app-shell", styles.text)
        self.assertIn(".global-search", styles.text)
        self.assertIn(".advanced-controls", styles.text)
        self.assertIn(".triage-card", styles.text)
        self.assertIn(".coverage-strip", styles.text)
        self.assertIn(".action-grid", styles.text)
        self.assertIn(".refresh-summary", styles.text)

    def test_ui_index_path_points_to_shell(self) -> None:
        self.assertTrue(ui_index_path().exists())
        self.assertEqual(ui_index_path().name, "index.html")

    def test_config_response_returns_summary(self) -> None:
        root = Path("/repo")
        config = RepoGraphConfig(
            name="test",
            config_path=root / "repo-graph.yaml",
            cache_dir=root / ".repo-graph/cache/repos",
            output_dir=root / ".repo-graph/output",
            sources=(Source(name="service", source_type="local_path", path=root / "service"),),
        )
        with patch("repo_graph.api_runtime.settings.load_config", return_value=config) as load_config:
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
            with patch("repo_graph.api_runtime.settings.load_config", return_value=config):
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
            with patch("repo_graph.api_runtime.settings.load_config", return_value=config):
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
            patch("repo_graph.api_runtime.config_workflows.load_graph_path", return_value=summary) as load_graph,
        ):
            payload = load_response(settings, LoadRequest(graph_path="graph.json"))

        self.assertEqual(payload["status"], "loaded")
        self.assertEqual(payload["summary"]["scope_name"], "example")
        load_graph.assert_called_once()

    def test_build_response_writes_graph_output(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        graph_data = {"summary": {"entity_count": 1}, "entities": [], "edges": []}
        with (
            patch("repo_graph.api_runtime.settings.load_config") as load_config,
            patch("repo_graph.api_runtime.config_workflows.build_graph") as build_graph,
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
            patch("repo_graph.api_runtime.config_workflows.build_response", return_value=build_payload) as build,
            patch("repo_graph.api_runtime.config_workflows.load_response", return_value=load_payload) as load,
        ):
            payload = build_load_response(settings, BuildLoadRequest(clear_existing=False))

        self.assertEqual(payload["status"], "built_and_loaded")
        self.assertEqual(payload["build"], build_payload)
        self.assertEqual(payload["load"], load_payload)
        build.assert_called_once()
        load.assert_called_once()

    def test_refresh_response_runs_incremental_refresh(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        refresh_payload = {
            "status": "refreshed",
            "output": "/repo/.repo-graph/output/graph.json",
            "changes": {"changed_sources": ["service"]},
        }
        with (
            patch("repo_graph.api_runtime.settings.load_config") as load_config,
            patch("repo_graph.api_runtime.config_workflows.refresh_graph", return_value=refresh_payload) as refresh,
        ):
            config = load_config.return_value
            config.config_path = Path("/repo/config/local-example.yaml")
            config.output_dir = Path("/repo/.repo-graph/output")

            payload = refresh_response(settings, RefreshRequest(sync=True, strict=True))

        self.assertEqual(payload, refresh_payload)
        refresh.assert_called_once()
        self.assertTrue(refresh.call_args.kwargs["sync_first"])
        self.assertTrue(refresh.call_args.kwargs["strict"])
        self.assertFalse(refresh.call_args.kwargs["load"])

    def test_refresh_response_rejects_invalid_max_file_bytes(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        with patch("repo_graph.api_runtime.settings.load_config") as load_config:
            config = load_config.return_value
            config.config_path = Path("/repo/config/local-example.yaml")
            config.output_dir = Path("/repo/.repo-graph/output")

            with self.assertRaises(ValueError):
                refresh_response(settings, RefreshRequest(max_file_bytes=0))

    def test_refresh_changed_response_skips_when_snapshot_has_no_changes(self) -> None:
        root = Path("/repo")
        settings = RuntimeSettings(config_path=root / "repo-graph.yaml", neo4j_uri=None, neo4j_user=None)
        config = RepoGraphConfig(
            name="test",
            config_path=root / "repo-graph.yaml",
            cache_dir=root / ".repo-graph/cache/repos",
            output_dir=root / ".repo-graph/output",
            sources=(Source(name="service", source_type="local_path", path=root / "service"),),
        )
        snapshot_payload = {
            "count": 1,
            "changed_count": 0,
            "unchanged_count": 1,
            "items": [{"source_name": "service", "changed": False, "status": "unchanged"}],
        }
        with (
            patch("repo_graph.api_runtime.settings.load_config", return_value=config),
            patch("repo_graph.api_runtime.config_workflows.snapshot_status", return_value=snapshot_payload) as snapshot,
            patch("repo_graph.api_runtime.config_workflows.refresh_graph") as refresh,
        ):
            payload = refresh_changed_response(settings, RefreshChangedRequest(sync=True))

        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(payload["reason"], "no_changed_sources")
        self.assertEqual(payload["changed_sources"], [])
        self.assertEqual(payload["load"]["action"], "skipped")
        self.assertEqual(payload["neo4j_load_mode"], "skipped")
        snapshot.assert_called_once_with(config, sync_first=True, max_file_bytes=1000000)
        refresh.assert_not_called()

    def test_refresh_changed_response_refreshes_and_loads_changed_sources(self) -> None:
        root = Path("/repo")
        settings = RuntimeSettings(
            config_path=root / "repo-graph.yaml",
            neo4j_uri="bolt://neo4j:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )
        config = RepoGraphConfig(
            name="test",
            config_path=root / "repo-graph.yaml",
            cache_dir=root / ".repo-graph/cache/repos",
            output_dir=root / ".repo-graph/output",
            sources=(Source(name="service", source_type="local_path", path=root / "service"),),
        )
        snapshot_payload = {
            "count": 1,
            "changed_count": 1,
            "unchanged_count": 0,
            "items": [{"source_name": "service", "changed": True, "status": "changed"}],
        }
        refresh_payload = {
            "status": "refreshed",
            "changes": {"changed_count": 1, "changed_sources": ["service"]},
            "cache": {"rebuilt_count": 1, "reused_count": 2},
            "load": {"action": "replace_sources", "reason": "changed_sources", "replace_sources": ["service"]},
        }
        with (
            patch("repo_graph.api_runtime.settings.load_config", return_value=config),
            patch("repo_graph.api_runtime.config_workflows.snapshot_status", return_value=snapshot_payload) as snapshot,
            patch("repo_graph.api_runtime.config_workflows.refresh_graph", return_value=refresh_payload) as refresh,
        ):
            payload = refresh_changed_response(
                settings,
                RefreshChangedRequest(sync=True, strict=True, max_file_bytes=1024),
            )

        self.assertEqual(payload["status"], "refreshed")
        self.assertEqual(payload["changed_sources"], ["service"])
        self.assertEqual(payload["neo4j_load_mode"], "replace_sources")
        self.assertEqual(payload["rebuilt_count"], 1)
        self.assertEqual(payload["reused_count"], 2)
        self.assertEqual(payload["refresh"], refresh_payload)
        snapshot.assert_called_once_with(config, sync_first=True, max_file_bytes=1024)
        refresh.assert_called_once()
        self.assertFalse(refresh.call_args.kwargs["sync_first"])
        self.assertTrue(refresh.call_args.kwargs["strict"])
        self.assertTrue(refresh.call_args.kwargs["load"])
        self.assertIsNotNone(refresh.call_args.kwargs["settings"])

    def test_snapshot_status_response_compares_configured_sources(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        snapshot_payload = {"count": 1, "changed_count": 1, "items": [{"source_name": "service"}]}
        with (
            patch("repo_graph.api_runtime.settings.load_config") as load_config,
            patch("repo_graph.api_runtime.config_workflows.snapshot_status", return_value=snapshot_payload) as compare,
        ):
            config = load_config.return_value

            payload = snapshot_status_response(
                settings,
                SnapshotStatusRequest(sync=True, max_file_bytes=1024),
            )

        self.assertEqual(payload, snapshot_payload)
        compare.assert_called_once_with(config, sync_first=True, max_file_bytes=1024)

    def test_snapshot_status_response_rejects_invalid_max_file_bytes(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        with patch("repo_graph.api_runtime.settings.load_config"), self.assertRaises(ValueError):
            snapshot_status_response(settings, SnapshotStatusRequest(max_file_bytes=0))

    def test_submit_build_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api_runtime.config_workflows.build_response", return_value={"status": "built"}):
            job = submit_build_job(registry, settings, BuildRequest(strict=True))

        self.assertEqual(job["kind"], "build")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["strict"], True)
        self.assertEqual(job["result"], {"status": "built"})

    def test_submit_sync_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api_runtime.config_workflows.sync_response", return_value={"status": "synced"}):
            job = submit_sync_job(registry, settings, SyncRequest(config_path="config/local-example.yaml"))

        self.assertEqual(job["kind"], "sync")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["config_path"], "config/local-example.yaml")
        self.assertEqual(job["result"], {"status": "synced"})

    def test_submit_build_load_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch(
            "repo_graph.api_runtime.config_workflows.build_load_response", return_value={"status": "built_and_loaded"}
        ):
            job = submit_build_load_job(registry, settings, BuildLoadRequest(clear_existing=False))

        self.assertEqual(job["kind"], "build-load")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["clear_existing"], False)
        self.assertEqual(job["result"], {"status": "built_and_loaded"})

    def test_submit_refresh_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api_runtime.config_workflows.refresh_response", return_value={"status": "refreshed"}):
            job = submit_refresh_job(registry, settings, RefreshRequest(load=True))

        self.assertEqual(job["kind"], "refresh")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["load"], True)
        self.assertEqual(job["result"], {"status": "refreshed"})

    def test_submit_refresh_changed_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch(
            "repo_graph.api_runtime.config_workflows.refresh_changed_response", return_value={"status": "skipped"}
        ):
            job = submit_refresh_changed_job(registry, settings, RefreshChangedRequest(sync=True))

        self.assertEqual(job["kind"], "refresh-changed")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["sync"], True)
        self.assertEqual(job["result"], {"status": "skipped"})

    def test_submit_snapshot_status_job_runs_through_registry(self) -> None:
        settings = RuntimeSettings(config_path=Path("config/local-example.yaml"))
        registry = JobRegistry(run_inline=True)
        with patch("repo_graph.api_runtime.config_workflows.snapshot_status_response", return_value={"count": 1}):
            job = submit_snapshot_status_job(registry, settings, SnapshotStatusRequest(sync=True))

        self.assertEqual(job["kind"], "snapshot-status")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"]["sync"], True)
        self.assertEqual(job["result"], {"count": 1})

    def test_snapshot_status_endpoint_rejects_unknown_request_fields(self) -> None:
        client = TestClient(create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None)))

        response = client.post("/snapshot/status", json={"unknown": True})

        self.assertEqual(response.status_code, 422)

    def test_snapshot_status_endpoint_returns_snapshot_response(self) -> None:
        client = TestClient(create_app(RuntimeSettings(config_path=Path("config/local-example.yaml"))))
        with patch(
            "repo_graph.api_runtime.config_workflows.snapshot_status_response", return_value={"count": 1}
        ) as compare:
            response = client.post("/snapshot/status", json={"sync": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"count": 1})
        compare.assert_called_once()

    def test_snapshot_status_job_endpoint_submits_job(self) -> None:
        registry = JobRegistry(run_inline=True)
        client = TestClient(create_app(RuntimeSettings(config_path=Path("config/local-example.yaml")), registry))
        with patch("repo_graph.api_runtime.config_workflows.snapshot_status_response", return_value={"count": 1}):
            response = client.post("/jobs/snapshot-status", json={"sync": True})

        payload = response.json()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["kind"], "snapshot-status")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["request"]["sync"], True)
        self.assertEqual(payload["result"], {"count": 1})

    def test_refresh_endpoint_rejects_unknown_request_fields(self) -> None:
        client = TestClient(create_app(RuntimeSettings(config_path=None, neo4j_uri=None, neo4j_user=None)))

        response = client.post("/refresh", json={"unknown": True})

        self.assertEqual(response.status_code, 422)

    def test_refresh_endpoint_returns_refresh_response(self) -> None:
        client = TestClient(create_app(RuntimeSettings(config_path=Path("config/local-example.yaml"))))
        with patch(
            "repo_graph.api_runtime.config_workflows.refresh_response", return_value={"status": "refreshed"}
        ) as refresh:
            response = client.post("/refresh", json={"strict": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "refreshed"})
        refresh.assert_called_once()

    def test_refresh_job_endpoint_submits_refresh_job(self) -> None:
        registry = JobRegistry(run_inline=True)
        client = TestClient(create_app(RuntimeSettings(config_path=Path("config/local-example.yaml")), registry))
        with patch("repo_graph.api_runtime.config_workflows.refresh_response", return_value={"status": "refreshed"}):
            response = client.post("/jobs/refresh", json={"load": True})

        payload = response.json()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["kind"], "refresh")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["request"]["load"], True)
        self.assertEqual(payload["result"], {"status": "refreshed"})

    def test_refresh_changed_job_endpoint_submits_refresh_changed_job(self) -> None:
        registry = JobRegistry(run_inline=True)
        client = TestClient(create_app(RuntimeSettings(config_path=Path("config/local-example.yaml")), registry))
        with patch(
            "repo_graph.api_runtime.config_workflows.refresh_changed_response", return_value={"status": "skipped"}
        ):
            response = client.post("/jobs/refresh-changed", json={"sync": True})

        payload = response.json()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["kind"], "refresh-changed")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["request"]["sync"], True)
        self.assertEqual(payload["result"], {"status": "skipped"})

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
        with patch("repo_graph.api_runtime.query_responses.read_graph_scope", return_value=scope):
            self.assertEqual(scope_response(settings), scope)

    def test_explore_response_returns_graph_overview(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        overview = {"loaded": True, "entity_types": [{"entity_type": "api_route", "entity_count": 3}]}

        with patch(
            "repo_graph.api_runtime.query_responses.read_graph_overview", return_value=overview
        ) as read_overview:
            self.assertEqual(explore_response(settings, 25), overview)

        read_overview.assert_called_once()
        self.assertEqual(read_overview.call_args.kwargs["limit"], 25)

    def test_source_overview_response_adds_unresolved_report(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        overview = {
            "source": {"name": "api-service"},
            "summary": {"entity_count": 1},
            "entity_types": [],
            "edge_types": [],
        }
        unresolved = {
            "edge": {
                "edge_id": "edge-1",
                "edge_type": "CALLS_SQL",
                "to_type": "stored_procedure",
                "to_name": "dbo.load",
                "source_name": "api-service",
                "resolved": False,
                "properties": {},
            }
        }

        with (
            patch(
                "repo_graph.api_runtime.query_responses.read_source_overview", return_value=overview
            ) as read_overview,
            patch(
                "repo_graph.api_runtime.query_responses.list_unresolved_edges", return_value=[unresolved]
            ) as unresolved_edges,
        ):
            payload = source_overview_response(settings, "api-service", 10)

        self.assertEqual(payload["source"], {"name": "api-service"})
        self.assertEqual(payload["unresolved_report"]["summary"]["unresolved_edge_count"], 1)
        read_overview.assert_called_once()
        self.assertEqual(read_overview.call_args.kwargs["limit"], 10)
        self.assertIn("CALLS_SQL", read_overview.call_args.kwargs["use_edge_types"])
        unresolved_edges.assert_called_once()
        self.assertEqual(unresolved_edges.call_args.kwargs["source_name"], "api-service")

    def test_source_overview_response_raises_for_missing_source(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with (
            patch("repo_graph.api_runtime.query_responses.read_source_overview", return_value=None),
            self.assertRaises(KeyError),
        ):
            source_overview_response(settings, "missing", 10)

    def test_source_file_snippet_response_reads_context_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "service"
            source_dir.mkdir()
            (source_dir / "src").mkdir()
            (source_dir / "src" / "app.py").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(Source(name="service", source_type="local_path", path=source_dir),),
            )

            with patch("repo_graph.api_runtime.source_files.load_config", return_value=config):
                payload = source_file_snippet_response(
                    RuntimeSettings(config_path=config.config_path),
                    "service",
                    "src/app.py",
                    line=3,
                    context=1,
                )

        self.assertEqual(payload["source_name"], "service")
        self.assertEqual(payload["file_path"], "src/app.py")
        self.assertEqual(payload["start_line"], 2)
        self.assertEqual(payload["end_line"], 4)
        self.assertEqual([item["text"] for item in payload["lines"]], ["two", "three", "four"])
        self.assertTrue(payload["lines"][1]["highlight"])

    def test_source_file_snippet_response_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "service"
            source_dir.mkdir()
            (root / "secret.txt").write_text("secret\n", encoding="utf-8")
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(Source(name="service", source_type="local_path", path=source_dir),),
            )

            with (
                patch("repo_graph.api_runtime.source_files.load_config", return_value=config),
                self.assertRaisesRegex(ValueError, "escapes"),
            ):
                source_file_snippet_response(
                    RuntimeSettings(config_path=config.config_path),
                    "service",
                    "../secret.txt",
                    line=1,
                    context=1,
                )

    def test_sources_response_wraps_scope_sources(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        scope = {
            "loaded": True,
            "scope_name": "example",
            "generated_at": "2026-05-11T00:00:00+00:00",
            "sources": [{"name": "api-service"}],
        }
        with patch("repo_graph.api_runtime.query_responses.read_graph_scope", return_value=scope):
            payload = sources_response(settings)

        self.assertEqual(payload["items"], [{"name": "api-service"}])
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["loaded"])

    def test_search_entities_response_wraps_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {"entity_id": "entity-1", "name": "GET /accounts"}
        with patch("repo_graph.api_runtime.query_responses.search_entities", return_value=[item]) as search:
            payload = search_entities_response(settings, "accounts", "api_route", "api-service", 10)

        self.assertEqual(payload, {"items": [item], "count": 1})
        search.assert_called_once()

    def test_relationship_search_response_groups_evidence(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {
            "from_entity": {"entity_id": "entity-1", "entity_type": "api_route", "source_name": "api-service"},
            "edge": {"edge_id": "edge-1", "edge_type": "CALLS_SQL", "resolved": True},
            "target": {"entity_id": "entity-2", "entity_type": "stored_procedure", "source_name": "database"},
            "from_source": "api-service",
            "to_source": "database",
            "from_type": "api_route",
            "to_type": "stored_procedure",
        }

        with patch("repo_graph.api_runtime.query_responses.search_relationships", return_value=[item]) as search:
            payload = relationship_search_response(
                settings,
                "api-service",
                "database",
                "CALLS_SQL",
                "api_route",
                "stored_procedure",
                True,
                25,
            )

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["filters"]["from_source"], "api-service")
        self.assertEqual(payload["filters"]["resolved"], True)
        self.assertEqual(payload["groups"][0]["edge_type"], "CALLS_SQL")
        self.assertEqual(payload["groups"][0]["from_source"], "api-service")
        self.assertEqual(payload["groups"][0]["to_source"], "database")
        search.assert_called_once()
        self.assertEqual(search.call_args.kwargs["edge_type"], "CALLS_SQL")
        self.assertEqual(search.call_args.kwargs["resolved"], True)

    def test_entity_response_raises_for_missing_entity(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        with patch("repo_graph.api_runtime.query_responses.get_entity", return_value=None), self.assertRaises(KeyError):
            entity_response(settings, "missing")

    def test_entity_overview_response_groups_direct_relationships(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        entity = {
            "entity_id": "entity-1",
            "entity_type": "api_route",
            "name": "GET /accounts",
            "source_name": "api-service",
        }
        incoming = [
            {
                "direction": "in",
                "depth": 1,
                "edge": {"edge_type": "CALLS_HTTP", "source_name": "web-service"},
                "neighbor": {"entity_id": "entity-2", "entity_type": "service", "source_name": "web-service"},
            }
        ]
        outgoing = [
            {
                "direction": "out",
                "depth": 1,
                "edge": {"edge_type": "CALLS_SQL", "source_name": "api-service"},
                "neighbor": {"target_id": "target-1", "target_type": "stored_procedure", "name": "dbo.load"},
            }
        ]

        with (
            patch("repo_graph.api_runtime.query_responses.get_entity", return_value=entity),
            patch(
                "repo_graph.api_runtime.query_responses.get_entity_neighbors", side_effect=[incoming, outgoing]
            ) as neighbors,
            patch("repo_graph.api_runtime.coverage.list_unresolved_edges", return_value=[]) as unresolved,
        ):
            payload = entity_overview_response(settings, "entity-1", 20)

        self.assertEqual(payload["entity"], entity)
        self.assertEqual(payload["coverage"]["status"], "ok")
        self.assertFalse(payload["coverage"]["edge_sample_truncated"])
        unresolved.assert_called_once()
        self.assertEqual(unresolved.call_args.kwargs["source_name"], "api-service")
        self.assertEqual(payload["incoming"]["count"], 1)
        self.assertEqual(payload["incoming"]["groups"][0]["source_name"], "web-service")
        self.assertEqual(payload["incoming"]["groups"][0]["neighbor_type"], "service")
        self.assertEqual(payload["outgoing"]["groups"][0]["edge_type"], "CALLS_SQL")
        self.assertEqual(payload["outgoing"]["groups"][0]["source_name"], "api-service")
        self.assertEqual(payload["outgoing"]["groups"][0]["neighbor_type"], "stored_procedure")
        self.assertEqual(neighbors.call_args_list[0].kwargs["direction"], "in")
        self.assertEqual(neighbors.call_args_list[1].kwargs["direction"], "out")
        self.assertEqual(neighbors.call_args_list[0].kwargs["limit"], 20)

    def test_entity_overview_response_adds_coverage_warnings(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        entity = {
            "entity_id": "entity-1",
            "entity_type": "api_route",
            "name": "GET /accounts",
            "source_name": "api-service",
        }
        unresolved_items = [
            {
                "edge": {
                    "edge_id": "edge-1",
                    "edge_type": "CALLS_SQL",
                    "to_type": "stored_procedure",
                    "to_name": "dbo.load",
                    "source_name": "api-service",
                    "resolved": False,
                    "properties": {},
                }
            },
            {
                "edge": {
                    "edge_id": "edge-2",
                    "edge_type": "IMPORTS",
                    "to_type": "module",
                    "to_name": "internal.module",
                    "source_name": "api-service",
                    "resolved": False,
                    "properties": {},
                }
            },
        ]

        with (
            patch("repo_graph.api_runtime.query_responses.get_entity", return_value=entity),
            patch("repo_graph.api_runtime.query_responses.get_entity_neighbors", return_value=[]),
            patch("repo_graph.api_runtime.coverage.list_unresolved_edges", return_value=unresolved_items),
        ):
            payload = entity_overview_response(settings, "entity-1", 20)

        self.assertEqual(payload["coverage"]["status"], "warning")
        self.assertEqual(payload["coverage"]["source_name"], "api-service")
        self.assertEqual(payload["coverage"]["unresolved_edge_count"], 2)
        self.assertFalse(payload["coverage"]["edge_sample_truncated"])
        self.assertEqual(payload["coverage"]["warnings"][0]["code"], "missing_source")
        self.assertEqual(payload["coverage"]["warnings"][1]["code"], "parser_gap")
        self.assertTrue(any(warning["code"] == "unresolved_sql_calls" for warning in payload["coverage"]["warnings"]))

    def test_entity_overview_response_raises_for_missing_entity(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with patch("repo_graph.api_runtime.query_responses.get_entity", return_value=None), self.assertRaises(KeyError):
            entity_overview_response(settings, "missing", 10)

    def test_neighbors_response_passes_depth_to_storage(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {"edge": {"edge_id": "edge-1"}, "neighbor": {"entity_id": "entity-2"}}

        with patch("repo_graph.api_runtime.query_responses.get_entity_neighbors", return_value=[item]) as neighbors:
            payload = neighbors_response(settings, "entity-1", "both", "CALLS_SQL", 2, 25)

        self.assertEqual(payload["depth"], 2)
        self.assertEqual(payload["count"], 1)
        neighbors.assert_called_once()
        self.assertEqual(neighbors.call_args.kwargs["depth"], 2)

    def test_impact_response_groups_neighbors_by_source(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        entity = {"entity_id": "entity-1", "name": "dbo.GetThing", "source_name": "database"}
        items = [
            {
                "depth": 1,
                "edge": {"edge_type": "CALLS_SQL", "source_name": "api-service"},
                "neighbor": {"entity_id": "file-1", "entity_type": "file", "source_name": "api-service"},
            },
            {
                "depth": 2,
                "edge": {"edge_type": "IMPORTS", "source_name": "worker"},
                "neighbor": {"entity_id": "file-2", "entity_type": "file", "source_name": "worker"},
            },
        ]

        with (
            patch("repo_graph.api_runtime.query_responses.entity_response", return_value=entity),
            patch("repo_graph.api_runtime.query_responses.get_entity_neighbors", return_value=items) as neighbors,
            patch("repo_graph.api_runtime.coverage.list_unresolved_edges", return_value=[]),
        ):
            payload = impact_response(settings, "entity-1", "in", "CALLS_SQL", 2, 25)

        self.assertEqual(payload["entity"], entity)
        self.assertEqual(payload["coverage"]["status"], "ok")
        self.assertEqual(payload["profile"], "impact")
        self.assertIsNone(payload["allowed_edge_types"])
        self.assertEqual(payload["affected_source_count"], 2)
        self.assertEqual(payload["affected_sources"][0]["source_name"], "api-service")
        self.assertEqual(payload["affected_sources"][0]["edge_types"], ["CALLS_SQL"])
        self.assertEqual(payload["path_groups"][0]["source_name"], "api-service")
        self.assertEqual(payload["path_groups"][0]["edge_type"], "CALLS_SQL")
        neighbors.assert_called_once()
        self.assertEqual(neighbors.call_args.kwargs["direction"], "in")
        self.assertEqual(neighbors.call_args.kwargs["edge_type"], "CALLS_SQL")
        self.assertIsNone(neighbors.call_args.kwargs["allowed_edge_types"])
        self.assertEqual(neighbors.call_args.kwargs["depth"], 2)

    def test_impact_response_defaults_to_dependency_impact_edges(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with (
            patch("repo_graph.api_runtime.query_responses.entity_response", return_value={"entity_id": "entity-1"}),
            patch("repo_graph.api_runtime.query_responses.get_entity_neighbors", return_value=[]) as neighbors,
        ):
            payload = impact_response(settings, "entity-1", "in", None, 2, 25)

        self.assertEqual(payload["profile"], "impact")
        self.assertIn("CALLS_SQL", payload["allowed_edge_types"])
        self.assertIn("IMPORTS", payload["allowed_edge_types"])
        self.assertNotIn("CONTAINS_FILE", payload["allowed_edge_types"])
        self.assertEqual(neighbors.call_args.kwargs["allowed_edge_types"], set(payload["allowed_edge_types"]))

    def test_impact_response_supports_structural_profile(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with (
            patch("repo_graph.api_runtime.query_responses.entity_response", return_value={"entity_id": "entity-1"}),
            patch("repo_graph.api_runtime.query_responses.get_entity_neighbors", return_value=[]) as neighbors,
        ):
            payload = impact_response(settings, "entity-1", "in", None, 2, 25, "structural")

        self.assertEqual(payload["profile"], "structural")
        self.assertIn("CONTAINS_FILE", payload["allowed_edge_types"])
        self.assertIn("DEFINES", payload["allowed_edge_types"])
        self.assertNotIn("CALLS_SQL", payload["allowed_edge_types"])
        self.assertEqual(neighbors.call_args.kwargs["allowed_edge_types"], set(payload["allowed_edge_types"]))

    def test_impact_response_rejects_unknown_profile(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")

        with self.assertRaises(ValueError):
            impact_response(settings, "entity-1", "in", None, 2, 25, "unknown")

    def test_unresolved_edges_response_wraps_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {"edge": {"edge_id": "edge-1"}}
        with patch("repo_graph.api_runtime.query_responses.list_unresolved_edges", return_value=[item]) as unresolved:
            payload = unresolved_edges_response(settings, "api-service", "CALLS_SQL", 10)

        self.assertEqual(payload, {"items": [item], "count": 1})
        unresolved.assert_called_once()

    def test_unresolved_report_response_groups_unresolved_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {
            "edge": {
                "edge_id": "edge-1",
                "edge_type": "CALLS_SQL",
                "to_type": "stored_procedure",
                "to_name": "dbo.load",
                "source_name": "api-service",
                "resolved": False,
                "properties": {},
            }
        }
        with patch("repo_graph.api_runtime.report_responses.list_unresolved_edges", return_value=[item]) as unresolved:
            payload = unresolved_report_response(settings, "api-service", "CALLS_SQL", 10, 2)

        self.assertEqual(payload["summary"]["unresolved_edge_count"], 1)
        self.assertEqual(payload["items"][0]["classification"], "likely_missing_source")
        self.assertEqual(payload["classification_groups"][0]["classification"], "likely_missing_source")
        self.assertEqual(payload["source_hotspots"][0]["source_name"], "api-service")
        self.assertEqual(payload["target_hotspots"][0]["to_name"], "dbo.load")
        self.assertEqual(payload["edge_sample_limit"], 1000)
        self.assertFalse(payload["edge_sample_truncated"])
        unresolved.assert_called_once()

    def test_interactions_report_response_groups_interaction_items(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        item = {
            "to_source": "inventory-service",
            "edge": {
                "edge_id": "edge-1",
                "edge_type": "CALLS_SERVICE",
                "to_type": "service",
                "to_name": "inventory-service",
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
            },
        }
        with patch(
            "repo_graph.api_runtime.report_responses.search_relationships_by_edge_types", return_value=[item]
        ) as search:
            payload = interactions_report_response(settings, "api-service", "inventory-service", None, 10, 2)

        self.assertEqual(payload["summary"]["interaction_edge_count"], 1)
        self.assertEqual(payload["items"][0]["from_source"], "api-service")
        self.assertEqual(payload["items"][0]["target_source"], "inventory-service")
        self.assertEqual(payload["edge_sample_limit"], 1000)
        self.assertFalse(payload["edge_sample_truncated"])
        search.assert_called_once()

    def test_database_reconciliation_report_response_groups_drift(self) -> None:
        settings = RuntimeSettings(neo4j_uri="bolt://neo4j:7687", neo4j_user="neo4j", neo4j_password="password")
        entities = [
            {
                "entity_id": "entity-db",
                "entity_type": "sql_table",
                "name": "dbo.Customers",
                "source_name": "current-db",
                "properties": {"full_name": "dbo.Customers", "schema_state": "current_database"},
            }
        ]
        items = [
            {
                "edge": {
                    "edge_id": "edge-1",
                    "edge_type": "CALLS_SQL",
                    "to_type": "stored_procedure",
                    "to_name": "dbo.LoadCustomer",
                    "source_name": "api-service",
                    "resolved": False,
                    "properties": {},
                }
            }
        ]
        with (
            patch(
                "repo_graph.api_runtime.report_responses.list_entities_by_types", return_value=entities
            ) as list_entities,
            patch(
                "repo_graph.api_runtime.report_responses.search_relationships_by_edge_types", return_value=items
            ) as search,
        ):
            payload = database_reconciliation_report_response(settings, "api-service", "current-db", 10, 2)

        self.assertEqual(payload["summary"]["current_database_entity_count"], 1)
        self.assertEqual(payload["items"][0]["classification"], "code_only_reference")
        self.assertEqual(payload["entity_sample_limit"], 1000)
        self.assertFalse(payload["entity_sample_truncated"])
        self.assertEqual(payload["edge_sample_limit"], 1000)
        self.assertFalse(payload["edge_sample_truncated"])
        list_entities.assert_called_once()
        search.assert_called_once()


if __name__ == "__main__":
    unittest.main()
