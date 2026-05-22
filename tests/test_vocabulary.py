from __future__ import annotations

import unittest
from pathlib import Path

from repo_graph.config import load_config
from repo_graph.extraction import build_graph
from repo_graph.vocabulary import (
    CLASSIFICATION_ACTIONS,
    CLASSIFICATION_COVERAGE_WARNING_RULES,
    CLASSIFICATION_ORDER,
    EDGE_TARGET_TYPES,
    EDGE_TYPE_COVERAGE_WARNING_RULES,
    EDGE_TYPES,
    ENTITY_TYPES,
    IMPACT_PROFILES,
    INTERACTION_DEPENDENCY_SCOPES,
    INTERACTION_EDGE_TYPES,
    INTERACTION_EVIDENCE_KEYS,
    INTERACTION_KINDS,
    INTERACTION_TARGET_BOUNDARIES,
    PARSER_IDS,
    UNRESOLVED_CLASSIFICATIONS,
)


class VocabularyTests(unittest.TestCase):
    def test_example_graph_uses_known_vocabulary(self) -> None:
        graph = build_graph(load_config(Path("config/local-example.yaml")), strict=True).to_dict()
        parsers = {edge["parser"] for edge in graph["edges"]}
        from_types = {edge["from_type"] for edge in graph["edges"] if edge.get("from_type")}
        to_types = {edge["to_type"] for edge in graph["edges"] if edge.get("to_type")}

        self.assertEqual(set(graph["entity_counts"]) - set(ENTITY_TYPES), set())
        self.assertEqual(set(graph["edge_counts"]) - set(EDGE_TYPES), set())
        self.assertEqual(parsers - set(PARSER_IDS), set())
        self.assertEqual(from_types - set(ENTITY_TYPES), set())
        self.assertEqual(to_types - set(EDGE_TARGET_TYPES), set())

    def test_impact_profiles_are_regular(self) -> None:
        self.assertIsNone(IMPACT_PROFILES["all"])
        self.assertIn("CALLS_SQL", IMPACT_PROFILES["impact"])
        self.assertIn("CONTAINS_FILE", IMPACT_PROFILES["structural"])
        self.assertNotIn("CONTAINS_FILE", IMPACT_PROFILES["impact"])
        for edge_types in IMPACT_PROFILES.values():
            if edge_types is not None:
                self.assertEqual(set(edge_types) - set(EDGE_TYPES), set())

    def test_interaction_edge_contract_is_regular(self) -> None:
        graph = build_graph(load_config(Path("config/local-example.yaml")), strict=True).to_dict()

        self.assertEqual(INTERACTION_EDGE_TYPES - set(EDGE_TYPES), set())
        interaction_edges = [edge for edge in graph["edges"] if edge["edge_type"] in INTERACTION_EDGE_TYPES]
        self.assertGreater(len(interaction_edges), 0)
        for edge in interaction_edges:
            properties = edge["properties"]
            for key in INTERACTION_EVIDENCE_KEYS:
                self.assertIn(key, properties, edge)
            self.assertIn(properties["target_boundary"], INTERACTION_TARGET_BOUNDARIES)
            self.assertIn(properties["dependency_scope"], INTERACTION_DEPENDENCY_SCOPES)
            self.assertIn(properties["interaction_kind"], INTERACTION_KINDS)

    def test_unresolved_classification_maps_match_definitions(self) -> None:
        names = [classification.name for classification in UNRESOLVED_CLASSIFICATIONS]

        self.assertEqual(names, ["likely_missing_source", "likely_parser_gap", "ambiguous_target", "needs_review"])
        self.assertEqual(set(CLASSIFICATION_ORDER), set(names))
        self.assertEqual(set(CLASSIFICATION_ACTIONS), set(names))

    def test_warning_rules_reference_known_vocabulary(self) -> None:
        classifications = {classification.name for classification in UNRESOLVED_CLASSIFICATIONS}

        self.assertEqual(
            {rule.target for rule in EDGE_TYPE_COVERAGE_WARNING_RULES} - set(EDGE_TYPES),
            set(),
        )
        self.assertEqual(
            {rule.target for rule in CLASSIFICATION_COVERAGE_WARNING_RULES} - classifications,
            set(),
        )
