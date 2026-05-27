"""Shared service interaction fact helpers."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import unresolved_relationship_fact
from repo_graph.extraction.facts import EntityReference, RelationshipFact
from repo_graph.extraction.scanners.interactions.http import http_target
from repo_graph.extraction.scanners.interactions.naming import service_name_from_identifier, service_name_from_url


def service_configuration_fact(
    from_ref: EntityReference,
    raw_target: str,
    context: FileScanContext,
    parser: str,
    service_name: str | None = None,
    fallback_identifier: object | None = None,
    line_number: int | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    resolved_service_name = service_name or service_name_from_url(raw_target)
    if resolved_service_name == "external-service":
        resolved_service_name = service_name_from_identifier(fallback_identifier)

    properties = http_target(raw_target, "GET")
    if extra_properties:
        properties.update({key: value for key, value in extra_properties.items() if value is not None})
    properties["dependency_scope"] = "configuration"
    properties["interaction_kind"] = "service_configuration"
    properties["service_name"] = resolved_service_name

    return unresolved_relationship_fact(
        from_ref,
        resolved_service_name,
        "CONFIGURES_SERVICE",
        context,
        parser,
        to_type="service",
        line_number=line_number,
        properties=properties,
    )
