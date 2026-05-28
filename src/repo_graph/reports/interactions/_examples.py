"""Interaction report example payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from repo_graph.reports._common import compact_dict, mapping_value, string_value


def interaction_example(edge: Mapping[str, Any]) -> dict[str, Any]:
    properties = mapping_value(edge.get("properties"))
    return compact_dict(
        {
            "edge_id": string_value(edge.get("edge_id")),
            "from_name": string_value(edge.get("from_name")),
            "from_type": string_value(edge.get("from_type")),
            "to_name": string_value(edge.get("to_name")),
            "to_type": string_value(edge.get("to_type")),
            "target_source": string_value(edge.get("target_source")),
            "resolved": edge.get("resolved"),
            "file_path": string_value(edge.get("file_path")),
            "line_number": edge.get("line_number"),
            "parser": string_value(edge.get("parser")),
            "confidence": string_value(edge.get("confidence")),
            "client": string_value(properties.get("client")),
            "protocol": string_value(properties.get("protocol")),
            "http_method": string_value(properties.get("http_method")),
            "target_path": string_value(properties.get("target_path")),
            "raw_target": string_value(properties.get("raw_target")),
            "normalized_target": string_value(properties.get("normalized_target")),
            "config_key": string_value(properties.get("config_key")),
            "sql_operation": string_value(properties.get("sql_operation")),
            "database_object_type": string_value(properties.get("database_object_type")),
            "schema_state": string_value(properties.get("schema_state")),
            "sql_source_kind": string_value(properties.get("sql_source_kind")),
        }
    )
