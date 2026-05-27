"""Cache operation extraction."""

from __future__ import annotations

from repo_graph.extraction.scanners.cache.models import CacheOperation
from repo_graph.extraction.scanners.cache.patterns import (
    CACHE_METHOD_RE,
    READ_METHODS,
    RECEIVER_HINTS,
    WRITE_METHODS,
)


def cache_operations_for_line(line: str) -> list[CacheOperation]:
    operations: list[CacheOperation] = []
    for match in CACHE_METHOD_RE.finditer(line):
        operation = cache_operation(match.group("method"), receiver=match.group("receiver"))
        if operation:
            operations.append(operation)
    return operations


def cache_operation(method: str | None, receiver: str | None = None) -> CacheOperation | None:
    if not method:
        return None
    normalized_method = method.lower()
    if normalized_method in READ_METHODS:
        action = "read"
    elif normalized_method in WRITE_METHODS:
        action = "write"
    else:
        return None
    if not cache_receiver_is_likely(receiver) and normalized_method in {"get", "set", "delete"}:
        return None
    return CacheOperation(action, normalized_method, receiver=receiver)


def cache_receiver_is_likely(receiver: str | None) -> bool:
    if not receiver:
        return False
    normalized = receiver.lower()
    return any(hint in normalized for hint in RECEIVER_HINTS)
