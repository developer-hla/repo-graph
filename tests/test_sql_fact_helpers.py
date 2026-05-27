from __future__ import annotations

import unittest
from pathlib import Path

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact
from repo_graph.extraction.scanners.sql.facts import (
    sql_call_fact,
    sql_object_read_fact,
    sql_object_write_fact,
    sql_schema_reference_fact,
)
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
    file = EntityFact(entity_type="file", name="src/app.py", source_name=source.name, file_path="src/app.py")
    return FileScanContext(
        source=source,
        repo_entity=repo,
        file_entity=file,
        file_path=Path("api-service/src/app.py"),
        rel_path="src/app.py",
    )


class SqlFactHelperTests(unittest.TestCase):
    def test_sql_call_fact_uses_runtime_database_evidence_and_source_context(self) -> None:
        context = example_context()
        function = EntityFact(
            entity_type="function",
            name="orders.handler",
            source_name=context.source.name,
            file_path=context.rel_path,
        )

        fact = sql_call_fact(context, "dbo.load_orders", 12, from_entity=function)

        self.assertEqual(fact.edge_type, "CALLS_SQL")
        self.assertEqual(fact.from_name, "orders.handler")
        self.assertEqual(fact.to_type, "stored_procedure")
        self.assertEqual(fact.to_name, "dbo.load_orders")
        self.assertEqual(fact.properties["target_boundary"], "database")
        self.assertEqual(fact.properties["dependency_scope"], "runtime")
        self.assertEqual(fact.properties["interaction_kind"], "sql_reference")
        self.assertEqual(fact.properties["protocol"], "sql")
        self.assertEqual(fact.properties["sql_operation"], "EXECUTE")
        self.assertEqual(fact.properties["database_object_type"], "stored_procedure")
        self.assertEqual(fact.properties["source_context_type"], "function")
        self.assertEqual(fact.properties["source_context_name"], "orders.handler")

    def test_sql_object_reference_fact_builders_use_expected_edge_types(self) -> None:
        context = example_context()
        table = "dbo.orders"

        read_fact = sql_object_read_fact(context, table, "FROM", 3)
        write_fact = sql_object_write_fact(context, table, "UPDATE", 4)
        schema_fact = sql_schema_reference_fact(context, table, 5)

        self.assertEqual(read_fact.edge_type, "READS_SQL_OBJECT")
        self.assertEqual(write_fact.edge_type, "WRITES_SQL_OBJECT")
        self.assertEqual(schema_fact.edge_type, "REFERENCES_SQL_OBJECT")
        self.assertEqual(schema_fact.properties["dependency_scope"], "schema")
        self.assertEqual(schema_fact.properties["interaction_kind"], "sql_schema_reference")
        self.assertTrue(all(fact.properties["target_boundary"] == "database" for fact in (read_fact, write_fact)))


if __name__ == "__main__":
    unittest.main()
