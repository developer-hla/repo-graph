from __future__ import annotations

import unittest

from repo_graph.extraction.facts import EntityFact, EntityReference, Evidence, FactBatch, RelationshipFact, ScanIssue
from repo_graph.graph import Edge, Entity, Graph, add_facts_to_graph


class GraphResolutionTests(unittest.TestCase):
    def test_adds_typed_facts_to_graph(self) -> None:
        graph = Graph(scope_name="test", sources=[])
        file_fact = EntityFact(
            entity_type="file",
            name="requirements.txt",
            source_name="worker",
            file_path="requirements.txt",
            aliases=frozenset({"requirements.txt"}),
            properties={"extension": ".txt"},
        )
        add_facts_to_graph(
            graph,
            FactBatch(
                entities=[file_fact],
                relationships=[
                    RelationshipFact(
                        from_ref=file_fact.reference,
                        to_ref=EntityReference(entity_type="package", name="requests"),
                        edge_type="DEPENDS_ON_PACKAGE",
                        evidence=Evidence(
                            source_name="worker",
                            parser="requirements",
                            file_path="requirements.txt",
                            line_number=1,
                        ),
                        properties={"ecosystem": "python"},
                    )
                ],
                issues=[
                    ScanIssue(
                        "example warning",
                        Evidence(source_name="worker", parser="test", file_path="requirements.txt"),
                    )
                ],
            ),
        )

        entity = next(iter(graph.entities.values()))
        edge = next(iter(graph.edges.values()))

        self.assertEqual(entity.entity_type, "file")
        self.assertEqual(edge.from_entity_id, entity.entity_id)
        self.assertEqual(edge.to_name, "requests")
        self.assertEqual(edge.to_type, "package")
        self.assertFalse(edge.resolved)
        self.assertEqual(edge.parser, "requirements")
        self.assertEqual(edge.line_number, 1)
        self.assertEqual(edge.properties["ecosystem"], "python")
        self.assertEqual(graph.errors, ["example warning"])

    def test_ambiguous_cross_source_resolution_stays_unresolved(self) -> None:
        graph = Graph(scope_name="test", sources=[])
        file_entity = graph.add_entity(Entity(entity_type="file", name="api.ts", source_name="api", file_path="api.ts"))
        graph.add_entity(Entity(entity_type="stored_procedure", name="dbo.load", source_name="database-a"))
        graph.add_entity(Entity(entity_type="stored_procedure", name="dbo.load", source_name="database-b"))
        graph.add_edge(
            Edge(
                from_entity_id=file_entity.entity_id,
                from_name=file_entity.name,
                from_type=file_entity.entity_type,
                to_name="dbo.load",
                to_type="stored_procedure",
                edge_type="CALLS_SQL",
                source_name="api",
            )
        )

        graph.resolve_edges()
        edge = next(iter(graph.edges.values()))

        self.assertFalse(edge.resolved)
        self.assertEqual(edge.properties["resolution_status"], "ambiguous")
        self.assertEqual(len(edge.properties["resolution_candidates"]), 2)

    def test_same_source_candidate_is_preferred(self) -> None:
        graph = Graph(scope_name="test", sources=[])
        file_entity = graph.add_entity(
            Entity(entity_type="file", name="schema.sql", source_name="database-a", file_path="schema.sql")
        )
        same_source = graph.add_entity(
            Entity(entity_type="stored_procedure", name="dbo.load", source_name="database-a")
        )
        graph.add_entity(Entity(entity_type="stored_procedure", name="dbo.load", source_name="database-b"))
        graph.add_edge(
            Edge(
                from_entity_id=file_entity.entity_id,
                from_name=file_entity.name,
                from_type=file_entity.entity_type,
                to_name="dbo.load",
                to_type="stored_procedure",
                edge_type="CALLS_SQL",
                source_name="database-a",
            )
        )

        graph.resolve_edges()
        edge = next(iter(graph.edges.values()))

        self.assertTrue(edge.resolved)
        self.assertEqual(edge.to_entity_id, same_source.entity_id)


if __name__ == "__main__":
    unittest.main()
