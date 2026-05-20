from __future__ import annotations

import unittest

from repo_graph.reports import (
    interactions_report_from_graph,
    interactions_report_from_items,
    unresolved_report_from_graph,
    unresolved_report_from_items,
)


class ReportTests(unittest.TestCase):
    def test_interactions_report_groups_app_and_database_edges(self) -> None:
        graph_data = {
            "metadata": {"scope_name": "test-scope", "generated_at": "2026-05-14T00:00:00+00:00"},
            "entities": [
                {
                    "entity_id": "entity-api",
                    "entity_type": "service",
                    "name": "inventory-service",
                    "source_name": "inventory-service",
                },
                {
                    "entity_id": "entity-table",
                    "entity_type": "sql_table",
                    "name": "dbo.orders",
                    "source_name": "database-project",
                },
            ],
            "edges": [
                interaction_edge(
                    "edge-1",
                    "ui-service",
                    "CALLS_SERVICE",
                    "service",
                    "inventory-service",
                    to_entity_id="entity-api",
                    raw_target="${INVENTORY_SERVICE_URL}/orders",
                    client="fetch",
                ),
                interaction_edge(
                    "edge-2",
                    "api-service",
                    "READS_SQL_OBJECT",
                    "sql_table",
                    "dbo.orders",
                    to_entity_id="entity-table",
                    properties={
                        "target_boundary": "database",
                        "dependency_scope": "runtime",
                        "interaction_kind": "sql_reference",
                        "protocol": "sql",
                        "raw_target": "dbo.orders",
                        "normalized_target": "dbo.orders",
                        "sql_operation": "FROM",
                        "database_object_type": "sql_object",
                    },
                ),
                {
                    "edge_id": "edge-3",
                    "edge_type": "DECLARES_SYMBOL",
                    "source_name": "api-service",
                    "to_name": "helper",
                    "properties": {},
                },
            ],
        }

        report = interactions_report_from_graph(graph_data)

        self.assertEqual(report["scope_name"], "test-scope")
        self.assertEqual(report["summary"]["interaction_edge_count"], 2)
        self.assertEqual(report["summary"]["resolved_edge_count"], 2)
        self.assertEqual(report["summary"]["target_boundary_counts"], {"application": 1, "database": 1})
        self.assertEqual(report["source_hotspots"][0]["source_name"], "api-service")
        self.assertEqual(report["target_hotspots"][0]["target_source"], "database-project")
        database_group = report["items"][0]
        self.assertEqual(database_group["from_source"], "api-service")
        self.assertEqual(database_group["target_source"], "database-project")
        self.assertEqual(database_group["interaction_kind"], "sql_reference")
        self.assertEqual(database_group["examples"][0]["sql_operation"], "FROM")

    def test_interactions_report_filters_api_payloads(self) -> None:
        items = [
            {
                "to_source": "inventory-service",
                "edge": interaction_edge(
                    "edge-1",
                    "ui-service",
                    "CALLS_SERVICE",
                    "service",
                    "inventory-service",
                    raw_target="${INVENTORY_SERVICE_URL}/orders",
                ),
            },
            {
                "to_source": "database-project",
                "edge": interaction_edge(
                    "edge-2",
                    "api-service",
                    "CALLS_SQL",
                    "stored_procedure",
                    "dbo.load",
                    properties={
                        "target_boundary": "database",
                        "dependency_scope": "runtime",
                        "interaction_kind": "sql_reference",
                        "protocol": "sql",
                        "raw_target": "dbo.load",
                        "normalized_target": "dbo.load",
                        "sql_operation": "EXECUTE",
                        "database_object_type": "stored_procedure",
                    },
                ),
            },
        ]

        report = interactions_report_from_items(items, source_name="api-service", target_source="database-project")

        self.assertEqual(report["filters"], {"source": "api-service", "target_source": "database-project"})
        self.assertEqual(report["summary"]["interaction_edge_count"], 1)
        self.assertEqual(report["items"][0]["to_name"], "dbo.load")

    def test_unresolved_report_groups_edges_with_classification_hints(self) -> None:
        graph_data = {
            "metadata": {"scope_name": "test-scope", "generated_at": "2026-05-14T00:00:00+00:00"},
            "edges": [
                edge(
                    "edge-1",
                    "api-service",
                    "CALLS_SERVICE",
                    "service",
                    "inventory-service",
                    raw_target="${INVENTORY_SERVICE_URL}/inventory",
                ),
                edge(
                    "edge-2",
                    "worker-service",
                    "CALLS_SERVICE",
                    "service",
                    "inventory-service",
                    raw_target="${INVENTORY_SERVICE_URL}/inventory",
                ),
                edge(
                    "edge-3",
                    "api-service",
                    "IMPORTS",
                    "module",
                    "internal.module",
                ),
                edge(
                    "edge-4",
                    "api-service",
                    "CONTAINS_PROJECT",
                    "project",
                    "src/Example.Service",
                ),
                edge(
                    "edge-5",
                    "api-service",
                    "CALLS_SQL",
                    "stored_procedure",
                    "dbo.load",
                    properties={"resolution_status": "ambiguous", "resolution_candidates": [{"name": "dbo.load"}]},
                ),
                {
                    "edge_id": "edge-6",
                    "resolved": True,
                    "edge_type": "CALLS_SERVICE",
                    "source_name": "api-service",
                    "to_type": "service",
                    "to_name": "billing-service",
                },
            ],
        }

        report = unresolved_report_from_graph(graph_data)

        self.assertEqual(report["scope_name"], "test-scope")
        self.assertEqual(report["summary"]["unresolved_edge_count"], 5)
        self.assertEqual(report["summary"]["group_count"], 4)
        self.assertEqual(report["summary"]["classification_edge_counts"]["likely_missing_source"], 2)
        self.assertEqual(report["summary"]["classification_edge_counts"]["likely_parser_gap"], 2)
        self.assertEqual(report["summary"]["classification_edge_counts"]["ambiguous_target"], 1)
        self.assertEqual(report["summary"]["classification_group_counts"]["likely_missing_source"], 1)
        self.assertEqual(report["classification_groups"][0]["classification"], "likely_missing_source")
        self.assertEqual(report["classification_groups"][0]["count"], 2)
        self.assertIn("Add or sync", report["classification_groups"][0]["recommended_action"])
        self.assertEqual(report["source_hotspots"][0]["source_name"], "api-service")
        self.assertEqual(report["source_hotspots"][0]["count"], 4)
        self.assertEqual(report["target_hotspots"][0]["to_name"], "inventory-service")
        service_group = report["items"][0]
        self.assertEqual(service_group["edge_type"], "CALLS_SERVICE")
        self.assertEqual(service_group["to_name"], "inventory-service")
        self.assertEqual(service_group["classification"], "likely_missing_source")
        self.assertIn("Add or sync", service_group["recommended_action"])
        self.assertEqual(service_group["count"], 2)
        self.assertEqual(service_group["source_names"], ["api-service", "worker-service"])
        self.assertEqual(service_group["examples"][0]["raw_target"], "${INVENTORY_SERVICE_URL}/inventory")

    def test_unresolved_report_filters_items_from_api_payloads(self) -> None:
        items = [
            {"edge": edge("edge-1", "api-service", "CALLS_SQL", "stored_procedure", "dbo.load")},
            {"edge": edge("edge-2", "worker-service", "CALLS_SQL", "stored_procedure", "dbo.load")},
            {"edge": edge("edge-3", "api-service", "CALLS_SERVICE", "service", "inventory-service")},
        ]

        report = unresolved_report_from_items(items, source_name="api-service", edge_type="CALLS_SQL")

        self.assertEqual(report["filters"], {"source": "api-service", "edge_type": "CALLS_SQL"})
        self.assertEqual(report["summary"]["unresolved_edge_count"], 1)
        self.assertEqual(report["items"][0]["to_name"], "dbo.load")


