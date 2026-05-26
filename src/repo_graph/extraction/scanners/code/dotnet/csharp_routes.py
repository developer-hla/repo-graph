"""C# route extraction helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.code.dotnet.csharp_syntax import (
    CSharpAttribute,
    csharp_first_string,
    csharp_join_route_paths,
    csharp_replace_route_tokens,
    csharp_unescape_string,
)
from repo_graph.extraction.scanners.interaction_helpers import add_route_facts, route_entity_fact, route_handler_fact

CS_MINIMAL_ROUTE_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*\.\s*Map(Get|Post|Put|Patch|Delete|Head|Options)\s*\(\s*"
    r"(?:\$@|@\$|\$|@)?\"((?:\"\"|\\.|[^\"])*)\"",
    re.IGNORECASE,
)


def csharp_route_prefix(
    attributes: Sequence[CSharpAttribute],
    type_name: str | None,
    method_name: str | None,
) -> str | None:
    route_attribute = next((attribute for attribute in attributes if attribute.name == "route"), None)
    if not route_attribute:
        return None
    route = csharp_first_string(route_attribute.args)
    if route is None:
        return None
    return csharp_replace_route_tokens(route, type_name, method_name)


def csharp_controller_route_facts(
    context: FileScanContext,
    method_name: str,
    attributes: Sequence[CSharpAttribute],
    route_prefix: str | None,
    type_name: str | None,
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    route_path = csharp_route_prefix(attributes, type_name, method_name)
    for attribute in attributes:
        method = csharp_http_attribute_method(attribute)
        if not method:
            continue
        attribute_path = csharp_first_string(attribute.args) or route_path or ""
        path = csharp_join_route_paths(
            route_prefix, csharp_replace_route_tokens(attribute_path, type_name, method_name)
        )
        route = route_entity_fact(context, method, path, line_number, "dotnet_controller_route", method_name)
        facts.entities.append(route)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                route.reference,
                "DECLARES_ROUTE",
                context,
                "dotnet_controller_route",
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
                    "dotnet_controller_route",
                    line_number,
                )
            )
        if handler:
            facts.relationships.append(
                route_handler_fact(context, route, handler, "dotnet_controller_route", line_number)
            )
    return facts


def csharp_http_attribute_method(attribute: CSharpAttribute) -> str | None:
    methods = {
        "httpget": "GET",
        "httppost": "POST",
        "httpput": "PUT",
        "httppatch": "PATCH",
        "httpdelete": "DELETE",
        "httphead": "HEAD",
        "httpoptions": "OPTIONS",
    }
    return methods.get(attribute.name)


def csharp_minimal_route_facts(context: FileScanContext, line: str, line_number: int) -> FactBatch:
    facts = FactBatch()
    for match in CS_MINIMAL_ROUTE_RE.finditer(line):
        facts.extend(
            add_route_facts(
                context,
                match.group(1).upper(),
                csharp_unescape_string(match.group(2)),
                line_number,
                "dotnet_minimal_route",
            )
        )
    return facts


__all__ = [
    "csharp_controller_route_facts",
    "csharp_http_attribute_method",
    "csharp_minimal_route_facts",
    "csharp_route_prefix",
]
