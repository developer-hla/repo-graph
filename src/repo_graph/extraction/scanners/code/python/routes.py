"""Python route declaration helpers."""

from __future__ import annotations

import ast
from collections.abc import Sequence

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_keyword_string,
    python_keyword_strings,
    python_string_arg,
)
from repo_graph.extraction.scanners.interaction_helpers import (
    HTTP_METHODS,
    route_entity_fact,
    route_handler_fact,
)


def python_route_facts(
    context: FileScanContext,
    operation_name: str,
    decorators: Sequence[ast.expr],
    line_number: int,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        path = python_string_arg(decorator, 0) or python_keyword_string(decorator, "path")
        if not path:
            continue
        for method in python_route_methods(decorator):
            facts.extend(python_add_route_facts(context, method, path, line_number, operation_name, handler))
    return facts


def python_route_methods(decorator: ast.Call) -> list[str]:
    callee = python_attribute_name(decorator.func)
    if callee in HTTP_METHODS:
        return [callee.upper()]
    if callee not in {"route", "api_route"}:
        return []
    methods = python_keyword_strings(decorator, "methods")
    return [method.upper() for method in methods] if methods else ["GET"]


def python_add_route_facts(
    context: FileScanContext,
    method: str,
    path: str,
    line_number: int,
    operation_name: str,
    handler: EntityFact | None = None,
) -> FactBatch:
    facts = FactBatch()
    route = route_entity_fact(context, method, path, line_number, "python_route", operation_name)
    facts.entities.append(route)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            route.reference,
            "DECLARES_ROUTE",
            context,
            "python_route",
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
                "python_route",
                line_number,
            )
        )
    if handler:
        facts.relationships.append(route_handler_fact(context, route, handler, "python_route", line_number))
    return facts
