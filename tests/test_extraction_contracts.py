from __future__ import annotations

import unittest
from pathlib import Path
from typing import get_type_hints

from repo_graph.config import load_config
from repo_graph.extraction.contracts import FileScanContext, ProjectInfo
from repo_graph.extraction.fact_validation import validate_fact_batch, validate_relationship_facts
from repo_graph.extraction.facts import EntityFact, EntityReference, Evidence, RelationshipFact
from repo_graph.extraction.registry import default_extractors
from repo_graph.extraction.source_scanner import scan_source
from repo_graph.sources import resolve_sources


class ExtractionContractTests(unittest.TestCase):
    def test_source_context_uses_fact_entities(self) -> None:
        self.assertIs(get_type_hints(ProjectInfo)["entity"], EntityFact)
        self.assertIs(get_type_hints(FileScanContext)["repo_entity"], EntityFact)
        self.assertIs(get_type_hints(FileScanContext)["file_entity"], EntityFact)

    def test_scanner_modules_do_not_import_graph_model(self) -> None:
        scanner_root = Path(__file__).resolve().parents[1] / "src" / "repo_graph" / "extraction" / "scanners"
        offenders = [
            path.relative_to(scanner_root).as_posix()
            for path in scanner_root.glob("*.py")
            if "repo_graph.graph" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_source_discovery_modules_do_not_import_graph_model(self) -> None:
        extraction_root = Path(__file__).resolve().parents[1] / "src" / "repo_graph" / "extraction"
        source_modules = [
            extraction_root / "source_scanner.py",
            extraction_root / "project_discovery.py",
            extraction_root / "source_facts.py",
        ]
        offenders = [
            path.relative_to(extraction_root).as_posix()
            for path in source_modules
            if "repo_graph.graph" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_database_metadata_modules_do_not_import_graph_model(self) -> None:
        database_root = Path(__file__).resolve().parents[1] / "src" / "repo_graph" / "database"
        offenders = [
            path.relative_to(database_root).as_posix()
            for path in database_root.glob("*.py")
            if "repo_graph.graph" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_interaction_fact_validation_catches_missing_evidence(self) -> None:
        relationship = RelationshipFact(
            from_ref=EntityReference(entity_type="function", name="handler", source_name="example"),
            to_ref=EntityReference(entity_type="service", name="inventory-service"),
            edge_type="CALLS_SERVICE",
            evidence=Evidence(source_name="example", parser="example_http", file_path="app.py", line_number=3),
            properties={},
        )

        issues = validate_relationship_facts([relationship])

        self.assertEqual(
            [issue.message for issue in issues],
            [
                "missing interaction property 'target_boundary'",
                "missing interaction property 'dependency_scope'",
                "missing interaction property 'interaction_kind'",
            ],
        )
        self.assertTrue(all(issue.edge_type == "CALLS_SERVICE" for issue in issues))
        self.assertTrue(all(issue.parser == "example_http" for issue in issues))

    def test_interaction_fact_validation_catches_invalid_evidence_values(self) -> None:
        relationship = RelationshipFact(
            from_ref=EntityReference(entity_type="function", name="handler", source_name="example"),
            to_ref=EntityReference(entity_type="service", name="inventory-service"),
            edge_type="CALLS_SERVICE",
            evidence=Evidence(source_name="example", parser="example_http", file_path="app.py", line_number=3),
            properties={
                "target_boundary": "library",
                "dependency_scope": "compile",
                "interaction_kind": "service_lookup",
            },
        )

        issues = validate_relationship_facts([relationship])

        self.assertEqual(
            [issue.message for issue in issues],
            [
                "invalid target_boundary 'library'",
                "invalid dependency_scope 'compile'",
                "invalid interaction_kind 'service_lookup'",
            ],
        )

    def test_example_source_scans_emit_valid_interaction_evidence(self) -> None:
        config = load_config(Path("config/local-example.yaml"))
        extractors = default_extractors()

        issues = []
        for source in resolve_sources(config):
            result = scan_source(config, source, max_file_bytes=1_000_000, extractors=extractors)
            issues.extend(validate_fact_batch(result.facts))

        self.assertEqual(issues, [])
