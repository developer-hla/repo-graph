from __future__ import annotations

import unittest

from repo_graph.database import (
    CURRENT_DATABASE_SCHEMA_STATE,
    SQLSERVER_METADATA_PARSER,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerObjectRow,
    graph_from_sqlserver_metadata,
)
from repo_graph.graph import Edge, Graph


class SqlServerMetadataGraphTests(unittest.TestCase):
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


def single_edge(edges: list[Edge]) -> Edge:
    if len(edges) != 1:
        raise AssertionError(f"Expected exactly one edge, found {len(edges)}.")
    return edges[0]
