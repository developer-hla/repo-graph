from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from repo_graph.config import load_config
from repo_graph.scanner import build_graph


class ScannerTests(unittest.TestCase):
    def test_build_graph_from_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "service"
            repo.mkdir()
            (repo / "package.json").write_text(
                '{"name": "@example/service", "dependencies": {"@example/lib": "1.0.0"}}',
                encoding="utf-8",
            )
            (repo / "api.ts").write_text(
                """
import { helper } from '@example/lib';
router.get('/health', handler);
const sql = 'EXEC dbo.get_things';
""",
                encoding="utf-8",
            )
            (repo / "schema.sql").write_text(
                """
CREATE PROCEDURE dbo.get_things AS
SELECT * FROM dbo.things
CREATE TABLE dbo.things (id int)
""",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: service
    path: service
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 3)
        self.assertGreaterEqual(graph_data["summary"]["entity_count"], 6)
        self.assertIn("CONTAINS_PROJECT", graph_data["edge_counts"])
        self.assertIn("DECLARES_ROUTE", graph_data["edge_counts"])
        self.assertIn("DEPENDS_ON_PACKAGE", graph_data["edge_counts"])
        self.assertIn("CALLS_SQL", graph_data["edge_counts"])
        self.assertIn("DEFINES", graph_data["edge_counts"])
        self.assertGreater(graph_data["summary"]["resolved_edge_count"], 0)

    def test_build_graph_resolves_cross_source_code_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            service = root / "api-service"
            shared = root / "shared-library"
            inventory = root / "inventory-service"
            for repo in (service, shared, inventory):
                (repo / "src").mkdir(parents=True)

            (service / "package.json").write_text(
                '{"name": "@example/api-service", "dependencies": {"@example/lib": "1.0.0"}}',
                encoding="utf-8",
            )
            (service / "src" / "index.ts").write_text(
                """
import { helper } from '@example/lib';
const server = fastify();
export async function loadThing(id: string) {
  await fetch(`/things/${id}`);
  await fetch(`${process.env.INVENTORY_SERVICE_URL}/inventory/${id}`);
}
server.get('/things/:id', handler);
""",
                encoding="utf-8",
            )
            (shared / "package.json").write_text('{"name": "@example/lib"}', encoding="utf-8")
            (shared / "src" / "index.ts").write_text(
                "export function helper() { return 'ok'; }",
                encoding="utf-8",
            )
            (inventory / "package.json").write_text('{"name": "@example/inventory-service"}', encoding="utf-8")
            (inventory / "src" / "index.ts").write_text(
                "server.get('/inventory/:id', handler);",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: api-service
    path: api-service
  - type: local_path
    name: shared-library
    path: shared-library
  - type: local_path
    name: inventory-service
    path: inventory-service
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 6)
        self.assertIn("DECLARES_SYMBOL", graph_data["edge_counts"])
        self.assertIn("CALLS_HTTP", graph_data["edge_counts"])
        self.assertIn("CALLS_SERVICE", graph_data["edge_counts"])
        self.assertTrue(
            any(
                edge["edge_type"] == "IMPORTS" and edge["to_name"] == "@example/lib" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "DEPENDS_ON_PACKAGE" and edge["to_name"] == "@example/lib" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_HTTP" and edge["to_name"] == "GET /things/:param" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_SERVICE" and edge["to_name"] == "inventory-service" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )

    def test_build_graph_discovers_python_and_dotnet_manifest_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            python_shared = root / "python-shared"
            python_service = root / "python-service"
            dotnet_service = root / "dotnet-service"
            (dotnet_service / "src" / "Example.Service").mkdir(parents=True)
            (dotnet_service / "src" / "Example.Shared").mkdir(parents=True)
            python_shared.mkdir()
            python_service.mkdir()

            (python_shared / "pyproject.toml").write_text(
                """
[project]
name = "example-python-shared"
version = "0.1.0"
""",
                encoding="utf-8",
            )
            (python_service / "pyproject.toml").write_text(
                """
[project]
name = "example-python-service"
version = "0.1.0"
dependencies = [
  "fastapi>=0.110",
  "example-python-shared==0.1.0",
  "requests>=2.31",
  "sqlalchemy>=2",
]
""",
                encoding="utf-8",
            )
            (python_service / "requirements.txt").write_text("httpx==0.27.0\n", encoding="utf-8")
            (dotnet_service / "Example.sln").write_text(
                """
Project("{TYPE}") = "Example.Service", "src\\Example.Service\\Example.Service.csproj", "{SERVICE}"
EndProject
Project("{TYPE}") = "Example.Shared", "src\\Example.Shared\\Example.Shared.csproj", "{SHARED}"
EndProject
""",
                encoding="utf-8",
            )
            (dotnet_service / "Directory.Build.props").write_text(
                """
<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.Extensions.Logging" Version="8.0.0" />
  </ItemGroup>
</Project>
""",
                encoding="utf-8",
            )
            (dotnet_service / "src" / "Example.Shared" / "Example.Shared.csproj").write_text(
                """
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <PackageId>Example.Shared</PackageId>
  </PropertyGroup>
</Project>
""",
                encoding="utf-8",
            )
            (dotnet_service / "src" / "Example.Service" / "Example.Service.csproj").write_text(
                """
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <PackageId>Example.Service</PackageId>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Example.Shared" Version="0.1.0" />
    <ProjectReference Include="../Example.Shared/Example.Shared.csproj" />
  </ItemGroup>
</Project>
""",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: python-shared
    path: python-shared
  - type: local_path
    name: python-service
    path: python-service
  - type: local_path
    name: dotnet-service
    path: dotnet-service
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 7)
        self.assertIn("DECLARES_BUILD_CONFIG", graph_data["edge_counts"])
        self.assertIn("DECLARES_SOLUTION", graph_data["edge_counts"])
        self.assertIn("DEPENDS_ON_PROJECT", graph_data["edge_counts"])
        self.assertTrue(
            any(
                entity["entity_type"] == "project" and entity["properties"].get("ecosystem") == "python"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                entity["entity_type"] == "project" and entity["properties"].get("ecosystem") == "dotnet"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "DEPENDS_ON_PACKAGE"
                and edge["to_name"] == "example-python-shared"
                and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "DEPENDS_ON_PACKAGE" and edge["to_name"] == "Example.Shared" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "DEPENDS_ON_PROJECT" and edge["to_name"] == "Example.Shared" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )

    def test_build_graph_discovers_python_code_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            python_shared = root / "python-shared"
            python_service = root / "python-service"
            inventory_service = root / "inventory-service"
            database_project = root / "database-project"
            (python_shared / "example_python_shared").mkdir(parents=True)
            (python_service / "example_python_worker").mkdir(parents=True)
            inventory_service.mkdir()
            database_project.mkdir()

            (python_shared / "pyproject.toml").write_text(
                """
[project]
name = "example-python-shared"
version = "0.1.0"
""",
                encoding="utf-8",
            )
            (python_shared / "example_python_shared" / "__init__.py").write_text(
                "from example_python_shared.formatting import format_thing\n",
                encoding="utf-8",
            )
            (python_shared / "example_python_shared" / "formatting.py").write_text(
                """
class ThingFormatter:
    def format(self, value: str) -> dict[str, str]:
        return {"label": value}


def format_thing(value: str) -> dict[str, str]:
    return ThingFormatter().format(value)
""",
                encoding="utf-8",
            )
            (python_service / "pyproject.toml").write_text(
                """
[project]
name = "example-python-worker"
version = "0.1.0"
dependencies = [
  "fastapi>=0.110",
  "example-python-shared==0.1.0",
  "requests>=2.31",
  "sqlalchemy>=2",
]
""",
                encoding="utf-8",
            )
            (python_service / "example_python_worker" / "app.py").write_text(
                """
import os

import requests
from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from example_python_shared import format_thing

app = FastAPI()
router = APIRouter()


class Worker:
    def fetch_inventory(self, thing_id: str) -> dict[str, str]:
        response = requests.get(f"{os.environ['INVENTORY_SERVICE_URL']}/inventory/{thing_id}")
        return response.json()


@router.get("/things/{thing_id}")
async def read_thing(thing_id: str) -> dict[str, str]:
    Worker().fetch_inventory(thing_id)
    query = text("EXEC dbo.get_thing_by_id")
    return format_thing(str(query))
""",
                encoding="utf-8",
            )
            (inventory_service / "package.json").write_text(
                '{"name": "@example/inventory-service"}',
                encoding="utf-8",
            )
            (database_project / "schema.sql").write_text(
                "CREATE PROCEDURE dbo.get_thing_by_id AS SELECT 1",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: python-shared
    path: python-shared
  - type: local_path
    name: python-service
    path: python-service
  - type: local_path
    name: inventory-service
    path: inventory-service
  - type: local_path
    name: database-project
    path: database-project
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 7)
        self.assertIn("IMPORTS", graph_data["edge_counts"])
        self.assertIn("DECLARES_SYMBOL", graph_data["edge_counts"])
        self.assertIn("DECLARES_ROUTE", graph_data["edge_counts"])
        self.assertIn("EXPOSES_ROUTE", graph_data["edge_counts"])
        self.assertIn("CALLS_SERVICE", graph_data["edge_counts"])
        self.assertIn("CALLS_SQL", graph_data["edge_counts"])
        self.assertTrue(
            any(
                entity["entity_type"] == "api_route" and entity["name"] == "GET /things/{thing_id}"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                entity["entity_type"] == "function" and entity["name"] == "example_python_worker.app.read_thing"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "IMPORTS" and edge["to_name"] == "example-python-shared" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_SERVICE" and edge["to_name"] == "inventory-service" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_SQL" and edge["to_name"] == "dbo.get_thing_by_id" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )

    def test_build_graph_discovers_workspace_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = root / "workspace"
            (repo / "packages" / "shared").mkdir(parents=True)
            (repo / "services" / "api").mkdir(parents=True)
            (repo / "package.json").write_text(
                '{"name": "@example/root", "workspaces": ["packages/*"]}',
                encoding="utf-8",
            )
            (repo / "pnpm-workspace.yaml").write_text(
                """
packages:
  - packages/*
  - services/*
""",
                encoding="utf-8",
            )
            (repo / "packages" / "shared" / "package.json").write_text(
                '{"name": "@example/shared"}',
                encoding="utf-8",
            )
            (repo / "services" / "api" / "package.json").write_text(
                '{"name": "@example/api", "dependencies": {"@example/shared": "0.1.0"}}',
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: workspace
    path: workspace
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 4)
        self.assertIn("DECLARES_WORKSPACE", graph_data["edge_counts"])
        self.assertTrue(any(entity["entity_type"] == "workspace" for entity in graph_data["entities"]))
        self.assertTrue(
            any(
                edge["edge_type"] == "DEPENDS_ON_PACKAGE" and edge["to_name"] == "@example/shared" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )

    def test_build_graph_discovers_legacy_vb_dotnet_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy_service = root / "legacy-service"
            inventory_service = root / "inventory-service"
            legacy_service.mkdir()
            inventory_service.mkdir()

            (inventory_service / "package.json").write_text(
                '{"name": "@example/inventory-service"}',
                encoding="utf-8",
            )
            (legacy_service / "Legacy.Service.vbproj").write_text(
                """
<Project ToolsVersion="15.0">
  <PropertyGroup>
    <RootNamespace>Example.Legacy</RootNamespace>
    <AssemblyName>Legacy.Service</AssemblyName>
    <TargetFrameworkVersion>v4.8</TargetFrameworkVersion>
  </PropertyGroup>
</Project>
""",
                encoding="utf-8",
            )
            (legacy_service / "packages.config").write_text(
                """
<packages>
  <package id="Newtonsoft.Json" version="13.0.3" targetFramework="net48" />
</packages>
""",
                encoding="utf-8",
            )
            (legacy_service / "Web.config").write_text(
                """
<configuration>
  <appSettings>
    <add key="InventoryServiceUrl" value="http://inventory-service/api" />
  </appSettings>
  <connectionStrings>
    <add name="MainDb" connectionString="Server=example;Database=example;" providerName="System.Data.SqlClient" />
  </connectionStrings>
  <system.serviceModel>
    <client>
      <endpoint name="InventoryServiceUrl"
                address="http://inventory-service/Inventory.svc"
                binding="basicHttpBinding"
                contract="Example.IInventory" />
    </client>
  </system.serviceModel>
</configuration>
""",
                encoding="utf-8",
            )
            (legacy_service / "LegacyOrderService.asmx").write_text(
                '<%@ WebService Language="VB" CodeBehind="LegacyOrderService.asmx.vb" '
                'Class="Example.Legacy.LegacyOrderService" %>',
                encoding="utf-8",
            )
            (legacy_service / "LegacyOrderService.asmx.vb").write_text(
                """
Imports System.Configuration
Imports System.Data
Imports System.Data.SqlClient
Imports System.Net
Imports System.Web.Services

Namespace Example.Legacy
  Public Class LegacyOrderService
    <WebMethod()>
    Public Function GetOrder(id As Integer) As String
      Dim baseUrl = ConfigurationManager.AppSettings("InventoryServiceUrl")
      Dim request = WebRequest.Create("http://inventory-service/api/orders/" & id)
      Dim command As New SqlCommand("dbo.GetOrder")
      command.CommandType = CommandType.StoredProcedure
      Return baseUrl
    End Function
  End Class
End Namespace
""",
                encoding="utf-8",
            )
            (legacy_service / "schema.sql").write_text(
                "CREATE PROCEDURE dbo.GetOrder AS SELECT 1",
                encoding="utf-8",
            )
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: legacy-service
    path: legacy-service
  - type: local_path
    name: inventory-service
    path: inventory-service
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            graph_data = graph.to_dict()

        self.assertEqual(graph_data["summary"]["files_scanned"], 7)
        self.assertIn("DECLARES_CONFIG_FILE", graph_data["edge_counts"])
        self.assertIn("DECLARES_CONFIG", graph_data["edge_counts"])
        self.assertIn("CONFIGURES_SERVICE", graph_data["edge_counts"])
        self.assertIn("DECLARES_ROUTE", graph_data["edge_counts"])
        self.assertIn("DECLARES_SYMBOL", graph_data["edge_counts"])
        self.assertIn("CALLS_SERVICE", graph_data["edge_counts"])
        self.assertIn("CALLS_SQL", graph_data["edge_counts"])
        self.assertIn("DEPENDS_ON_PACKAGE", graph_data["edge_counts"])
        self.assertTrue(
            any(
                entity["entity_type"] == "api_route" and entity["name"] == "POST /LegacyOrderService.asmx/GetOrder"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                entity["entity_type"] == "function" and entity["name"] == "Example.Legacy.LegacyOrderService.GetOrder"
                for entity in graph_data["entities"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_SQL" and edge["to_name"] == "dbo.GetOrder" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CALLS_SERVICE" and edge["to_name"] == "inventory-service" and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["edge_type"] == "CONFIGURES_SERVICE"
                and edge["to_name"] == "inventory-service"
                and edge["resolved"]
                for edge in graph_data["edges"]
            )
        )

    def test_strict_build_raises_on_missing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "sources.yaml"
            config_path.write_text(
                """
name: test-scope
sources:
  - type: local_path
    name: missing
    path: missing
""",
                encoding="utf-8",
            )
            config = load_config(config_path)

            graph = build_graph(config)
            with self.assertRaisesRegex(RuntimeError, "scanner errors"):
                build_graph(config, strict=True)

        self.assertEqual(graph.errors, ["Missing source path: {}".format((root / "missing").resolve())])


if __name__ == "__main__":
    unittest.main()
