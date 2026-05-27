"""Python messaging interaction helpers."""

from __future__ import annotations

import ast

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.scanners.code.python.ast_values import (
    python_attribute_name,
    python_call_receiver_name,
    python_call_root_name,
    python_keyword_strings,
    python_string_values_from_arg,
)
from repo_graph.extraction.scanners.messaging_helpers import (
    MessageTarget,
    message_operation,
    message_relationship_fact,
    message_target,
)


def python_message_facts(
    context: FileScanContext,
    call: ast.Call,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    callee = python_attribute_name(call.func)
    operation = message_operation(
        callee,
        receiver=python_call_root_name(call.func) or python_call_receiver_name(call.func),
    )
    if not operation:
        return []
    return [
        message_relationship_fact(context, operation, target, call.lineno, "python_message", from_entity)
        for target in python_message_targets(call, operation.method)
    ]


def python_message_targets(call: ast.Call, method: str) -> list[MessageTarget]:
    targets: list[MessageTarget] = []
    for key in ("topic", "topics", "queue", "queue_name", "QueueName", "QueueUrl", "routing_key"):
        values = python_keyword_strings(call, key)
        targets.extend(message_target(value, python_message_destination_kind(key), key) for value in values)
    if not targets:
        targets.extend(
            message_target(value, python_message_destination_kind_for_method(method), "first_arg")
            for value in python_string_values_from_arg(call, 0)
        )
    return targets


def python_message_destination_kind(key: str) -> str:
    normalized = key.lower()
    if "queue" in normalized or "routing" in normalized:
        return "queue"
    return "topic"


def python_message_destination_kind_for_method(method: str) -> str:
    if method in {"basic_consume", "receive_message", "send_message"}:
        return "queue"
    return "topic"
