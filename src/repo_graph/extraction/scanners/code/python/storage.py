"""Python storage interaction helpers."""

from __future__ import annotations

import ast

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_call_receiver_name,
    python_call_root_name,
    python_keyword_string,
    python_string_arg,
)
from repo_graph.extraction.scanners.storage_helpers import (
    StorageOperation,
    StorageTarget,
    storage_operation,
    storage_relationship_fact,
    storage_target,
    storage_target_from_parts,
)


def python_storage_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    operation = python_storage_operation(call)
    if not operation:
        return []
    target = python_storage_target(call)
    if not target:
        return []
    return [storage_relationship_fact(context, operation, target, call.lineno, "python_storage", from_entity)]


def python_storage_operation(call: ast.Call) -> StorageOperation | None:
    callee = python_attribute_name(call.func)
    if callee == "open":
        return StorageOperation(python_open_mode_action(call), "open")
    return storage_operation(callee, receiver=python_call_root_name(call.func) or python_call_receiver_name(call.func))


def python_open_mode_action(call: ast.Call) -> str:
    mode = python_string_arg(call, 1) or python_keyword_string(call, "mode") or "r"
    if any(token in mode for token in ("w", "a", "x", "+")):
        return "write"
    return "read"


def python_storage_target(call: ast.Call) -> StorageTarget | None:
    values: dict[str, str] = {}
    for key in ("Bucket", "bucket", "bucket_name", "Container", "container", "Key", "key", "path", "file_path"):
        value = python_keyword_string(call, key)
        if value:
            values[key.lower()] = value
    if values:
        return storage_target_from_parts(values)
    raw_target = python_string_arg(call, 0)
    if raw_target:
        return storage_target(raw_target, "path", target_key="first_arg")
    return None
