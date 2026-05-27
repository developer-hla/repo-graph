"""Shared HTTP interaction helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.interactions.naming import (
    ENV_NAME_RE,
    ENV_URL_RE,
    extract_endpoint,
    normalize_route_path,
    service_name_from_env,
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
FETCH_RE = re.compile(r"\bfetch\s*\(\s*([\"'`])([^\"'`]+)\1(?P<args>[^)]*)", re.IGNORECASE)
AXIOS_RE = re.compile(
    r"\baxios\.(get|post|put|patch|delete|head|options)\s*\(\s*([\"'`])([^\"'`]+)\2",
    re.IGNORECASE,
)


def http_call_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for match in FETCH_RE.finditer(line):
        method = fetch_method(match.group("args"))
        facts.extend(
            http_facts_for_target(
                context,
                method,
                match.group(2),
                line_number,
                "javascript_http",
                client="fetch",
                from_entity=from_entity,
            )
        )
    for match in AXIOS_RE.finditer(line):
        facts.extend(
            http_facts_for_target(
                context,
                match.group(1).upper(),
                match.group(3),
                line_number,
                "javascript_http",
                client="axios",
                from_entity=from_entity,
            )
        )
    return facts


def http_facts_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str,
    line_number: int,
    parser: str,
    client: str | None = None,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> list[RelationshipFact]:
    source_ref = entity_reference(from_entity or context.file_entity)
    target = http_target(raw_target, method)
    if client:
        target["client"] = client
    if extra_properties:
        target.update(extra_properties)
    if target.get("service_name"):
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
    return [
        unresolved_relationship_fact(
            source_ref,
            target["route_name"],
            "CALLS_HTTP",
            context,
            parser,
            to_type="api_route",
            line_number=line_number,
            properties=target,
        )
    ]


def http_target(raw_target: str, method: str) -> dict[str, Any]:
    env_match = ENV_URL_RE.search(raw_target) or ENV_NAME_RE.search(raw_target)
    endpoint = extract_endpoint(raw_target)
    normalized_path = normalize_route_path(endpoint or raw_target)
    parsed = urlparse(raw_target)
    host = parsed.netloc or None
    service_name = service_name_from_env(env_match.group(1)) if env_match else None
    return interaction_properties(
        "application",
        "runtime",
        "http_call",
        protocol=parsed.scheme if parsed.scheme in {"http", "https"} else "http",
        raw_target=raw_target,
        normalized_target=f"{method} {normalized_path}",
        route_name=f"{method} {normalized_path}",
        http_method=method,
        target_host=host,
        target_path=normalized_path,
        target_env_var=env_match.group(1) if env_match else None,
        service_name=service_name,
    )


def fetch_method(args: str) -> str:
    match = re.search(r"method\s*:\s*[\"'](get|post|put|patch|delete|head|options)[\"']", args, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "GET"
