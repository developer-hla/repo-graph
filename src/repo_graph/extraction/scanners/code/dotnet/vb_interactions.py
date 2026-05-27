"""Visual Basic application and database interaction helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.interactions.http import http_facts_for_target, http_target
from repo_graph.extraction.scanners.interactions.naming import service_name_from_identifier, service_name_from_url
from repo_graph.extraction.scanners.sql.properties import source_context_properties, sql_interaction_properties
from repo_graph.extraction.scanners.sql.references import stored_procedure_target

VB_CONFIG_SETTING_RE = re.compile(r"ConfigurationManager\.AppSettings\s*\(\s*\"([^\"]+)\"\s*\)", re.IGNORECASE)
VB_COMMAND_TEXT_RE = re.compile(r"\.CommandText\s*=\s*\"([^\"]+)\"", re.IGNORECASE)
VB_SQL_COMMAND_RE = re.compile(r"New\s+SqlCommand\s*\(\s*\"([^\"]+)\"", re.IGNORECASE)
VB_HTTP_LITERAL_RE = re.compile(
    r"(?:WebRequest\.Create|WebClient\(\)\.(?:DownloadString|OpenRead|UploadString)|\.DownloadString|\.OpenRead)"
    r"\s*\(\s*\"([^\"]+)\"",
    re.IGNORECASE,
)


def vb_service_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    for match in VB_HTTP_LITERAL_RE.finditer(line):
        facts.extend(
            legacy_http_facts_for_target(
                context,
                match.group(1),
                line_number,
                "vb_http",
                client=legacy_http_client(match.group(0)),
                from_entity=from_entity,
                extra_properties=extra_properties,
            )
        )
    for match in VB_CONFIG_SETTING_RE.finditer(line):
        key = match.group(1)
        service_name = service_name_from_identifier(key)
        properties = interaction_properties(
            "application",
            "runtime",
            "service_call",
            raw_target=key,
            normalized_target=service_name,
            config_key=key,
            service_name=service_name,
        )
        properties.update(extra_properties)
        facts.append(
            unresolved_relationship_fact(
                source_ref,
                service_name,
                "CALLS_SERVICE",
                context,
                "vb_config_service",
                to_type="service",
                line_number=line_number,
                properties=properties,
            )
        )
    return facts


def legacy_http_facts_for_target(
    context: FileScanContext,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, "GET")
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        if extra_properties:
            target.update(extra_properties)
        return [
            unresolved_relationship_fact(
                source_ref,
                target["service_name"],
                "CALLS_SERVICE",
                context,
                parser,
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_facts_for_target(
        context,
        "GET",
        raw_target,
        line_number,
        parser,
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
    )


def legacy_http_client(evidence: str) -> str:
    if "WebRequest" in evidence:
        return "WebRequest"
    if "WebClient" in evidence:
        return "WebClient"
    return "legacy_http_client"


def vb_sql_command_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    targets = [match.group(1) for match in VB_COMMAND_TEXT_RE.finditer(line)]
    targets.extend(match.group(1) for match in VB_SQL_COMMAND_RE.finditer(line))
    facts: list[RelationshipFact] = []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    for target in targets:
        normalized = stored_procedure_target(target)
        if not normalized:
            continue
        facts.append(
            unresolved_relationship_fact(
                source_ref,
                normalized,
                "CALLS_SQL",
                context,
                "vb_sql_command",
                to_type="stored_procedure",
                line_number=line_number,
                properties=sql_interaction_properties(
                    target,
                    "EXECUTE",
                    "stored_procedure",
                    extra_properties=extra_properties,
                ),
            )
        )
    return facts


__all__ = [
    "legacy_http_client",
    "legacy_http_facts_for_target",
    "vb_service_call_facts",
    "vb_sql_command_facts",
]
