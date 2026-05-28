"""Compatibility exports for .NET code scanners."""

from __future__ import annotations

from repo_graph.extraction.scanners.code.dotnet.csharp_scanner import CSharpCodeExtractor
from repo_graph.extraction.scanners.code.dotnet.legacy_endpoints import LegacyDotnetEndpointExtractor
from repo_graph.extraction.scanners.code.dotnet.vb_scanner import VbCodeExtractor

__all__ = [
    "CSharpCodeExtractor",
    "LegacyDotnetEndpointExtractor",
    "VbCodeExtractor",
]
