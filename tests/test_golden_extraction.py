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

    def test_legacy_dotnet_manifest_fixture_emits_expected_facts(self) -> None:
        graph_data = build_legacy_dotnet_fixture_graph()
        edges = graph_data["edges"]
        entities = graph_data["entities"]

        expected_entities = (
            {
                "entity_type": "project",
                "name": "Legacy.Ordering",
                "properties": {
                    "ecosystem": "dotnet",
                    "project_type": "dotnet_project",
                    "package_name": "Legacy.Ordering",
                },
            },
            {
                "entity_type": "package",
                "name": "Legacy.Ordering",
                "properties": {
                    "ecosystem": "dotnet",
                    "target_framework": "v4.8",
                },
            },
            {
                "entity_type": "config_value",
                "name": "app_setting:InventoryServiceUrl",
                "properties": {
                    "value_kind": "app_setting",
                    "target_url": "http://inventory-service/api",
                },
            },
            {
                "entity_type": "config_value",
                "name": "connection_string:MainDb",
                "properties": {
                    "value_kind": "connection_string",
                    "provider_name": "System.Data.SqlClient",
                },
            },
            {
                "entity_type": "config_value",
                "name": "wcf_endpoint:InventoryClient",
                "properties": {
                    "binding": "basicHttpBinding",
                    "contract": "Example.IInventory",
                    "target_url": "http://inventory-service/Inventory.svc",
                },
            },
        )
        expected_edges = (
            {
                "edge_type": "DECLARES_PACKAGE",
                "parser": "dotnet_project",
                "from_type": "project",
                "from_name": "Legacy.Ordering",
                "to_type": "package",
                "to_name": "Legacy.Ordering",
                "resolved": True,
            },
            {
                "edge_type": "DEPENDS_ON_PROJECT",
                "parser": "dotnet_project",
                "from_type": "project",
                "from_name": "Legacy.Ordering",
                "to_type": "project",
                "to_name": "Legacy.Shared",
                "resolved": True,
                "properties": {
                    "raw_target": r"..\Legacy.Shared\Legacy.Shared.vbproj",
                    "normalized_target": "Legacy.Shared",
                },
            },
            {
                "edge_type": "CONTAINS_PROJECT",
                "parser": "dotnet_solution",
                "from_type": "solution",
                "from_name": "LegacySuite",
                "to_type": "project",
                "to_name": "Legacy.Ordering",
                "resolved": True,
                "properties": {
                    "raw_target": r"src\Legacy.Ordering\Legacy.Ordering.vbproj",
                    "normalized_target": "Legacy.Ordering",
                },
            },
            {
                "edge_type": "DECLARES_CONFIG_FILE",
                "parser": "dotnet_framework_config",
                "from_type": "file",
                "to_type": "config_file",
                "to_name": "Web.config",
                "resolved": True,
            },
            {
                "edge_type": "DECLARES_CONFIG",
                "parser": "dotnet_framework_config",
                "from_type": "config_file",
                "from_name": "Web.config",
                "to_type": "config_value",
                "to_name": "app_setting:InventoryServiceUrl",
                "resolved": True,
            },
            {
                "edge_type": "CONFIGURES_SERVICE",
                "parser": "dotnet_framework_config",
                "from_type": "config_value",
                "from_name": "app_setting:InventoryServiceUrl",
                "to_type": "project",
                "to_name": "inventory-service",
                "resolved": True,
                "properties": {
                    "dependency_scope": "configuration",
                    "interaction_kind": "service_configuration",
                    "target_boundary": "application",
                },
            },
            {
                "edge_type": "CONFIGURES_SERVICE",
                "parser": "dotnet_framework_config",
                "from_type": "config_value",
                "from_name": "wcf_endpoint:InventoryClient",
                "to_type": "project",
                "to_name": "inventory-service",
                "resolved": True,
            },
            {
                "edge_type": "DEPENDS_ON_PACKAGE",
                "parser": "packages_config",
                "from_type": "project",
                "from_name": "Legacy.Ordering",
                "to_type": "package",
                "to_name": "Newtonsoft.Json",
                "resolved": False,
                "properties": {
                    "dependency_type": "packages.config",
                    "version": "13.0.3",
                },
            },
            {
                "edge_type": "DECLARES_BUILD_CONFIG",
                "parser": "dotnet_build_config",
                "from_type": "file",
                "to_type": "build_config",
                "to_name": "Directory.Build.props",
                "resolved": True,
            },
            {
                "edge_type": "DEPENDS_ON_PACKAGE",
                "parser": "dotnet_build_config",
                "from_type": "build_config",
                "from_name": "Directory.Build.props",
                "to_type": "package",
                "to_name": "Microsoft.Net.Compilers.Toolset",
                "resolved": False,
            },
        )

        for expected in expected_entities:
            with self.subTest(expected=expected):
                self.assertTrue(entity_exists(entities, expected), expected)
        for expected in expected_edges:
            with self.subTest(expected=expected):
                self.assertTrue(edge_exists(edges, expected), expected)

        self.assertEqual(graph_data["summary"]["files_scanned"], 7)
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