def edge(
    edge_id: str,
    source_name: str,
    edge_type: str,
    to_type: str,
    to_name: str,
    raw_target: str | None = None,
    properties: dict[str, object] | None = None,
) -> dict[str, object]:
    edge_properties = dict(properties or {})
    if raw_target:
        edge_properties["raw_target"] = raw_target
        edge_properties["normalized_target"] = to_name
    return {
        "edge_id": edge_id,
        "from_name": "src/app.py",
        "from_type": "file",
        "to_name": to_name,
        "to_type": to_type,
        "edge_type": edge_type,
        "resolved": False,
        "source_name": source_name,
        "file_path": "src/app.py",
        "line_number": 10,
        "confidence": "medium",
        "parser": "test_parser",
        "properties": edge_properties,
    }


def interaction_edge(
    edge_id: str,
    source_name: str,
    edge_type: str,
    to_type: str,
    to_name: str,
    to_entity_id: str | None = None,
    raw_target: str | None = None,
    client: str | None = None,
    properties: dict[str, object] | None = None,
) -> dict[str, object]:
    edge_properties = dict(
        properties
        or {
            "target_boundary": "application",
            "dependency_scope": "runtime",
            "interaction_kind": "http_call",
            "protocol": "http",
            "raw_target": raw_target or to_name,
            "normalized_target": to_name,
        }
    )
    if client:
        edge_properties["client"] = client
    return {
        "edge_id": edge_id,
        "from_name": "src/app.py",
        "from_type": "file",
        "to_name": to_name,
        "to_type": to_type,
        "to_entity_id": to_entity_id,
        "edge_type": edge_type,
        "resolved": to_entity_id is not None,
        "source_name": source_name,
        "file_path": "src/app.py",
        "line_number": 10,
        "confidence": "medium",
        "parser": "test_parser",
        "properties": edge_properties,
    }


if __name__ == "__main__":
    unittest.main()
