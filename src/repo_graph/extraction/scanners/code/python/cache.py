"""Python cache interaction helpers."""

from __future__ import annotations

import ast

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.cache.facts import cache_relationship_fact
from repo_graph.extraction.scanners.cache.operations import cache_operation
from repo_graph.extraction.scanners.cache.targets import cache_target
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_call_receiver_name,
    python_call_root_name,
    python_string_arg,
)


def python_cache_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    operation = cache_operation(
        python_attribute_name(call.func),
        receiver=python_call_root_name(call.func) or python_call_receiver_name(call.func),
    )
    raw_target = python_string_arg(call, 0)
    if not operation or not raw_target:
        return []
    return [
        cache_relationship_fact(context, operation, cache_target(raw_target), call.lineno, "python_cache", from_entity)
    ]
