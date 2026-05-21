from __future__ import annotations

import unittest

from repo_graph.database import (
    CURRENT_DATABASE_SCHEMA_STATE,
    POSTGRES_METADATA_PARSER,
    SQLSERVER_METADATA_PARSER,
    DatabaseConnectorUnavailable,
    DatabaseSourceRequest,
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresMetadata,
    PostgresObjectRow,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerObjectRow,
    database_connector_unavailable_message,
    database_metadata_adapter,
    graph_from_database_metadata,
    graph_from_database_source,
    graph_from_postgres_metadata,
    graph_from_sqlserver_metadata,
    supported_database_engines,
)
from repo_graph.graph import Edge, Graph


class SqlServerMetadataGraphTests(unittest.TestCase):
    def test_adapter_registry_dispatches_supported_engines(self) -> None:
        self.assertEqual(supported_database_engines(), frozenset({"postgres", "sqlserver"}))
        self.assertEqual(database_metadata_adapter("sqlserver").metadata_parser, SQLSERVER_METADATA_PARSER)
        self.assertEqual(database_metadata_adapter("postgres").metadata_parser, POSTGRES_METADATA_PARSER)

        facts = graph_from_database_metadata(
            "current-db",
            "sqlserver",
            SqlServerMetadata(tables=(SqlServerObjectRow("dbo", "Customers"),)),
        )

        self.assertEqual(facts.entities[0].name, "dbo.Customers")

    def test_live_database_connector_reports_safe_unavailable_error(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-db",
            engine="postgres",
            connection_env="REPO_GRAPH_EXAMPLE_POSTGRES_URL",
        )

        with self.assertRaises(DatabaseConnectorUnavailable) as error:
            graph_from_database_source(request)

        self.assertIn("current-db", str(error.exception))
        self.assertIn("postgres", str(error.exception))
        self.assertIn("no live connector enabled yet", str(error.exception))
        self.assertNotIn("REPO_GRAPH_EXAMPLE_POSTGRES_URL", str(error.exception))
        self.assertEqual(
            database_connector_unavailable_message("current-db", "postgres"),
            "Database source 'current-db' uses engine 'postgres', which has a metadata adapter "
            "but no live connector enabled yet.",
        )

    def test_emits_current_database_sql_entities(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "Customers"),),
                views=(SqlServerObjectRow("reporting", "ActiveCustomers"),),
                stored_procedures=(SqlServerObjectRow("dbo", "LoadCustomer"),),
                functions=(SqlServerObjectRow("dbo", "FormatCustomer"),),
            ),
        )

        entities_by_name = {entity.name: entity for entity in facts.entities}

        self.assertEqual(facts.errors, [])
        self.assertEqual(entities_by_name["dbo.Customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["reporting.ActiveCustomers"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["dbo.LoadCustomer"].entity_type, "stored_procedure")
        self.assertEqual(entities_by_name["dbo.FormatCustomer"].entity_type, "sql_function")
        self.assertEqual(entities_by_name["dbo.Customers"].aliases, {"Customers"})
        self.assertEqual(entities_by_name["dbo.Customers"].properties["schema_state"], CURRENT_DATABASE_SCHEMA_STATE)
        self.assertEqual(entities_by_name["dbo.Customers"].properties["database_engine"], "sqlserver")
        self.assertEqual(entities_by_name["dbo.Customers"].properties["metadata_source"], "sys.tables")

    def test_emits_resolved_foreign_key_edge(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(
                    SqlServerObjectRow("dbo", "Customers"),
                    SqlServerObjectRow("dbo", "Orders"),
                ),
                foreign_keys=(
                    SqlServerForeignKeyRow(
                        schema="dbo",
                        table="Orders",
                        referenced_schema="dbo",
                        referenced_table="Customers",
                        name="FK_Orders_Customers",
                    ),
                ),
            ),
        )

        edge = single_edge(facts.edges)

        self.assertEqual(facts.errors, [])
        self.assertTrue(edge.resolved)
        self.assertEqual(edge.from_name, "dbo.Orders")
        self.assertEqual(edge.to_name, "dbo.Customers")
        self.assertEqual(edge.to_type, "sql_table")
        self.assertEqual(edge.edge_type, "REFERENCES_SQL_OBJECT")
        self.assertEqual(edge.parser, SQLSERVER_METADATA_PARSER)
        self.assertEqual(edge.confidence, "high")
        self.assertEqual(edge.properties["target_boundary"], "database")
        self.assertEqual(edge.properties["dependency_scope"], "schema")
        self.assertEqual(edge.properties["interaction_kind"], "sql_schema_reference")
        self.assertEqual(edge.properties["sql_operation"], "FOREIGN_KEY")
        self.assertEqual(edge.properties["metadata_source"], "sys.foreign_keys")
        self.assertEqual(edge.properties["constraint_name"], "FK_Orders_Customers")
        self.assertEqual(edge.identity_key, "foreign_key|dbo.Orders|dbo.Customers|FK_Orders_Customers")

    def test_same_table_pair_foreign_keys_keep_distinct_edge_ids(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(
                    SqlServerObjectRow("dbo", "Customers"),
                    SqlServerObjectRow("dbo", "Orders"),
                ),
                foreign_keys=(
                    SqlServerForeignKeyRow(
                        schema="dbo",
                        table="Orders",
                        referenced_schema="dbo",
                        referenced_table="Customers",
                        name="FK_Orders_BillingCustomer",
                    ),
                    SqlServerForeignKeyRow(
                        schema="dbo",
                        table="Orders",
                        referenced_schema="dbo",
                        referenced_table="Customers",
                        name="FK_Orders_ShippingCustomer",
                    ),
                ),
            ),
        )

        graph = Graph(scope_name="test", sources=[])
        for entity in facts.entities:
            graph.add_entity(entity)
        for edge in facts.edges:
            graph.add_edge(edge)

        self.assertEqual(facts.errors, [])
        self.assertEqual(len(facts.edges), 2)
        self.assertEqual(len({edge.edge_id for edge in facts.edges}), 2)
        self.assertEqual(len(graph.edges), 2)

    def test_missing_foreign_key_target_stays_unresolved(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "Orders"),),
                foreign_keys=(
                    SqlServerForeignKeyRow(
                        schema="dbo",
                        table="Orders",
                        referenced_schema="dbo",
                        referenced_table="Customers",
                    ),
                ),
            ),
        )

        edge = single_edge(facts.edges)

        self.assertEqual(facts.errors, [])
        self.assertFalse(edge.resolved)
        self.assertIsNone(edge.to_entity_id)
        self.assertEqual(edge.to_name, "dbo.Customers")
        self.assertEqual(edge.to_type, "sql_table")

    def test_ambiguous_dependency_target_stays_unresolved_with_candidates(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "CustomerFacts"),),
                views=(SqlServerObjectRow("dbo", "CustomerFacts"),),
                stored_procedures=(SqlServerObjectRow("dbo", "LoadCustomerFacts"),),
                dependencies=(
                    SqlServerDependencyRow(
                        from_schema="dbo",
                        from_name="LoadCustomerFacts",
                        from_type="stored_procedure",
                        to_schema="dbo",
                        to_name="CustomerFacts",
                        to_type="sql_object",
                    ),
                ),
            ),
        )

        edge = single_edge(facts.edges)

        self.assertEqual(facts.errors, [])
        self.assertFalse(edge.resolved)
        self.assertEqual(edge.properties["resolution_status"], "ambiguous")
        self.assertEqual(
            {candidate["entity_type"] for candidate in edge.properties["resolution_candidates"]},
            {"sql_table", "sql_view"},
        )

    def test_missing_dependency_source_is_reported(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "Customers"),),
                dependencies=(
                    SqlServerDependencyRow(
                        from_schema="dbo",
                        from_name="MissingProcedure",
                        from_type="stored_procedure",
                        to_schema="dbo",
                        to_name="Customers",
                        to_type="table",
                    ),
                ),
            ),
        )

        self.assertEqual(facts.edges, [])
        self.assertEqual(facts.errors, ["Missing source entity for SQL Server dependency: dbo.MissingProcedure"])

    def test_module_dependency_edges_use_generic_reference_until_operation_is_known(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "Customers"),),
                stored_procedures=(SqlServerObjectRow("dbo", "LoadCustomer"),),
                dependencies=(
                    SqlServerDependencyRow(
                        from_schema="dbo",
                        from_name="LoadCustomer",
                        from_type="stored_procedure",
                        to_schema="dbo",
                        to_name="Customers",
                        to_type="table",
                    ),
                ),
            ),
        )

        edge = single_edge(facts.edges)

        self.assertEqual(facts.errors, [])
        self.assertTrue(edge.resolved)
        self.assertEqual(edge.edge_type, "REFERENCES_SQL_OBJECT")
        self.assertEqual(edge.from_type, "stored_procedure")
        self.assertEqual(edge.to_type, "sql_table")
        self.assertEqual(edge.properties["dependency_scope"], "schema")
        self.assertEqual(edge.properties["interaction_kind"], "sql_schema_reference")
        self.assertEqual(edge.properties["sql_operation"], "MODULE_REFERENCE")
        self.assertEqual(edge.properties["metadata_source"], "sys.sql_expression_dependencies")

    def test_execute_dependency_emits_sql_call(self) -> None:
        facts = graph_from_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                stored_procedures=(
                    SqlServerObjectRow("dbo", "RunBatch"),
                    SqlServerObjectRow("dbo", "LoadCustomer"),
                ),
                dependencies=(
                    SqlServerDependencyRow(
                        from_schema="dbo",
                        from_name="RunBatch",
                        to_schema="dbo",
                        to_name="LoadCustomer",
                        to_type="stored_procedure",
                        dependency_type="execute",
                    ),
                ),
            ),
        )

        edge = single_edge(facts.edges)

        self.assertEqual(facts.errors, [])
        self.assertTrue(edge.resolved)
        self.assertEqual(edge.edge_type, "CALLS_SQL")
        self.assertEqual(edge.to_type, "stored_procedure")
        self.assertEqual(edge.properties["dependency_scope"], "runtime")
        self.assertEqual(edge.properties["interaction_kind"], "sql_reference")
        self.assertEqual(edge.properties["sql_operation"], "EXECUTE")

    def test_postgres_metadata_emits_current_database_entities_and_edges(self) -> None:
        facts = graph_from_postgres_metadata(
            "current-pg",
            PostgresMetadata(
                tables=(
                    PostgresObjectRow("public", "customers"),
                    PostgresObjectRow("public", "orders"),
                ),
                views=(PostgresObjectRow("reporting", "active_customers"),),
                materialized_views=(PostgresObjectRow("reporting", "customer_rollup"),),
                functions=(PostgresObjectRow("public", "format_customer"),),
                procedures=(PostgresObjectRow("public", "refresh_customer"),),
                foreign_keys=(
                    PostgresForeignKeyRow(
                        schema="public",
                        table="orders",
                        referenced_schema="public",
                        referenced_table="customers",
                        name="orders_customer_id_fkey",
                    ),
                ),
                dependencies=(
                    PostgresDependencyRow(
                        from_schema="public",
                        from_name="refresh_customer",
                        from_type="procedure",
                        to_schema="public",
                        to_name="format_customer",
                        to_type="function",
                        dependency_type="execute",
                    ),
                ),
            ),
        )

        entities_by_name = {entity.name: entity for entity in facts.entities}
        edges_by_operation = {edge.properties["sql_operation"]: edge for edge in facts.edges}

        self.assertEqual(facts.errors, [])
        self.assertEqual(entities_by_name["public.customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["reporting.active_customers"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["reporting.customer_rollup"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["public.refresh_customer"].entity_type, "stored_procedure")
        self.assertEqual(entities_by_name["public.format_customer"].entity_type, "sql_function")
        self.assertEqual(entities_by_name["public.customers"].properties["database_engine"], "postgres")
        self.assertEqual(entities_by_name["public.customers"].properties["metadata_source"], "pg_class")
        self.assertEqual(
            entities_by_name["reporting.customer_rollup"].properties["postgres_relkind"],
            "materialized_view",
        )
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].parser, POSTGRES_METADATA_PARSER)
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].properties["metadata_source"], "pg_constraint")
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].properties["database_engine"], "postgres")
        self.assertEqual(edges_by_operation["EXECUTE"].edge_type, "CALLS_SQL")
        self.assertEqual(edges_by_operation["EXECUTE"].to_type, "sql_function")


def single_edge(edges: list[Edge]) -> Edge:
    if len(edges) != 1:
        raise AssertionError(f"Expected exactly one edge, found {len(edges)}.")
    return edges[0]
