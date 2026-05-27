"""Shared route declaration helpers."""

from __future__ import annotations

import re

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.interactions.naming import normalize_route_path

ROUTE_RE = re.compile(
    r"\b(?:app|router|server|fastify)\s*\.\s*(get|post|put|patch|delete|options|head)\s*\(\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
ROUTE_HANDLER_RE = re.compile(
    r"\b(?:app|router|server|fastify)\s*\.\s*(?:get|post|put|patch|delete|options|head)\s*\("
    r"\s*[\"'][^\"']+[\"']\s*,\s*(?P<handler>[A-Za-z_$][\w$]*)",
    re.IGNORECASE,
)
NEST_ROUTE_RE = re.compile(
    r"@(Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*(?:[\"']([^\"']+)[\"'])?",
    re.IGNORECASE,
)


def route_facts(
    context: FileScanContext,
    line: str,
    line_number: int,
    handler_by_name: dict[str, EntityFact] | None = None,
) -> FactBatch:
    facts = FactBatch()
    for match in ROUTE_RE.finditer(line):
        handler = javascript_route_handler(line, handler_by_name)
        facts.extend(
            add_route_facts(
                context,
                match.group(1).upper(),
                match.group(2),
                line_number,
                "javascript_route",
                handler=handler,
            )
        )
    for match in NEST_ROUTE_RE.finditer(line):
        facts.extend(
            add_route_facts(context, match.group(1).upper(), match.group(2) or "/", line_number, "nestjs_route")
        )
    return facts


def add_route_facts(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    parser: str,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    route = route_entity_fact(context, method, path, line_number, parser, operation_name=None)
    facts.entities.append(route)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            route.reference,
            "DECLARES_ROUTE",
            context,
            parser,
            line_number,
        )
    )
    if context.project:
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.project.entity),
                route.reference,
                "EXPOSES_ROUTE",
                context,
                parser,
                line_number,
            )
        )
    if handler:
        facts.relationships.append(route_handler_fact(context, route, handler, parser, line_number))
    return facts


def route_handler_fact(
    context: FileScanContext,
    route: EntityFact,
    handler: EntityFact,
    parser: str,
    line_number: int,
) -> RelationshipFact:
    return resolved_relationship_fact(
        route.reference,
        handler.reference,
        "HANDLES_ROUTE",
        context,
        parser,
        line_number,
        properties={
            key: value
            for key, value in {
                "route_method": route.properties.get("method"),
                "route_path": route.properties.get("path"),
                "normalized_route_path": route.properties.get("normalized_path"),
                "operation_name": route.properties.get("operation_name"),
                "handler_name": handler.name,
                "handler_type": handler.entity_type,
                "project": route.properties.get("project"),
            }.items()
            if value is not None
        },
    )


def route_entity_fact(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    parser: str,
    operation_name: str | None,
) -> EntityFact:
    normalized_path = normalize_route_path(path)
    properties = {
        "method": method,
        "path": path,
        "normalized_path": normalized_path,
        "project": context.project.name if context.project else None,
        "parser": parser,
    }
    if operation_name:
        properties["operation_name"] = operation_name
    return entity_fact(
        context,
        entity_type="api_route",
        name=f"{method} {path}",
        line_number=line_number,
        aliases={f"{method} {normalized_path}", normalized_path, path},
        properties=properties,
    )


def javascript_route_handler(line: str, handler_by_name: dict[str, EntityFact] | None) -> EntityFact | None:
    if not handler_by_name:
        return None
    for match in ROUTE_HANDLER_RE.finditer(line):
        handler = handler_by_name.get(match.group("handler"))
        if handler:
            return handler
    return None
