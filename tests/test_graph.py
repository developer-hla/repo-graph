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

    def test_message_resources_are_materialized_as_shared_external_nodes(self) -> None:
        graph = Graph(scope_name="test", sources=[])
        publisher = graph.add_entity(Entity(entity_type="file", name="producer.py", source_name="publisher"))
        consumer = graph.add_entity(Entity(entity_type="file", name="consumer.ts", source_name="consumer"))
        graph.add_edge(
            Edge(
                from_entity_id=publisher.entity_id,
                from_name=publisher.name,
                from_type=publisher.entity_type,
                to_name="orders.created",
                to_type="message_topic",
                edge_type="PUBLISHES_MESSAGE",
                source_name="publisher",
            )
        )
        graph.add_edge(
            Edge(
                from_entity_id=consumer.entity_id,
                from_name=consumer.name,
                from_type=consumer.entity_type,
                to_name="orders.created",
                to_type="message_topic",
                edge_type="CONSUMES_MESSAGE",
                source_name="consumer",
            )
        )

        graph.resolve_edges()
        message_entities = [entity for entity in graph.entities.values() if entity.entity_type == "message_topic"]
        message_edges = [edge for edge in graph.edges.values() if edge.to_type == "message_topic"]

        self.assertEqual(len(message_entities), 1)
        self.assertEqual(message_entities[0].source_name, "external-resources")
        self.assertTrue(all(edge.resolved for edge in message_edges))
        self.assertEqual({edge.to_entity_id for edge in message_edges}, {message_entities[0].entity_id})


if __name__ == "__main__":
    unittest.main()
