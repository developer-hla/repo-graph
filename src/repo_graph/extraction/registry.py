"""Scanner registry."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from repo_graph.extraction.contracts import FileExtractor, ScannerSpec, scanner_spec
from repo_graph.extraction.scanners.code.dotnet import (
    CSharpCodeExtractor,
    LegacyDotnetEndpointExtractor,
    VbCodeExtractor,
)
from repo_graph.extraction.scanners.code.javascript import JavaScriptExtractor
from repo_graph.extraction.scanners.code.python import PythonCodeExtractor
from repo_graph.extraction.scanners.deployment import KubernetesManifestExtractor
from repo_graph.extraction.scanners.manifests import (
    DotnetBuildConfigExtractor,
    DotnetFrameworkConfigExtractor,
    DotnetPackagesConfigExtractor,
    DotnetProjectExtractor,
    DotnetSolutionExtractor,
    PackageJsonExtractor,
    PnpmWorkspaceExtractor,
    PythonProjectExtractor,
    PythonRequirementsExtractor,
)
from repo_graph.extraction.scanners.sql import (
    SqlExtractor,
    SqlReferenceExtractor,
)

VALID_SCANNER_FAMILIES = frozenset({"code", "deployment", "manifest", "sql"})


@dataclass(frozen=True)
class ScannerRegistration:
    order: int
    spec: ScannerSpec
    factory: Callable[[], FileExtractor]
    enabled_by_default: bool = True

    def create_extractor(self) -> FileExtractor:
        return self.factory()

    @property
    def factory_module(self) -> str:
        return self.factory.__module__

    @property
    def factory_name(self) -> str:
        return self.factory.__name__


DEFAULT_SCANNER_REGISTRATIONS = (
    ScannerRegistration(1, PackageJsonExtractor.spec, PackageJsonExtractor),
    ScannerRegistration(2, PythonProjectExtractor.spec, PythonProjectExtractor),
    ScannerRegistration(3, PythonRequirementsExtractor.spec, PythonRequirementsExtractor),
    ScannerRegistration(4, PythonCodeExtractor.spec, PythonCodeExtractor),
    ScannerRegistration(5, DotnetProjectExtractor.spec, DotnetProjectExtractor),
    ScannerRegistration(6, DotnetPackagesConfigExtractor.spec, DotnetPackagesConfigExtractor),
    ScannerRegistration(7, DotnetFrameworkConfigExtractor.spec, DotnetFrameworkConfigExtractor),
    ScannerRegistration(8, DotnetBuildConfigExtractor.spec, DotnetBuildConfigExtractor),
    ScannerRegistration(9, DotnetSolutionExtractor.spec, DotnetSolutionExtractor),
    ScannerRegistration(10, PnpmWorkspaceExtractor.spec, PnpmWorkspaceExtractor),
    ScannerRegistration(11, KubernetesManifestExtractor.spec, KubernetesManifestExtractor),
    ScannerRegistration(12, LegacyDotnetEndpointExtractor.spec, LegacyDotnetEndpointExtractor),
    ScannerRegistration(13, CSharpCodeExtractor.spec, CSharpCodeExtractor),
    ScannerRegistration(14, VbCodeExtractor.spec, VbCodeExtractor),
    ScannerRegistration(15, JavaScriptExtractor.spec, JavaScriptExtractor),
    ScannerRegistration(16, SqlExtractor.spec, SqlExtractor),
    ScannerRegistration(17, SqlReferenceExtractor.spec, SqlReferenceExtractor),
)


def default_extractors() -> list[FileExtractor]:
    return [registration.create_extractor() for registration in default_scanner_registrations()]


def default_scanner_specs() -> list[ScannerSpec]:
    return [registration.spec for registration in default_scanner_registrations()]


def default_scanner_registrations() -> list[ScannerRegistration]:
    return sorted(
        (registration for registration in DEFAULT_SCANNER_REGISTRATIONS if registration.enabled_by_default),
        key=lambda registration: registration.order,
    )


def validate_scanner_registrations(
    registrations: Sequence[ScannerRegistration] | None = None,
) -> list[str]:
    active_registrations = list(registrations if registrations is not None else default_scanner_registrations())
    issues: list[str] = []
    seen_orders: set[int] = set()
    seen_names: set[str] = set()

    for registration in active_registrations:
        spec = registration.spec
        if registration.order < 1:
            issues.append(f"{spec.name}: order must be positive")
        elif registration.order in seen_orders:
            issues.append(f"{spec.name}: duplicate registration order {registration.order}")
        seen_orders.add(registration.order)

        if not spec.name.strip():
            issues.append(f"{registration.factory_name}: scanner name is required")
        elif spec.name in seen_names:
            issues.append(f"{spec.name}: duplicate scanner name")
        seen_names.add(spec.name)

        if spec.family not in VALID_SCANNER_FAMILIES:
            issues.append(f"{spec.name}: unknown scanner family {spec.family!r}")
        if not spec.target_patterns:
            issues.append(f"{spec.name}: target_patterns must not be empty")
        if not all(pattern.strip() for pattern in spec.target_patterns):
            issues.append(f"{spec.name}: target_patterns must not contain blank values")
        if not spec.parser_ids:
            issues.append(f"{spec.name}: parser_ids must not be empty")
        if not all(parser_id.strip() for parser_id in spec.parser_ids):
            issues.append(f"{spec.name}: parser_ids must not contain blank values")
        if len(spec.parser_ids) != len(set(spec.parser_ids)):
            issues.append(f"{spec.name}: parser_ids must be unique within the scanner")
        if not spec.description.strip():
            issues.append(f"{spec.name}: description is required")

        try:
            extractor = registration.create_extractor()
            extractor_spec = scanner_spec(extractor)
        except Exception as exc:
            issues.append(f"{spec.name}: factory failed: {exc}")
            continue
        if extractor_spec != spec:
            issues.append(f"{spec.name}: factory returned scanner spec {extractor_spec!r}")

    expected_orders = list(range(1, len(active_registrations) + 1))
    actual_orders = sorted(registration.order for registration in active_registrations)
    if actual_orders != expected_orders:
        issues.append(f"scanner orders must be contiguous from 1: {actual_orders}")

    return issues


__all__ = [
    "VALID_SCANNER_FAMILIES",
    "ScannerRegistration",
    "default_extractors",
    "default_scanner_registrations",
    "default_scanner_specs",
    "validate_scanner_registrations",
]
