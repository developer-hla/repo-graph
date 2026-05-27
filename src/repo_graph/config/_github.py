"""GitHub organization source config parsing."""

from __future__ import annotations

from typing import Any

from repo_graph.config._defaults import GITHUB_ORG_VISIBILITIES
from repo_graph.config._models import Source
from repo_graph.config._values import bool_value, object_mapping, optional_positive_int, string_tuple


def parse_github_org_source(raw_source: dict[str, Any], name: str, ref: str) -> Source:
    org = raw_source.get("org")
    if not isinstance(org, str) or not org.strip():
        raise ValueError(f"GitHub org source '{name}' must define 'org'.")
    visibility = raw_source.get("visibility", "all")
    if not isinstance(visibility, str) or not visibility.strip():
        raise ValueError(f"GitHub org source '{name}' has invalid 'visibility'.")
    visibility = visibility.strip()
    if visibility not in GITHUB_ORG_VISIBILITIES:
        raise ValueError(f"GitHub org source '{name}' has unsupported 'visibility'.")

    include = object_mapping(raw_source.get("include"), f"GitHub org source '{name}' include")
    exclude = object_mapping(raw_source.get("exclude"), f"GitHub org source '{name}' exclude")
    limit = optional_positive_int(raw_source.get("limit"), f"GitHub org source '{name}' limit")
    return Source(
        name=name,
        source_type="github_org",
        ref=ref,
        org=org.strip(),
        visibility=visibility,
        include_archived=bool_value(include.get("archived"), default=False),
        include_forks=bool_value(include.get("forks"), default=False),
        include_name_patterns=string_tuple(include.get("name_patterns")),
        exclude_name_patterns=string_tuple(exclude.get("name_patterns")),
        limit=limit,
    )
