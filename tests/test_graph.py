from __future__ import annotations

import unittest

from repo_graph.graph import Edge, Entity, Graph


class GraphResolutionTests(unittest.TestCase):
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
