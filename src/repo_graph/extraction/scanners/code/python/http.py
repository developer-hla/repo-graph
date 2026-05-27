"""Python HTTP interaction helpers."""

from __future__ import annotations

import ast
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_call_root_name,
    python_keyword_string,
    python_string_arg,
)
from repo_graph.extraction.scanners.interactions.http import HTTP_METHODS, http_facts_for_target, http_target
from repo_graph.extraction.scanners.interactions.naming import service_name_from_url
from repo_graph.extraction.scanners.sql.helpers import source_context_properties


def python_http_call_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    callee = python_attribute_name(call.func)
    root_name = python_call_root_name(call.func)
    if root_name not in {"httpx", "requests"}:
        return []
    if callee in HTTP_METHODS:
        raw_target = python_string_arg(call, 0) or python_keyword_string(call, "url")
        return python_http_facts_for_target(context, callee.upper(), raw_target, call.lineno, root_name, from_entity)
    if callee == "request":
        method = python_string_arg(call, 0) or python_keyword_string(call, "method") or "GET"
        raw_target = python_string_arg(call, 1) or python_keyword_string(call, "url")
        return python_http_facts_for_target(context, method.upper(), raw_target, call.lineno, root_name, from_entity)
    return []


def python_http_facts_for_target(
    context: FileScanContext,
    method: str,
    raw_target: str | None,
    line_number: int,
    client: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    if not raw_target:
        return []
    source_ref = entity_reference(from_entity or context.file_entity)
    extra_properties = source_context_properties(from_entity)
    parsed = urlparse(raw_target)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        target = http_target(raw_target, method)
        target["service_name"] = service_name_from_url(raw_target)
        target["client"] = client
        target.update(extra_properties)
        return [
            unresolved_relationship_fact(
                source_ref,
                target["service_name"],
                "CALLS_SERVICE",
                context,
                "python_http",
                to_type="service",
                line_number=line_number,
                properties=target,
            )
        ]
    return http_facts_for_target(
        context,
        method,
        raw_target,
        line_number,
        "python_http",
        client=client,
        from_entity=from_entity,
        extra_properties=extra_properties,
    )
