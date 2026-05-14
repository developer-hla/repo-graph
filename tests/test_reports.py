from __future__ import annotations

import unittest

from repo_graph.reports import unresolved_report_from_graph, unresolved_report_from_items


class ReportTests(unittest.TestCase):
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
        service_group = report["items"][0]
        self.assertEqual(service_group["edge_type"], "CALLS_SERVICE")
        self.assertEqual(service_group["to_name"], "inventory-service")
        self.assertEqual(service_group["classification"], "likely_missing_source")
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


if __name__ == "__main__":
    unittest.main()
