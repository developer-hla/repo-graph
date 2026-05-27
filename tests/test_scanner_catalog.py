"""Scanner catalog metadata tests."""

from __future__ import annotations

import unittest

from repo_graph.extraction.contracts import ScannerSpec, scanner_spec
from repo_graph.extraction.registry import (
    ScannerRegistration,
    default_extractors,
    default_scanner_registrations,
    default_scanner_specs,
    validate_scanner_registrations,
)


class ScannerCatalogTests(unittest.TestCase):
    def test_default_extractors_expose_scanner_specs(self) -> None:
        for extractor in default_extractors():
            spec = scanner_spec(extractor)
            with self.subTest(scanner=spec.name):
                self.assertIsInstance(spec, ScannerSpec)
                self.assertTrue(spec.name.strip())
                self.assertTrue(spec.family.strip())
                self.assertTrue(spec.target_patterns)
                self.assertTrue(spec.parser_ids)
                self.assertTrue(spec.description.strip())
                self.assertEqual(extractor.name, spec.name)
                self.assertEqual(extractor.target_patterns, spec.target_patterns)
                self.assertEqual(extractor.parser_ids, spec.parser_ids)
                self.assertTrue(all(pattern.strip() for pattern in spec.target_patterns))
                self.assertTrue(all(parser_id.strip() for parser_id in spec.parser_ids))
                self.assertEqual(len(spec.parser_ids), len(set(spec.parser_ids)))

    def test_default_scanner_specs_keep_registration_order(self) -> None:
        registration_specs = [registration.spec for registration in default_scanner_registrations()]
        self.assertEqual(default_scanner_specs(), registration_specs)
        self.assertEqual(default_scanner_specs(), [scanner_spec(extractor) for extractor in default_extractors()])

    def test_default_scanner_names_are_unique(self) -> None:
        names = [scanner_spec(extractor).name for extractor in default_extractors()]
        self.assertEqual(len(names), len(set(names)))

    def test_default_scanner_registrations_are_valid(self) -> None:
        self.assertEqual(validate_scanner_registrations(), [])

    def test_default_extractors_are_built_from_registrations(self) -> None:
        registrations = default_scanner_registrations()
        extractors = default_extractors()
        self.assertEqual(
            [registration.order for registration in registrations],
            list(range(1, len(registrations) + 1)),
        )
        self.assertEqual(
            [registration.spec for registration in registrations],
            [scanner_spec(extractor) for extractor in extractors],
        )

    def test_registration_validation_catches_factory_spec_mismatch(self) -> None:
        registrations = default_scanner_registrations()
        mismatched = ScannerRegistration(
            order=1,
            spec=registrations[1].spec,
            factory=registrations[0].factory,
        )
        issues = validate_scanner_registrations([mismatched])

        self.assertTrue(any("factory returned scanner spec" in issue for issue in issues))
