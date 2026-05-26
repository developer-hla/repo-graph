from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from repo_graph.database import (
    CURRENT_DATABASE_SCHEMA_STATE,
    POSTGRES_METADATA_PARSER,
    SQLSERVER_METADATA_PARSER,
    DatabaseSourceRequest,
    PostgresDependencyRow,
    PostgresForeignKeyRow,
    PostgresMetadata,
    PostgresObjectRow,
    PostgresTriggerRow,
    SqlServerDependencyRow,
    SqlServerForeignKeyRow,
    SqlServerMetadata,
    SqlServerObjectRow,
    SqlServerTriggerRow,
    database_connector_unavailable_message,
    database_metadata_adapter,
    scan_database_metadata,
    scan_database_source,
    scan_postgres_metadata,
    scan_postgres_source,
    scan_sqlserver_metadata,
    scan_sqlserver_source,
    supported_database_engines,
)
from repo_graph.extraction.facts import RelationshipFact
from repo_graph.graph import Graph, add_facts_to_graph


class DatabaseMetadataGraphTests(unittest.TestCase):
    def test_adapter_registry_dispatches_supported_engines(self) -> None:
        self.assertEqual(supported_database_engines(), frozenset({"postgres", "sqlserver"}))
        self.assertEqual(database_metadata_adapter("sqlserver").metadata_parser, SQLSERVER_METADATA_PARSER)
        self.assertEqual(database_metadata_adapter("postgres").metadata_parser, POSTGRES_METADATA_PARSER)

        facts = scan_database_metadata(
            "current-db",
            "sqlserver",
            SqlServerMetadata(tables=(SqlServerObjectRow("dbo", "Customers"),)),
        )

        self.assertEqual(facts.entities[0].name, "dbo.Customers")

    def test_postgres_live_connector_reports_missing_driver_without_secret_value(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-db",
            engine="postgres",
            connection_env="REPO_GRAPH_EXAMPLE_POSTGRES_URL",
        )

        with (
            patch.dict("os.environ", {"REPO_GRAPH_EXAMPLE_POSTGRES_URL": "postgres://user:secret@localhost/db"}),
            patch("repo_graph.database._metadata.postgres_driver_available", return_value=False),
        ):
            facts = scan_database_source(request)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(
            facts.errors,
            ["PostgreSQL connector requires optional dependency 'psycopg' for database source 'current-db'."],
        )
        self.assertNotIn("REPO_GRAPH_EXAMPLE_POSTGRES_URL", facts.errors[0])
        self.assertNotIn("secret", facts.errors[0])

    def test_live_database_connector_reports_safe_unavailable_error_for_missing_engine(self) -> None:
        self.assertEqual(
            database_connector_unavailable_message("current-db", None),
            "Database source 'current-db' is missing a database engine.",
        )

    def test_sqlserver_live_connector_reads_catalog_metadata(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-db",
            engine="sqlserver",
            connection_env="REPO_GRAPH_EXAMPLE_SQLSERVER_URL",
            schemas=("dbo",),
            query_timeout_seconds=7,
            max_metadata_rows=20,
        )
        connection = FakeSqlServerConnection()

        with patch.dict("os.environ", {"REPO_GRAPH_EXAMPLE_SQLSERVER_URL": "Driver=example"}):
            facts = scan_sqlserver_source(request, connect=lambda connection_string, timeout: connection)

        entities_by_name = {entity.name: entity for entity in facts.entities}
        edges_by_operation = {edge.properties["sql_operation"]: edge for edge in facts.edges}

        self.assertEqual(facts.errors, [])
        self.assertTrue(connection.closed)
        self.assertEqual(connection.cursor_instance.timeout, 7)
        self.assertEqual(entities_by_name["dbo.Customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["dbo.Orders.TR_Orders_Audit"].entity_type, "sql_trigger")
        self.assertEqual(entities_by_name["dbo.LoadCustomer"].entity_type, "stored_procedure")
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].to_name, "dbo.Customers")
        self.assertEqual(edges_by_operation["TRIGGER_ON"].edge_type, "TRIGGERS_ON_SQL_OBJECT")
        self.assertEqual(
            edges_by_operation["MODULE_REFERENCE"].properties["metadata_source"], "sys.sql_expression_dependencies"
        )

    def test_sqlserver_live_connector_reports_missing_env_without_secret_value(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-db",
            engine="sqlserver",
            connection_env="REPO_GRAPH_EXAMPLE_SQLSERVER_URL",
        )

        facts = scan_sqlserver_source(request, connect=lambda _connection_string, _timeout: None)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(
            facts.errors,
            ["Database source 'current-db' connection_env is not set in the runtime environment."],
        )
        self.assertNotIn("REPO_GRAPH_EXAMPLE_SQLSERVER_URL", facts.errors[0])

    def test_sqlserver_live_connector_reports_unconfigured_connection_env(self) -> None:
        request = DatabaseSourceRequest(source_name="current-db", engine="sqlserver", connection_env="")

        facts = scan_sqlserver_source(request, connect=lambda _connection_string, _timeout: None)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(facts.errors, ["Database source 'current-db' connection_env is not configured."])

    def test_sqlserver_live_connector_redacts_connection_string_from_driver_errors(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-db",
            engine="sqlserver",
            connection_env="REPO_GRAPH_EXAMPLE_SQLSERVER_URL",
        )

        def fail_connection(connection_string: str, _timeout: int) -> None:
            raise RuntimeError(f"could not open {connection_string}")

        with patch.dict("os.environ", {"REPO_GRAPH_EXAMPLE_SQLSERVER_URL": "Driver=example;Pwd=secret"}):
            facts = scan_sqlserver_source(request, connect=fail_connection)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(
            facts.errors,
            ["SQL Server metadata connection failed for 'current-db': RuntimeError: could not open [redacted]"],
        )
        self.assertNotIn("secret", facts.errors[0])

    def test_postgres_live_connector_reads_catalog_metadata(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-pg",
            engine="postgres",
            connection_env="REPO_GRAPH_EXAMPLE_POSTGRES_URL",
            schemas=("public",),
            query_timeout_seconds=7,
            max_metadata_rows=20,
        )
        connection = FakePostgresConnection()

        with patch.dict("os.environ", {"REPO_GRAPH_EXAMPLE_POSTGRES_URL": "postgres://example"}):
            facts = scan_postgres_source(request, connect=lambda _connection_string, _timeout: connection)

        entities_by_name = {entity.name: entity for entity in facts.entities}
        edges_by_operation = {edge.properties["sql_operation"]: edge for edge in facts.edges}

        self.assertEqual(facts.errors, [])
        self.assertTrue(connection.closed)
        self.assertEqual(connection.cursor_instance.statement_timeout_ms, 7000)
        self.assertEqual(entities_by_name["public.customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["public.active_customers"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["public.customer_rollup"].properties["postgres_relkind"], "materialized_view")
        self.assertEqual(entities_by_name["public.orders.orders_audit_trigger"].entity_type, "sql_trigger")
        self.assertEqual(entities_by_name["public.refresh_customer"].entity_type, "stored_procedure")
        self.assertEqual(entities_by_name["public.format_customer"].entity_type, "sql_function")
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].to_name, "public.customers")
        self.assertEqual(edges_by_operation["TRIGGER_ON"].edge_type, "TRIGGERS_ON_SQL_OBJECT")
        self.assertEqual(edges_by_operation["EXECUTE"].from_type, "sql_trigger")
        self.assertEqual(edges_by_operation["OBJECT_DEPENDENCY"].properties["metadata_source"], "pg_depend")

    def test_postgres_live_connector_reports_missing_env_without_secret_value(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-pg",
            engine="postgres",
            connection_env="REPO_GRAPH_EXAMPLE_POSTGRES_URL",
        )

        facts = scan_postgres_source(request, connect=lambda _connection_string, _timeout: None)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(
            facts.errors,
            ["Database source 'current-pg' connection_env is not set in the runtime environment."],
        )
        self.assertNotIn("REPO_GRAPH_EXAMPLE_POSTGRES_URL", facts.errors[0])

    def test_postgres_live_connector_redacts_connection_string_from_driver_errors(self) -> None:
        request = DatabaseSourceRequest(
            source_name="current-pg",
            engine="postgres",
            connection_env="REPO_GRAPH_EXAMPLE_POSTGRES_URL",
        )

        def fail_connection(connection_string: str, _timeout: int) -> None:
            raise RuntimeError(f"could not open {connection_string}")

        with patch.dict("os.environ", {"REPO_GRAPH_EXAMPLE_POSTGRES_URL": "postgres://user:secret@localhost/db"}):
            facts = scan_postgres_source(request, connect=fail_connection)

        self.assertEqual(facts.entities, [])
        self.assertEqual(facts.edges, [])
        self.assertEqual(
            facts.errors,
            ["PostgreSQL metadata connection failed for 'current-pg': RuntimeError: could not open [redacted]"],
        )
        self.assertNotIn("secret", facts.errors[0])

    def test_emits_current_database_sql_entities(self) -> None:
        facts = scan_sqlserver_metadata(
            "current-db",
            SqlServerMetadata(
                tables=(SqlServerObjectRow("dbo", "Customers"),),
                views=(SqlServerObjectRow("reporting", "ActiveCustomers"),),
                stored_procedures=(SqlServerObjectRow("dbo", "LoadCustomer"),),
                functions=(SqlServerObjectRow("dbo", "FormatCustomer"),),
                triggers=(
                    SqlServerTriggerRow(
                        schema="dbo",
                        name="TR_Customers_Audit",
                        table_schema="dbo",
                        table="Customers",
                        events=("INSERT", "UPDATE"),
                        is_disabled=False,
                    ),
                ),
            ),
        )

        entities_by_name = {entity.name: entity for entity in facts.entities}
        edges_by_operation = {edge.properties["sql_operation"]: edge for edge in facts.edges}

        self.assertEqual(facts.errors, [])
        self.assertEqual(entities_by_name["dbo.Customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["reporting.ActiveCustomers"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["dbo.LoadCustomer"].entity_type, "stored_procedure")
        self.assertEqual(entities_by_name["dbo.FormatCustomer"].entity_type, "sql_function")
        self.assertEqual(entities_by_name["dbo.Customers.TR_Customers_Audit"].entity_type, "sql_trigger")
        self.assertEqual(entities_by_name["dbo.Customers"].aliases, {"Customers"})
        self.assertEqual(entities_by_name["dbo.Customers"].properties["schema_state"], CURRENT_DATABASE_SCHEMA_STATE)
        self.assertEqual(entities_by_name["dbo.Customers"].properties["database_engine"], "sqlserver")
        self.assertEqual(entities_by_name["dbo.Customers"].properties["metadata_source"], "sys.tables")
        self.assertEqual(
            entities_by_name["dbo.Customers.TR_Customers_Audit"].properties["trigger_table"], "dbo.Customers"
        )
        self.assertEqual(edges_by_operation["TRIGGER_ON"].to_name, "dbo.Customers")
        self.assertEqual(edges_by_operation["TRIGGER_ON"].properties["trigger_events"], ["INSERT", "UPDATE"])

    def test_emits_resolved_foreign_key_edge(self) -> None:
        facts = scan_sqlserver_metadata(
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
        facts = scan_sqlserver_metadata(
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
        add_facts_to_graph(graph, facts.facts)

        self.assertEqual(facts.errors, [])
        self.assertEqual(len(facts.edges), 2)
        self.assertEqual(len(graph.edges), 2)

    def test_missing_foreign_key_target_stays_unresolved(self) -> None:
        facts = scan_sqlserver_metadata(
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
        facts = scan_sqlserver_metadata(
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
        facts = scan_sqlserver_metadata(
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
        facts = scan_sqlserver_metadata(
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
        facts = scan_sqlserver_metadata(
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
        facts = scan_postgres_metadata(
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
                triggers=(
                    PostgresTriggerRow(
                        schema="public",
                        name="orders_audit_trigger",
                        table_schema="public",
                        table="orders",
                        events=("INSERT", "UPDATE"),
                        is_enabled=True,
                        function_schema="public",
                        function_name="format_customer",
                    ),
                ),
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
        execute_edges = [edge for edge in facts.edges if edge.properties["sql_operation"] == "EXECUTE"]

        self.assertEqual(facts.errors, [])
        self.assertEqual(entities_by_name["public.customers"].entity_type, "sql_table")
        self.assertEqual(entities_by_name["reporting.active_customers"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["reporting.customer_rollup"].entity_type, "sql_view")
        self.assertEqual(entities_by_name["public.refresh_customer"].entity_type, "stored_procedure")
        self.assertEqual(entities_by_name["public.format_customer"].entity_type, "sql_function")
        self.assertEqual(entities_by_name["public.orders.orders_audit_trigger"].entity_type, "sql_trigger")
        self.assertEqual(entities_by_name["public.customers"].properties["database_engine"], "postgres")
        self.assertEqual(entities_by_name["public.customers"].properties["metadata_source"], "pg_class")
        self.assertEqual(
            entities_by_name["reporting.customer_rollup"].properties["postgres_relkind"],
            "materialized_view",
        )
        self.assertEqual(
            entities_by_name["public.orders.orders_audit_trigger"].properties["trigger_function"],
            "public.format_customer",
        )
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].parser, POSTGRES_METADATA_PARSER)
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].properties["metadata_source"], "pg_constraint")
        self.assertEqual(edges_by_operation["FOREIGN_KEY"].properties["database_engine"], "postgres")
        self.assertEqual(edges_by_operation["TRIGGER_ON"].parser, POSTGRES_METADATA_PARSER)
        self.assertEqual(edges_by_operation["TRIGGER_ON"].to_name, "public.orders")
        self.assertEqual({edge.edge_type for edge in execute_edges}, {"CALLS_SQL"})
        self.assertIn(
            ("public.orders.orders_audit_trigger", "public.format_customer"),
            {(edge.from_name, edge.to_name) for edge in execute_edges},
        )


def single_edge(edges: list[RelationshipFact]) -> RelationshipFact:
    if len(edges) != 1:
        raise AssertionError(f"Expected exactly one edge, found {len(edges)}.")
    return edges[0]


class FakeSqlServerConnection:
    def __init__(self) -> None:
        self.closed = False
        self.cursor_instance = FakeSqlServerCursor()

    def cursor(self) -> FakeSqlServerCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class FakeSqlServerCursor:
    def __init__(self) -> None:
        self.timeout: int | None = None
        self.rows: list[SimpleNamespace] = []

    def execute(self, query: str, *_params: str) -> FakeSqlServerCursor:
        if "FROM sys.objects AS o" in query:
            self.rows = [
                SimpleNamespace(schema_name="dbo", object_name="Customers", object_type="U"),
                SimpleNamespace(schema_name="dbo", object_name="Orders", object_type="U"),
                SimpleNamespace(schema_name="dbo", object_name="LoadCustomer", object_type="P"),
            ]
        elif "FROM sys.foreign_keys AS fk" in query:
            self.rows = [
                SimpleNamespace(
                    schema_name="dbo",
                    table_name="Orders",
                    referenced_schema_name="dbo",
                    referenced_table_name="Customers",
                    constraint_name="FK_Orders_Customers",
                )
            ]
        elif "FROM sys.triggers AS trigger_definition" in query:
            self.rows = [
                SimpleNamespace(
                    schema_name="dbo",
                    trigger_name="TR_Orders_Audit",
                    table_schema_name="dbo",
                    table_name="Orders",
                    event_name="INSERT",
                    is_disabled=False,
                )
            ]
        elif "FROM sys.sql_expression_dependencies AS d" in query:
            self.rows = [
                SimpleNamespace(
                    from_schema_name="dbo",
                    from_object_name="LoadCustomer",
                    from_object_type="P",
                    to_schema_name="dbo",
                    to_object_name="Customers",
                    to_object_type="U",
                    dependency_name="OBJECT_OR_COLUMN",
                )
            ]
        else:
            raise AssertionError(f"Unexpected query: {query}")
        return self

    def fetchall(self) -> list[SimpleNamespace]:
        return self.rows


class FakePostgresConnection:
    def __init__(self) -> None:
        self.closed = False
        self.cursor_instance = FakePostgresCursor()

    def cursor(self) -> FakePostgresCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class FakePostgresCursor:
    def __init__(self) -> None:
        self.statement_timeout_ms: int | None = None
        self.rows: list[SimpleNamespace] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
        if query == "SET statement_timeout = %s":
            self.statement_timeout_ms = int(params[0])
            self.rows = []
        elif "FROM pg_catalog.pg_class AS c" in query:
            self.rows = [
                SimpleNamespace(schema_name="public", object_name="customers", object_type="table"),
                SimpleNamespace(schema_name="public", object_name="orders", object_type="table"),
                SimpleNamespace(schema_name="public", object_name="active_customers", object_type="view"),
                SimpleNamespace(schema_name="public", object_name="customer_rollup", object_type="materialized_view"),
            ]
        elif "FROM pg_catalog.pg_proc AS p" in query:
            self.rows = [
                SimpleNamespace(schema_name="public", object_name="refresh_customer", object_type="procedure"),
                SimpleNamespace(schema_name="public", object_name="format_customer", object_type="function"),
            ]
        elif "FROM pg_catalog.pg_constraint AS con" in query:
            self.rows = [
                SimpleNamespace(
                    schema_name="public",
                    table_name="orders",
                    referenced_schema_name="public",
                    referenced_table_name="customers",
                    constraint_name="orders_customer_id_fkey",
                )
            ]
        elif "FROM pg_catalog.pg_trigger AS trigger_definition" in query:
            self.rows = [
                SimpleNamespace(
                    schema_name="public",
                    trigger_name="orders_audit_trigger",
                    table_schema_name="public",
                    table_name="orders",
                    fires_insert=True,
                    fires_update=True,
                    fires_delete=False,
                    fires_truncate=False,
                    is_disabled=False,
                    function_schema_name="public",
                    function_name="format_customer",
                )
            ]
        elif "FROM pg_catalog.pg_rewrite AS rw" in query:
            self.rows = [
                SimpleNamespace(
                    from_schema_name="public",
                    from_object_name="active_customers",
                    from_object_type="view",
                    to_schema_name="public",
                    to_object_name="customers",
                    to_object_type="table",
                    dependency_name="n",
                    dependency_type="object_dependency",
                )
            ]
        else:
            raise AssertionError(f"Unexpected query: {query}")

    def fetchall(self) -> list[SimpleNamespace]:
        return self.rows
