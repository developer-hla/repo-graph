"""Interaction evidence vocabulary."""

from __future__ import annotations

INTERACTION_EVIDENCE_KEYS = (
    "target_boundary",
    "dependency_scope",
    "interaction_kind",
)
INTERACTION_TARGET_BOUNDARIES = (
    "application",
    "cache",
    "database",
    "messaging",
    "storage",
)
INTERACTION_DEPENDENCY_SCOPES = (
    "configuration",
    "deployment",
    "runtime",
    "schema",
)
INTERACTION_KINDS = (
    "http_call",
    "ingress_route",
    "cache_read",
    "cache_write",
    "message_consume",
    "message_publish",
    "service_call",
    "service_configuration",
    "sql_reference",
    "sql_schema_reference",
    "sql_trigger",
    "storage_read",
    "storage_write",
)
