"""Shared cache interaction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.sql.properties import source_context_properties

CACHE_NAME_RE = r"[A-Za-z_][\w.]*"
CACHE_METHOD_RE = re.compile(
    rf"(?:(?P<receiver>{CACHE_NAME_RE})\s*\.\s*)?"
    r"(?P<method>getString|setString|get_many|set_many|mget|mset|get|set|setex|"
    r"exists|delete|del|hget|hset)\s*\(",
    re.IGNORECASE,
)
CACHE_FIRST_ARG_RE = re.compile(
    r"\(\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)

READ_METHODS = frozenset({"exists", "get", "get_many", "getstring", "hget", "mget"})
WRITE_METHODS = frozenset({"del", "delete", "hset", "mset", "set", "set_many", "setex", "setstring"})
RECEIVER_HINTS = ("cache", "redis", "memcache", "memorycache", "distributedcache")


@dataclass(frozen=True)
class CacheTarget:
    name: str
    raw_target: str


@dataclass(frozen=True)
class CacheOperation:
    action: str
    method: str
    receiver: str | None = None

    @property
    def edge_type(self) -> str:
        if self.action == "read":
            return "READS_CACHE_KEY"
        return "WRITES_CACHE_KEY"

    @property
    def interaction_kind(self) -> str:
        return f"cache_{self.action}"


def cache_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in cache_operations_for_line(line):
        target = cache_target_for_line(line)
        if target:
            facts.append(cache_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


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


def cache_target_for_line(line: str) -> CacheTarget | None:
    match = CACHE_FIRST_ARG_RE.search(line)
    if not match:
        return None
    return cache_target(match.group("value"))


def cache_target(value: str) -> CacheTarget:
    normalized = normalize_cache_key(value)
    return CacheTarget(name=normalized, raw_target=value)


def cache_relationship_fact(
    context: FileScanContext,
    operation: CacheOperation,
    target: CacheTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "cache",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        cache_operation=operation.action,
        cache_method=operation.method,
        cache_receiver=operation.receiver,
    )
    properties.update(source_context_properties(from_entity))
    if extra_properties:
        properties.update(extra_properties)
    return unresolved_relationship_fact(
        entity_reference(from_entity or context.file_entity),
        target.name,
        operation.edge_type,
        context,
        parser,
        to_type="cache_key",
        line_number=line_number,
        properties=properties,
    )


def normalize_cache_key(value: str) -> str:
    return value.strip().strip("\"'")
