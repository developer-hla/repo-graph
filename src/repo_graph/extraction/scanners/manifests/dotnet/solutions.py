""".NET solution manifest helpers."""

from __future__ import annotations

import re

from repo_graph.extraction.scanners.manifests.dotnet.constants import DOTNET_PROJECT_SUFFIXES
from repo_graph.extraction.scanners.manifests.dotnet.paths import (
    dotnet_manifest_path_stem,
    dotnet_manifest_path_suffix,
)

SLN_PROJECT_RE = re.compile(r'^Project\("[^"]+"\)\s*=\s*"([^"]+)",\s*"([^"]+)"')


def solution_project_reference(line: str) -> dict[str, str | None] | None:
    match = SLN_PROJECT_RE.match(line)
    if not match:
        return None
    raw_path = match.group(2)
    if dotnet_manifest_path_suffix(raw_path) not in DOTNET_PROJECT_SUFFIXES:
        return None
    name = dotnet_manifest_path_stem(raw_path)
    return {
        "name": name,
        "display_name": match.group(1),
        "raw_target": raw_path,
        "normalized_target": name,
    }
