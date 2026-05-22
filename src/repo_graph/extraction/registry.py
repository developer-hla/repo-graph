"""Scanner registry."""

from __future__ import annotations

from repo_graph.extraction.contracts import FileExtractor
from repo_graph.extraction.scanners.deployment import KubernetesManifestExtractor
from repo_graph.extraction.scanners.dotnet import (
    CSharpCodeExtractor,
    LegacyDotnetEndpointExtractor,
    VbCodeExtractor,
)
from repo_graph.extraction.scanners.javascript import JavaScriptExtractor
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
from repo_graph.extraction.scanners.python import PythonCodeExtractor
from repo_graph.extraction.scanners.sql import (
    SqlExtractor,
    SqlReferenceExtractor,
)


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
