"""Tests for Neo4j storage record shaping."""

from __future__ import annotations

import unittest

from repo_graph.storage.neo4j import (
    edge_payload,
    edge_record,
    entity_payload,
    entity_record,
    graph_node_payload,
    load_summary,
    normalize_direction,
    normalize_limit,
    sanitize_relationship_type,
    scope_payload,
    source_payload,
    source_record,
    target_payload,
    unloaded_scope_payload,
    unresolved_target_records,
)


class Neo4jStorageTests(unittest.TestCase):
    def test_sanitize_relationship_type_returns_safe_cypher_type(self) -> None:
        self.assertEqual(sanitize_relationship_type("reads sql-object"), "READS_SQL_OBJECT")
        self.assertEqual(sanitize_relationship_type("123 edge"), "EDGE_123_EDGE")
        self.assertEqual(sanitize_relationship_type(""), "RELATED_TO")

    def test_entity_record_flattens_properties(self) -> None:
        record = entity_record(
            {
                "entity_id": "entity-1",
                "entity_type": "sql_table",
                "name": "dbo.Account",
                "source_name": "database-project",
                "aliases": ["Account"],
                "properties": {"schema": "dbo", "full_name": "dbo.Account"},
            }
        )

        self.assertEqual(record["entity_id"], "entity-1")
        self.assertEqual(record["properties"]["entity_type"], "sql_table")
        self.assertEqual(record["properties"]["property_schema"], "dbo")
        self.assertIn("properties_json", record["properties"])

    def test_edge_record_marks_unresolved_edges(self) -> None:
        record = edge_record(
            {
                "edge_id": "edge-1",
                "from_entity_id": "entity-1",
                "from_name": "service.ts",
                "from_type": "file",
                "to_name": "dbo.MissingProc",
                "to_type": "stored_procedure",
                "edge_type": "CALLS_SQL",
                "resolved": False,
                "source_name": "api-service",
                "properties": {},
            }
        )

        self.assertFalse(record["resolved"])
        self.assertEqual(record["relationship_type"], "CALLS_SQL")
        self.assertTrue(record["target_id"])

    def test_unresolved_targets_are_deduped(self) -> None:
        edge = {
            "edge_id": "edge-1",
            "from_entity_id": "entity-1",
            "from_name": "service.ts",
            "from_type": "file",
            "to_name": "dbo.MissingProc",
            "to_type": "stored_procedure",
            "edge_type": "CALLS_SQL",
            "resolved": False,
            "source_name": "api-service",
            "properties": {},
        }
        targets = unresolved_target_records([edge_record(edge), edge_record(edge)])

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["properties"]["name"], "dbo.MissingProc")

    def test_load_summary_counts_edges_and_targets(self) -> None:
        graph_data = {
            "metadata": {"scope_name": "example", "schema_version": "0.1"},
            "sources": [{"name": "api-service"}],
            "entities": [{"entity_id": "entity-1"}],
            "edges": [],
        }
        resolved = {"resolved": True}
        unresolved = {"resolved": False}
        source = {"source_id": "source-1"}
        summary = load_summary(
            graph_data,
            [source],
            [resolved, unresolved],
            [{"target_id": "target-1"}],
            clear_existing=True,
        )

        self.assertEqual(summary.scope_name, "example")
        self.assertEqual(summary.source_count, 1)
        self.assertEqual(summary.entity_count, 1)
        self.assertEqual(summary.edge_count, 2)
        self.assertEqual(summary.resolved_edge_count, 1)
        self.assertEqual(summary.unresolved_target_count, 1)

    def test_source_record_uses_scope_and_source_name_for_id(self) -> None:
        record = source_record(
            {"name": "api-service", "type": "local_path", "path": "/repo/examples/api-service", "ref": "default"},
            {"metadata": {"scope_name": "example"}},
            0,
        )

        self.assertEqual(record["properties"]["name"], "api-service")
        self.assertEqual(record["properties"]["index"], 0)
        self.assertTrue(record["source_id"])

    def test_source_payload_returns_public_source_fields(self) -> None:
        payload = source_payload(
            {
                "source_id": "source-1",
                "index": 0,
                "name": "api-service",
                "type": "git",
                "url": "https://github.com/example/api-service.git",
                "ref": "main",
                "commit": "abc123",
            }
        )

        self.assertEqual(payload["name"], "api-service")
        self.assertEqual(payload["type"], "git")
        self.assertEqual(payload["commit"], "abc123")

    def test_scope_payload_includes_summary_and_sources(self) -> None:
        payload = scope_payload(
            {
                "scope_name": "example",
                "schema_version": "0.1",
                "generated_at": "2026-05-11T00:00:00+00:00",
                "tool": "RepoGraph",
                "summary_json": '{"entity_count": 1}',
            },
            [{"source_id": "source-1", "name": "api-service"}],
        )

        self.assertTrue(payload["loaded"])
        self.assertEqual(payload["source_count"], 1)
        self.assertEqual(payload["sources"][0]["name"], "api-service")
        self.assertEqual(payload["summary"]["entity_count"], 1)

    def test_unloaded_scope_payload_has_no_sources(self) -> None:
        payload = unloaded_scope_payload()

        self.assertFalse(payload["loaded"])
        self.assertEqual(payload["source_count"], 0)
        self.assertEqual(payload["sources"], [])

    def test_entity_payload_restores_nested_properties(self) -> None:
        payload = entity_payload(
            {
                "entity_id": "entity-1",
                "entity_type": "api_route",
                "name": "GET /accounts",
                "source_name": "api-service",
                "properties_json": '{"method": "GET", "path": "/accounts"}',
            }
        )

        self.assertEqual(payload["entity_id"], "entity-1")
        self.assertEqual(payload["properties"]["method"], "GET")

    def test_edge_payload_restores_nested_properties(self) -> None:
        payload = edge_payload(
            {
                "edge_id": "edge-1",
                "edge_type": "IMPORTS",
                "from_entity_id": "file-1",
                "to_name": "express",
                "resolved": False,
                "properties_json": '{"resolution_status": "ambiguous"}',
            }
        )

        self.assertEqual(payload["edge_type"], "IMPORTS")
        self.assertEqual(payload["properties"]["resolution_status"], "ambiguous")

    def test_graph_node_payload_uses_target_shape_for_targets(self) -> None:
        payload = graph_node_payload(
            {"target_id": "target-1", "name": "dbo.Missing", "target_type": "stored_procedure"},
            ["RepoGraphTarget"],
        )

        self.assertEqual(payload, target_payload(payload))
        self.assertEqual(payload["target_id"], "target-1")

    def test_normalize_limit_rejects_out_of_range_values(self) -> None:
        self.assertEqual(normalize_limit(25, maximum=100), 25)

        with self.assertRaises(ValueError):
            normalize_limit(0, maximum=100)

        with self.assertRaises(ValueError):
            normalize_limit(101, maximum=100)

    def test_normalize_direction_accepts_only_supported_values(self) -> None:
        self.assertEqual(normalize_direction("OUT"), "out")

        with self.assertRaises(ValueError):
            normalize_direction("sideways")


if __name__ == "__main__":
    unittest.main()
