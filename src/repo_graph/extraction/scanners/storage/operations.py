"""Storage operation extraction."""

from __future__ import annotations

from repo_graph.extraction.scanners.storage.models import StorageOperation
from repo_graph.extraction.scanners.storage.patterns import (
    BROAD_STORAGE_METHODS,
    READ_METHODS,
    RECEIVER_HINTS,
    STORAGE_METHOD_RE,
    WRITE_METHODS,
)


def storage_operations_for_line(line: str) -> list[StorageOperation]:
    operations: list[StorageOperation] = []
    for match in STORAGE_METHOD_RE.finditer(line):
        operation = storage_operation(match.group("method"), receiver=match.group("receiver"))
        if operation:
            operations.append(operation)
    return operations


def storage_operation(method: str | None, receiver: str | None = None) -> StorageOperation | None:
    if not method:
        return None
    normalized_method = method.lower()
    if normalized_method in READ_METHODS:
        action = "read"
    elif normalized_method in WRITE_METHODS:
        action = "write"
    else:
        return None
    if not storage_receiver_is_likely(receiver) and normalized_method not in specific_storage_methods():
        return None
    return StorageOperation(action, normalized_method, receiver=receiver)


def storage_receiver_is_likely(receiver: str | None) -> bool:
    if not receiver:
        return False
    normalized = receiver.lower()
    return any(hint in normalized for hint in RECEIVER_HINTS)


def specific_storage_methods() -> frozenset[str]:
    return (READ_METHODS | WRITE_METHODS) - BROAD_STORAGE_METHODS