def build_legacy_dotnet_fixture_graph() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        legacy = root / "legacy-suite"
        ordering = legacy / "src" / "Legacy.Ordering"
        shared = legacy / "src" / "Legacy.Shared"
        inventory = root / "inventory-service"
        ordering.mkdir(parents=True)
        shared.mkdir(parents=True)
        inventory.mkdir()

        (legacy / "LegacySuite.sln").write_text(
            "\n".join(
                [
                    "Microsoft Visual Studio Solution File, Format Version 12.00",
                    (
                        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Legacy.Ordering", '
                        r'"src\Legacy.Ordering\Legacy.Ordering.vbproj", '
                        '"{11111111-1111-1111-1111-111111111111}"'
                    ),
                    "EndProject",
                    (
                        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Legacy.Shared", '
                        r'"src\Legacy.Shared\Legacy.Shared.vbproj", '
                        '"{22222222-2222-2222-2222-222222222222}"'
                    ),
                    "EndProject",
                    "Global",
                    "EndGlobal",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (legacy / "Directory.Build.props").write_text(
            textwrap.dedent(
                """
                <Project>
                  <ItemGroup>
                    <PackageReference Include="Microsoft.Net.Compilers.Toolset" Version="4.8.0" />
                  </ItemGroup>
                </Project>
                """
            ),
            encoding="utf-8",
        )
        (ordering / "Legacy.Ordering.vbproj").write_text(
            textwrap.dedent(
                r"""
                <Project ToolsVersion="15.0">
                  <PropertyGroup>
                    <RootNamespace>Example.Legacy.Ordering</RootNamespace>
                    <AssemblyName>Legacy.Ordering</AssemblyName>
                    <TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
                  </PropertyGroup>
                  <ItemGroup>
                    <ProjectReference Include="..\Legacy.Shared\Legacy.Shared.vbproj" />
                  </ItemGroup>
                </Project>
                """
            ),
            encoding="utf-8",
        )
        (ordering / "packages.config").write_text(
            textwrap.dedent(
                """
                <packages>
                  <package id="Newtonsoft.Json" version="13.0.3" targetFramework="net48" />
                </packages>
                """
            ),
            encoding="utf-8",
        )
        (ordering / "Web.config").write_text(
            textwrap.dedent(
                """
                <configuration>
                  <appSettings>
                    <add key="InventoryServiceUrl" value="http://inventory-service/api" />
                  </appSettings>
                  <connectionStrings>
                    <add name="MainDb"
                         connectionString="Server=example;Database=legacy;"
                         providerName="System.Data.SqlClient" />
                  </connectionStrings>
                  <system.serviceModel>
                    <client>
                      <endpoint name="InventoryClient"
                                address="http://inventory-service/Inventory.svc"
                                binding="basicHttpBinding"
                                contract="Example.IInventory" />
                    </client>
                  </system.serviceModel>
                </configuration>
                """
            ),
            encoding="utf-8",
        )
        (shared / "Legacy.Shared.vbproj").write_text(
            textwrap.dedent(
                """
                <Project ToolsVersion="15.0">
                  <PropertyGroup>
                    <RootNamespace>Example.Legacy.Shared</RootNamespace>
                    <AssemblyName>Legacy.Shared</AssemblyName>
                    <TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
                  </PropertyGroup>
                </Project>
                """
            ),
            encoding="utf-8",
        )
        (inventory / "package.json").write_text('{"name": "@example/inventory-service"}', encoding="utf-8")

        config_path = root / "sources.yaml"
        config_path.write_text(
            textwrap.dedent(
                """
                name: legacy-dotnet-golden-scope
                sources:
                  - type: local_path
                    name: legacy-suite
                    path: legacy-suite
                  - type: local_path
                    name: inventory-service
                    path: inventory-service
                """
            ),
            encoding="utf-8",
        )

        return build_graph(load_config(config_path)).to_dict()


def edge_exists(edges: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    return any(edge_matches(edge, expected) for edge in edges)


def entity_exists(entities: list[dict[str, Any]], expected: dict[str, Any]) -> bool:
    return any(item_matches(entity, expected) for entity in entities)


def edge_matches(edge: dict[str, Any], expected: dict[str, Any]) -> bool:
    return item_matches(edge, expected)


def item_matches(item: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if isinstance(value, dict):
            actual = item.get(key)
            if not isinstance(actual, dict) or not item_matches(actual, value):
                return False
        elif item.get(key) != value:
            return False
    return True
