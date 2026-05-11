"""Tests for Neo4j storage record shaping."""

from __future__ import annotations

import unittest

from repo_graph.storage.neo4j import (
    edge_record,
    entity_record,
    load_summary,
    sanitize_relationship_type,
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
            "entities": [{"entity_id": "entity-1"}],
            "edges": [],
        }
        resolved = {"resolved": True}
        unresolved = {"resolved": False}
        summary = load_summary(graph_data, [resolved, unresolved], [{"target_id": "target-1"}], clear_existing=True)

        self.assertEqual(summary.scope_name, "example")
        self.assertEqual(summary.entity_count, 1)
        self.assertEqual(summary.edge_count, 2)
        self.assertEqual(summary.resolved_edge_count, 1)
        self.assertEqual(summary.unresolved_target_count, 1)


if __name__ == "__main__":
    unittest.main()
