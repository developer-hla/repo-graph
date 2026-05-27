"""Golden extraction fixtures for first-class interaction facts."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

from repo_graph.config import load_config
from repo_graph.extraction import build_graph


class GoldenExtractionTests(unittest.TestCase):
    def test_first_class_interaction_fixture_emits_expected_edges(self) -> None:
        graph_data = build_golden_fixture_graph()
        edges = graph_data["edges"]

        expected_edges = (
            {
                "edge_type": "CALLS_SERVICE",
                "parser": "javascript_http",
                "from_type": "function",
                "from_name": "handler",
                "to_type": "project",
                "to_name": "inventory-service",
                "resolved": True,
            },
            {
                "edge_type": "CALLS_SQL",
                "parser": "sql_reference",
                "from_type": "function",
                "from_name": "handler",
                "to_type": "stored_procedure",
                "to_name": "dbo.load_order",
            },
            {
                "edge_type": "READS_SQL_OBJECT",
                "parser": "sql_reference",
                "from_type": "stored_procedure",
                "from_name": "dbo.load_order",
                "to_name": "dbo.orders",
                "resolved": True,
            },
            {
                "edge_type": "PUBLISHES_MESSAGE",
                "parser": "javascript_message",
                "from_type": "function",
                "from_name": "handler",
                "to_type": "message_topic",
                "to_name": "orders.changed",
                "resolved": True,
            },
            {
                "edge_type": "CONSUMES_MESSAGE",
                "parser": "python_message",
                "from_type": "function",
                "to_type": "message_topic",
                "to_name": "orders.changed",
                "resolved": True,
            },
            {
                "edge_type": "WRITES_CACHE_KEY",
                "parser": "javascript_cache",
                "from_type": "function",
                "to_type": "cache_key",
                "to_name": "order:latest",
                "resolved": True,
            },
            {
                "edge_type": "READS_CACHE_KEY",
                "parser": "python_cache",
                "from_type": "function",
                "to_type": "cache_key",
                "to_name": "order:latest",
                "resolved": True,
            },
            {
                "edge_type": "WRITES_STORAGE_OBJECT",
                "parser": "javascript_storage",
                "from_type": "function",
                "to_type": "storage_location",
                "to_name": "reports/orders/latest.json",
                "resolved": True,
            },
            {
                "edge_type": "READS_STORAGE_OBJECT",
                "parser": "python_storage",
                "from_type": "function",
                "to_type": "storage_location",
                "to_name": "reports/orders/latest.json",
                "resolved": True,
            },
            {
                "edge_type": "RUNS_JOB",
                "parser": "javascript_job",
                "from_type": "scheduled_job",
                "to_type": "function",
                "to_name": "refreshOrderCache",
            },
            {
                "edge_type": "SELECTS_DEPLOYMENT",
                "parser": "kubernetes_selector",
                "from_type": "service",
                "from_name": "orders-api",
                "to_type": "deployment",
                "to_name": "orders-api",
            },
            {
                "edge_type": "ROUTES_TO_SERVICE",
                "parser": "kubernetes_ingress_route",
                "from_type": "api_route",
                "to_type": "service",
                "to_name": "orders-api",
            },
            {
                "edge_type": "CONFIGURES_SERVICE",
                "parser": "kubernetes_env",
                "from_type": "config_value",
                "to_type": "project",
                "to_name": "inventory-service",
                "resolved": True,
            },
        )

        for expected in expected_edges:
            with self.subTest(expected=expected):
                self.assertTrue(edge_exists(edges, expected), expected)

        self.assertEqual(graph_data["summary"]["error_count"], 0)


def build_golden_fixture_graph() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        app = root / "orders-api"
        inventory = root / "inventory-service"
        worker = root / "orders-worker"
        database = root / "orders-db"
        deploy = root / "orders-deploy"
        for repo in (app, inventory, worker, database, deploy):
            repo.mkdir()

        (app / "app.ts").write_text(
            textwrap.dedent(
                """
                export async function handler(id: string) {
                  await fetch(`${process.env.INVENTORY_SERVICE_URL}/inventory/${id}`);
                  await db.query('EXEC dbo.load_order');
                  await producer.send({ topic: "orders.changed", messages: [{ value: id }] });
                  await redis.set("order:latest", id);
                  await s3.putObject({ Bucket: "reports", Key: "orders/latest.json", Body: id });
                }

                function refreshOrderCache() {
                  return handler("latest");
                }

                cron.schedule("0 * * * *", refreshOrderCache);
                server.get('/orders/:id', handler);
                """
            ),
            encoding="utf-8",
        )
        (worker / "worker.py").write_text(
            textwrap.dedent(
                """
                def consume_orders() -> None:
                    consumer.subscribe(["orders.changed"])
                    redis.get("order:latest")
                    s3.get_object(Bucket="reports", Key="orders/latest.json")
                """
            ),
            encoding="utf-8",
        )
        (inventory / "package.json").write_text('{"name": "@example/inventory-service"}', encoding="utf-8")
        (inventory / "index.ts").write_text("server.get('/inventory/:id', handler);", encoding="utf-8")
        (database / "schema.sql").write_text(
            textwrap.dedent(
                """
                CREATE TABLE dbo.orders (id int)
                CREATE PROCEDURE dbo.load_order AS
                SELECT * FROM dbo.orders
                """
            ),
            encoding="utf-8",
        )
        (deploy / "deployment.yaml").write_text(
            textwrap.dedent(
                """
                apiVersion: v1
                kind: Service
                metadata:
                  name: orders-api
                spec:
                  selector:
                    app: orders-api
                  ports:
                    - port: 80
                ---
                apiVersion: apps/v1
                kind: Deployment
                metadata:
                  name: orders-api
                spec:
                  selector:
                    matchLabels:
                      app: orders-api
                  template:
                    metadata:
                      labels:
                        app: orders-api
                    spec:
                      containers:
                        - name: api
                          image: orders-api:latest
                          env:
                            - name: INVENTORY_SERVICE_URL
                              value: http://inventory-service:8080
                ---
                apiVersion: networking.k8s.io/v1
                kind: Ingress
                metadata:
                  name: orders-api
                spec:
                  rules:
                    - host: orders.example.test
                      http:
                        paths:
                          - path: /orders
                            pathType: Prefix
                            backend:
                              service:
                                name: orders-api
                                port:
                                  number: 80
                """
            ),
            encoding="utf-8",
        )
        config_path = root / "sources.yaml"
        config_path.write_text(
            textwrap.dedent(
                """
                name: golden-scope
                sources:
                  - type: local_path
                    name: orders-api
                    path: orders-api
                  - type: local_path
                    name: inventory-service
                    path: inventory-service
                  - type: local_path
                    name: orders-worker
                    path: orders-worker
                  - type: local_path
                    name: orders-db
                    path: orders-db
                  - type: local_path
                    name: orders-deploy
                    path: orders-deploy
                """
            ),
            encoding="utf-8",
        )

        return build_graph(load_config(config_path)).to_dict()


def edge_exists(edges: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    return any(edge_matches(edge, expected) for edge in edges)


def edge_matches(edge: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(edge.get(key) == value for key, value in expected.items())
