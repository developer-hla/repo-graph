"""Application-boundary route and service helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.package_helpers import import_target_name

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


IMPORT_RE = re.compile(
    r"(?:import\s+(?:.+?\s+from\s+)?|export\s+.+?\s+from\s+|require\s*\()\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


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


EXPORT_FUNCTION_RE = re.compile(r"\bexport\s+(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")


EXPORT_CLASS_RE = re.compile(r"\bexport\s+class\s+([A-Za-z_$][\w$]*)")


EXPORT_CONST_RE = re.compile(
    r"\bexport\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)?\s*=>"
)


FETCH_RE = re.compile(r"\bfetch\s*\(\s*([\"'`])([^\"'`]+)\1(?P<args>[^)]*)", re.IGNORECASE)


AXIOS_RE = re.compile(
    r"\baxios\.(get|post|put|patch|delete|head|options)\s*\(\s*([\"'`])([^\"'`]+)\2",
    re.IGNORECASE,
)


ENV_URL_RE = re.compile(r"(?:process\.env\.|import\.meta\.env\.)([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))")


ENV_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))\b")


def import_facts(context: FileScanContext, line: str, line_number: int) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for match in IMPORT_RE.finditer(line):
        raw_target = match.group(1)
        target_name = import_target_name(raw_target)
        is_package = not raw_target.startswith(".")
        facts.append(
            unresolved_relationship_fact(
                entity_reference(context.file_entity),
                target_name,
                "IMPORTS",
                context,
                "javascript_import",
                to_type="package" if is_package else "module",
                line_number=line_number,
                properties={
                    "raw_target": raw_target,
                    "normalized_target": target_name,
                    "import_kind": "package" if is_package else "relative",
                },
            )
        )
    return facts


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


def export_symbol_facts(context: FileScanContext, line: str, line_number: int) -> FactBatch:
    facts = FactBatch()
    for entity_type, name in exported_symbols(line):
        symbol = entity_fact(
            context,
            entity_type=entity_type,
            name=name,
            line_number=line_number,
            aliases={name},
            properties={"project": context.project.name if context.project else None},
        )
        facts.entities.append(symbol)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                symbol.reference,
                "DECLARES_SYMBOL",
                context,
                "javascript_export",
                line_number,
            )
        )
    return facts


def exported_symbols(line: str) -> Iterable[tuple[str, str]]:
    for match in EXPORT_FUNCTION_RE.finditer(line):
        yield "function", match.group(1)
    for match in EXPORT_CLASS_RE.finditer(line):
        yield "class", match.group(1)
    for match in EXPORT_CONST_RE.finditer(line):
        yield "function", match.group(1)


def javascript_route_handler(line: str, handler_by_name: dict[str, EntityFact] | None) -> EntityFact | None:
    if not handler_by_name:
        return None
    for match in ROUTE_HANDLER_RE.finditer(line):
        handler = handler_by_name.get(match.group("handler"))
        if handler:
            return handler
    return None


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


def extract_endpoint(raw_target: str) -> str:
    if raw_target.startswith("${"):
        after_base = raw_target.split("}", 1)[-1]
        if after_base.startswith("/"):
            return after_base
    if "}" in raw_target:
        after_template = raw_target.rsplit("}", 1)[-1]
        if after_template.startswith("/"):
            return after_template
    parsed = urlparse(raw_target)
    if parsed.path:
        return parsed.path
    if raw_target.startswith("/"):
        return raw_target
    return raw_target


def service_name_from_env(env_var: str) -> str:
    name = env_var.lower()
    for suffix in ("_base_url", "_api_url", "_url", "_uri", "_endpoint", "_host"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", "-")


def url_value(value: object) -> str | None:
    raw_value = string_value(value)
    if not raw_value:
        return None
    parsed = urlparse(raw_value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw_value
    return None


def service_name_from_url(raw_target: str) -> str:
    host = urlparse(raw_target).hostname
    if not host:
        return "external-service"
    first_label = host.split(".", 1)[0]
    return service_name_from_identifier(first_label)


def service_name_from_identifier(value: object) -> str:
    raw_value = string_value(value) or "external-service"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", raw_value)
    normalized = re.sub(r"(?:Base)?(?:Url|Uri|Endpoint|Host)$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return normalized or "external-service"


def normalize_route_path(value: str) -> str:
    path = extract_endpoint(value)
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"\$\{[^}]+\}", ":param", path)
    path = re.sub(r"\{[^}]+\}", ":param", path)
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        if part.startswith(":") or part.isdigit():
            parts.append(":param")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"
