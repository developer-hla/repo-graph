"""Tests for Neo4j storage record shaping."""

from __future__ import annotations

import unittest

from repo_graph.storage._neo4j_common import (
    normalize_depth,
    normalize_direction,
    normalize_edge_types,
    normalize_limit,
    sanitize_relationship_type,
)
from repo_graph.storage._neo4j_payloads import (
    edge_payload,
    entity_payload,
    graph_node_payload,
    neighbor_payload,
    relationship_evidence_payload,
    scope_payload,
    source_payload,
    target_payload,
    unloaded_scope_payload,
)
from repo_graph.storage._neo4j_records import (
    edge_record,
    entity_record,
    load_summary,
    normalize_source_names,
    prepare_graph_records,
    source_record,
    unresolved_target_records,
    validate_replace_sources,
)
from repo_graph.storage._neo4j_relationship_queries import outgoing_neighbors_query, relationship_search_query
from repo_graph.storage._neo4j_scope_queries import (
    cross_source_edges_query,
    edge_type_counts_query,
    entity_type_counts_query,
    source_edge_counts_query,
    source_entity_counts_query,
    source_metadata_query,
)
from repo_graph.storage._neo4j_source_queries import (
    source_detail_query,
    source_edge_type_counts_query,
    source_entity_type_counts_query,
    source_incoming_cross_source_query,
    source_outgoing_cross_source_query,
    source_owned_surface_query,
    source_summary_query,
    source_uses_query,
)
from repo_graph.storage._neo4j_writes import (
    delete_current_edges_tx,
    delete_orphan_external_resources_tx,
    delete_source_data_tx,
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

    def test_neighbor_payload_includes_depth_and_path(self) -> None:
        payload = neighbor_payload(
            {
                "direction": "out",
                "depth": 2,
                "edge": {
                    "edge_id": "edge-1",
                    "edge_type": "IMPORTS",
                    "from_entity_id": "file-1",
                    "to_name": "shared",
                    "resolved": True,
                },
                "neighbor": {"entity_id": "entity-2", "entity_type": "package", "name": "shared"},
                "labels": ["RepoGraphEntity"],
                "path_nodes": [
                    {"entity_id": "entity-1", "entity_type": "file", "name": "index.ts"},
                    {"entity_id": "entity-2", "entity_type": "package", "name": "shared"},
                ],
                "path_node_labels": [["RepoGraphEntity"], ["RepoGraphEntity"]],
                "path_edges": [
                    {
                        "edge_id": "edge-1",
                        "edge_type": "IMPORTS",
                        "from_entity_id": "file-1",
                        "to_name": "shared",
                        "resolved": True,
                    }
                ],
                "node_ids": ["entity-1", "entity-2"],
                "edge_ids": ["edge-1"],
            }
        )

        self.assertEqual(payload["depth"], 2)
        self.assertEqual(payload["path"]["node_ids"], ["entity-1", "entity-2"])
        self.assertEqual(payload["path"]["edge_ids"], ["edge-1"])
        self.assertEqual(payload["path"]["steps"][0]["from"]["entity_id"], "entity-1")
        self.assertEqual(payload["path"]["steps"][0]["edge"]["edge_type"], "IMPORTS")
        self.assertEqual(payload["path"]["steps"][0]["to"]["entity_id"], "entity-2")

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

    def test_normalize_depth_accepts_one_to_three(self) -> None:
        self.assertEqual(normalize_depth(3), 3)

        with self.assertRaises(ValueError):
            normalize_depth(0)

        with self.assertRaises(ValueError):
            normalize_depth(4)

    def test_normalize_edge_types_dedupes_and_ignores_blanks(self) -> None:
        self.assertEqual(normalize_edge_types([" CALLS_SQL ", "", "IMPORTS", "CALLS_SQL"]), ["CALLS_SQL", "IMPORTS"])
        self.assertIsNone(normalize_edge_types(None))
        self.assertIsNone(normalize_edge_types(["", " "]))

    def test_neighbor_query_supports_allowed_edge_type_filter(self) -> None:
        query = outgoing_neighbors_query(2)

        self.assertIn("edge.edge_type IN $edge_types", query)
        self.assertIn("[*1..2]", query)
        self.assertIn("nodes(path) AS path_nodes", query)
        self.assertIn("relationships(path) AS path_edges", query)

    def test_explore_count_queries_are_limited_and_grouped(self) -> None:
        self.assertIn("entity.entity_type", entity_type_counts_query())
        self.assertIn("LIMIT $limit", entity_type_counts_query())
        self.assertIn("resolved_edge_count", edge_type_counts_query())
        self.assertIn("unresolved_edge_count", edge_type_counts_query())
        self.assertIn("source.name", source_metadata_query())
        self.assertIn("entity.source_name", source_entity_counts_query())
        self.assertIn("unresolved_edge_count", source_edge_counts_query())
        self.assertIn("edge.source_name <> to.source_name", cross_source_edges_query())

    def test_source_overview_queries_are_scoped_to_source(self) -> None:
        self.assertIn("RepoGraphSource {name: $source_name}", source_detail_query())
        self.assertIn("edge.source_name = $source_name", source_summary_query())
        self.assertIn("entity.source_name = $source_name", source_entity_type_counts_query())
        self.assertIn("edge.source_name = $source_name", source_edge_type_counts_query())
        self.assertIn("entity.entity_type IN $surface_entity_types", source_owned_surface_query())
        self.assertIn("edge.edge_type IN $use_edge_types", source_uses_query())
        self.assertIn("target.source_name <> $source_name", source_outgoing_cross_source_query())
        self.assertIn("target.source_name = $source_name", source_incoming_cross_source_query())

    def test_relationship_search_query_filters_relationship_evidence(self) -> None:
        query = relationship_search_query()

        self.assertIn("$from_source", query)
        self.assertIn("$to_source", query)
        self.assertIn("$edge_type", query)
        self.assertIn("$from_type", query)
        self.assertIn("$to_type", query)
        self.assertIn("$resolved", query)
        self.assertIn("labels(target) AS target_labels", query)

    def test_relationship_evidence_payload_shapes_resolved_target(self) -> None:
        payload = relationship_evidence_payload(
            {
                "source": {
                    "entity_id": "entity-1",
                    "entity_type": "api_route",
                    "name": "GET /accounts",
                    "source_name": "api-service",
                },
                "edge": {
                    "edge_id": "edge-1",
                    "edge_type": "CALLS_SQL",
                    "from_type": "api_route",
                    "to_type": "stored_procedure",
                    "resolved": True,
                    "source_name": "api-service",
                },
                "target": {
                    "entity_id": "entity-2",
                    "entity_type": "stored_procedure",
                    "name": "dbo.load_accounts",
                    "source_name": "database",
                },
                "target_labels": ["RepoGraphEntity"],
            }
        )

        self.assertEqual(payload["from_source"], "api-service")
        self.assertEqual(payload["to_source"], "database")
        self.assertEqual(payload["from_type"], "api_route")
        self.assertEqual(payload["to_type"], "stored_procedure")
        self.assertEqual(payload["target"]["entity_id"], "entity-2")

    def test_prepare_graph_records_shapes_all_load_records(self) -> None:
        graph_data = {
            "metadata": {"scope_name": "example", "schema_version": "0.1"},
            "sources": [{"name": "api-service"}],
            "entities": [
                {
                    "entity_id": "entity-1",
                    "entity_type": "file",
                    "name": "index.ts",
                    "source_name": "api-service",
                }
            ],
            "edges": [
                {
                    "edge_id": "edge-1",
                    "from_entity_id": "entity-1",
                    "from_name": "index.ts",
                    "from_type": "file",
                    "to_name": "missing",
                    "to_type": "package",
                    "edge_type": "IMPORTS",
                    "resolved": False,
                    "source_name": "api-service",
                }
            ],
        }

        records = prepare_graph_records(graph_data)

        self.assertEqual(len(records.source_records), 1)
        self.assertEqual(len(records.entity_records), 1)
        self.assertEqual(len(records.edge_records), 1)
        self.assertEqual(len(records.target_records), 1)

    def test_normalize_source_names_dedupes_and_ignores_blanks(self) -> None:
        self.assertEqual(normalize_source_names([" service ", "", "api", "service"]), ("api", "service"))

    def test_validate_replace_sources_rejects_names_missing_from_graph(self) -> None:
        graph_data = {"sources": [{"name": "api-service"}]}

        with self.assertRaises(ValueError):
            validate_replace_sources(graph_data, ("missing-service",))

    def test_delete_current_edges_tx_deletes_existing_edge_ids(self) -> None:
        tx = FakeTx()

        delete_current_edges_tx(tx, [{"edge_id": "edge-1"}, {"edge_id": "edge-2"}])

        self.assertEqual(tx.calls[0]["params"]["edge_ids"], ["edge-1", "edge-2"])
        self.assertIn("edge.edge_id IN $edge_ids", tx.calls[0]["query"])

    def test_delete_source_data_tx_deletes_source_owned_graph_data(self) -> None:
        tx = FakeTx()

        delete_source_data_tx(tx, ["api-service"])

        self.assertEqual(len(tx.calls), 4)
        self.assertTrue(all(call["params"]["source_names"] == ["api-service"] for call in tx.calls))
        self.assertIn("edge.source_name IN $source_names", tx.calls[0]["query"])
        self.assertIn("DETACH DELETE entity", tx.calls[1]["query"])
        self.assertIn("DETACH DELETE target", tx.calls[2]["query"])
        self.assertIn("DETACH DELETE source", tx.calls[3]["query"])

    def test_delete_orphan_external_resources_tx_removes_unused_canonical_resources(self) -> None:
        tx = FakeTx()

        delete_orphan_external_resources_tx(tx)

        self.assertEqual(len(tx.calls), 1)
        self.assertIn("property_canonical_external_resource", tx.calls[0]["query"])
        self.assertIn("NOT (entity)--()", tx.calls[0]["query"])
        self.assertIn("DETACH DELETE entity", tx.calls[0]["query"])


class FakeResult:
    def consume(self) -> None:
        return None


class FakeTx:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, query: str, **params: object) -> FakeResult:
        self.calls.append({"query": query, "params": params})
        return FakeResult()


if __name__ == "__main__":
    unittest.main()
