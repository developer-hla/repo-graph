from __future__ import annotations

import unittest
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact
from repo_graph.extraction.scanners.interactions.services import service_configuration_fact
from repo_graph.sources import ResolvedSource


def example_context() -> FileScanContext:
    source = ResolvedSource(
        name="api-service",
        source_type="local_path",
        path=Path("api-service"),
        url=None,
        ref="HEAD",
        commit=None,
    )
    repo = EntityFact(entity_type="repo", name="api-service", source_name=source.name)
    file = EntityFact(entity_type="file", name="app.config", source_name=source.name, file_path="app.config")
    return FileScanContext(
        source=source,
        repo_entity=repo,
        file_entity=file,
        file_path=Path("api-service/app.config"),
        rel_path="app.config",
    )


class InteractionFactHelperTests(unittest.TestCase):
    def test_service_configuration_fact_uses_structured_interaction_evidence(self) -> None:
        context = example_context()
        config_value = EntityFact(
            entity_type="config_value",
            name="app_setting:InventoryServiceUrl",
            source_name=context.source.name,
            file_path=context.rel_path,
        )

        fact = service_configuration_fact(
            config_value.reference,
            "https://inventory-service.example.com/api/orders?include=summary",
            context,
            "dotnet_framework_config",
        )

        self.assertEqual(fact.edge_type, "CONFIGURES_SERVICE")
        self.assertEqual(fact.to_type, "service")
        self.assertEqual(fact.to_name, "inventory-service")
        self.assertFalse(fact.resolved)
        self.assertEqual(fact.properties["target_boundary"], "application")
        self.assertEqual(fact.properties["dependency_scope"], "configuration")
        self.assertEqual(fact.properties["interaction_kind"], "service_configuration")
        self.assertEqual(
            fact.properties["raw_target"], "https://inventory-service.example.com/api/orders?include=summary"
        )
        self.assertEqual(fact.properties["normalized_target"], "GET /api/orders")
        self.assertEqual(fact.properties["service_name"], "inventory-service")

    def test_service_configuration_fact_preserves_explicit_service_name_and_config_key(self) -> None:
        context = example_context()
        config_value = EntityFact(
            entity_type="config_value",
            name="env:api-service:INVENTORY_SERVICE_URL",
            source_name=context.source.name,
            file_path=context.rel_path,
        )

        fact = service_configuration_fact(
            config_value.reference,
            "INVENTORY_SERVICE_URL",
            context,
            "kubernetes_env",
            service_name="inventory-service",
            extra_properties={"config_key": "INVENTORY_SERVICE_URL"},
        )

        self.assertEqual(fact.to_name, "inventory-service")
        self.assertEqual(fact.properties["target_boundary"], "application")
        self.assertEqual(fact.properties["dependency_scope"], "configuration")
        self.assertEqual(fact.properties["interaction_kind"], "service_configuration")
        self.assertEqual(fact.properties["raw_target"], "INVENTORY_SERVICE_URL")
        self.assertEqual(fact.properties["target_env_var"], "INVENTORY_SERVICE_URL")
        self.assertEqual(fact.properties["config_key"], "INVENTORY_SERVICE_URL")

    def test_service_configuration_fact_falls_back_to_identifier_when_target_has_no_host(self) -> None:
        context = example_context()
        config_value = EntityFact(
            entity_type="config_value",
            name="app_setting:InventoryApiBaseUrl",
            source_name=context.source.name,
            file_path=context.rel_path,
        )

        fact = service_configuration_fact(
            config_value.reference,
            "/api/orders",
            context,
            "dotnet_framework_config",
            fallback_identifier="InventoryApi",
        )

        self.assertEqual(fact.to_name, "inventory-api")
        self.assertEqual(fact.properties["service_name"], "inventory-api")


if __name__ == "__main__":
    unittest.main()
