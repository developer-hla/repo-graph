"""Unresolved-reference report example payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import compact_dict, mapping_value, string_value


def edge_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "edge_id": string_value(edge.get("edge_id")),
            "source_name": string_value(edge.get("source_name")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "confidence": string_value(edge.get("confidence")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
        }
    )
