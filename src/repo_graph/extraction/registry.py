"""Scanner registry."""

from __future__ import annotations

from repo_graph.extraction._scanner_impl import (
    CSharpCodeExtractor,
    DotnetBuildConfigExtractor,
    DotnetFrameworkConfigExtractor,
    DotnetPackagesConfigExtractor,
    DotnetProjectExtractor,
    DotnetSolutionExtractor,
    JavaScriptExtractor,
    KubernetesManifestExtractor,
    LegacyDotnetEndpointExtractor,
    PackageJsonExtractor,
    PnpmWorkspaceExtractor,
    PythonCodeExtractor,
    PythonProjectExtractor,
    PythonRequirementsExtractor,
    SqlExtractor,
    SqlReferenceExtractor,
    VbCodeExtractor,
)
from repo_graph.extraction.contracts import FileExtractor


def default_extractors() -> list[FileExtractor]:
    return [
        PackageJsonExtractor(),
        PythonProjectExtractor(),
        PythonRequirementsExtractor(),
        PythonCodeExtractor(),
        DotnetProjectExtractor(),
        DotnetPackagesConfigExtractor(),
        DotnetFrameworkConfigExtractor(),
        DotnetBuildConfigExtractor(),
        DotnetSolutionExtractor(),
        PnpmWorkspaceExtractor(),
        KubernetesManifestExtractor(),
        LegacyDotnetEndpointExtractor(),
        CSharpCodeExtractor(),
        VbCodeExtractor(),
        JavaScriptExtractor(),
        SqlExtractor(),
        SqlReferenceExtractor(),
    ]
