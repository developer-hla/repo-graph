from __future__ import annotations

import unittest

from repo_graph.reports import (
    database_reconciliation_report_from_graph,
    database_reconciliation_report_from_items,
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

    def test_database_reconciliation_report_groups_drift(self) -> None:
        graph_data = {
            "metadata": {"scope_name": "test-scope", "generated_at": "2026-05-14T00:00:00+00:00"},
            "entities": [
                sql_entity("db-customers", "sql_table", "dbo.Customers", "current-db", "current_database"),
                sql_entity("db-orders", "sql_table", "dbo.Orders", "current-db", "current_database"),
                sql_entity("db-summary", "sql_table", "dbo.CustomerSummary", "current-db", "current_database"),
                sql_entity("schema-summary", "sql_view", "dbo.CustomerSummary", "database-project", "current_schema"),
                sql_entity("history-legacy", "sql_table", "dbo.LegacyCustomer", "database-project", "historical"),
            ],
            "edges": [
                interaction_edge(
                    "edge-1",
                    "api-service",
                    "READS_SQL_OBJECT",
                    "sql_table",
                    "dbo.Customers",
                    to_entity_id="db-customers",
                ),
                interaction_edge(
                    "edge-2",
                    "api-service",
                    "CALLS_SQL",
                    "stored_procedure",
                    "dbo.LoadMissing",
                    properties=sql_edge_properties("dbo.LoadMissing", "EXECUTE", "stored_procedure"),
                ),
                interaction_edge(
                    "edge-3",
                    "current-db",
                    "REFERENCES_SQL_OBJECT",
                    "sql_table",
                    "dbo.MissingParent",
                    properties={
                        **sql_edge_properties("dbo.MissingParent", "FOREIGN_KEY", "sql_object"),
                        "schema_state": "current_database",
                    },
                )
                | {"parser": "sqlserver_metadata"},
            ],
        }

        report = database_reconciliation_report_from_graph(graph_data)

        self.assertEqual(report["scope_name"], "test-scope")
        self.assertTrue(report["summary"]["database_evidence_present"])
        self.assertEqual(report["summary"]["classification_group_counts"]["code_only_reference"], 1)
        self.assertEqual(report["summary"]["classification_group_counts"]["unresolved_database_reference"], 1)
        self.assertEqual(report["summary"]["classification_group_counts"]["schema_drift"], 1)
        self.assertEqual(report["summary"]["classification_group_counts"]["migration_only_object"], 1)
        self.assertEqual(report["summary"]["classification_group_counts"]["database_only_object"], 1)
        classifications = {item["classification"]: item for item in report["items"]}
        self.assertEqual(classifications["code_only_reference"]["target_name"], "dbo.LoadMissing")
        self.assertEqual(classifications["unresolved_database_reference"]["database_sources"], ["current-db"])
        self.assertEqual(classifications["schema_drift"]["target_name"], "dbo.CustomerSummary")
        self.assertEqual(classifications["migration_only_object"]["target_name"], "dbo.LegacyCustomer")
        self.assertEqual(classifications["database_only_object"]["target_name"], "dbo.Orders")

    def test_database_reconciliation_report_filters_items_from_api_payloads(self) -> None:
        entities = [
            sql_entity("db-customers", "sql_table", "dbo.Customers", "current-db", "current_database"),
            sql_entity("db-orders", "sql_table", "dbo.Orders", "current-db", "current_database"),
        ]
        items = [
            {
                "edge": interaction_edge(
                    "edge-1",
                    "api-service",
                    "READS_SQL_OBJECT",
                    "sql_table",
                    "dbo.Customers",
                    to_entity_id="db-customers",
                )
            }
        ]

        report = database_reconciliation_report_from_items(
            entities,
            items,
            source_name="api-service",
            database_source="current-db",
        )

        self.assertEqual(report["filters"], {"source": "api-service", "database_source": "current-db"})
        self.assertEqual(report["summary"]["current_database_entity_count"], 2)
        self.assertEqual(report["items"][0]["classification"], "database_only_object")
        self.assertEqual(report["items"][0]["target_name"], "dbo.Orders")


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


def sql_entity(
    entity_id: str,
    entity_type: str,
    name: str,
    source_name: str,
    schema_state: str,
) -> dict[str, object]:
    schema, _short_name = name.split(".", 1)
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "name": name,
        "source_name": source_name,
        "properties": {
            "schema": schema,
            "full_name": name,
            "schema_state": schema_state,
        },
    }


def sql_edge_properties(raw_target: str, operation: str, database_object_type: str) -> dict[str, object]:
    return {
        "target_boundary": "database",
        "dependency_scope": "runtime",
        "interaction_kind": "sql_reference",
        "protocol": "sql",
        "raw_target": raw_target,
        "normalized_target": raw_target,
        "sql_operation": operation,
        "database_object_type": database_object_type,
    }


if __name__ == "__main__":
    unittest.main()
