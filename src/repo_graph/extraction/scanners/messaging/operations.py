"""Messaging operation extraction."""

from __future__ import annotations

from repo_graph.extraction.scanners.messaging.models import MessageOperation
from repo_graph.extraction.scanners.messaging.patterns import (
    CONSUME_METHODS,
    GENERIC_METHODS,
    MESSAGE_METHOD_RE,
    PUBLISH_METHODS,
    QUEUE_METHODS,
    RECEIVER_HINTS,
)


def message_operations_for_line(line: str) -> list[MessageOperation]:
    operations: list[MessageOperation] = []
    for match in MESSAGE_METHOD_RE.finditer(line):
        operation = message_operation(
            match.group("method"),
            receiver=match.group("receiver"),
            generic_target=match.group("generic"),
        )
        if operation:
            operations.append(operation)
    return operations


def message_operation(
    method: str | None,
    receiver: str | None = None,
    generic_target: str | None = None,
) -> MessageOperation | None:
    if not method:
        return None
    normalized_method = method.lower()
    if normalized_method in PUBLISH_METHODS:
        action = "publish"
    elif normalized_method in CONSUME_METHODS:
        action = "consume"
    else:
        return None
    if not message_receiver_is_likely(receiver) and not method_or_target_is_specific(normalized_method, generic_target):
        return None
    return MessageOperation(action, normalized_method, receiver=receiver, generic_target=generic_target)


def message_receiver_is_likely(receiver: str | None) -> bool:
    if not receiver:
        return False
    normalized = receiver.lower()
    return any(hint in normalized for hint in RECEIVER_HINTS)


def method_or_target_is_specific(method: str, generic_target: str | None) -> bool:
    return method in QUEUE_METHODS or (method in GENERIC_METHODS and bool(generic_target))
