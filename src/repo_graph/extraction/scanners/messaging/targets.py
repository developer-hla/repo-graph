"""Messaging target extraction."""

from __future__ import annotations

from urllib.parse import urlparse

from repo_graph.extraction.scanners.messaging.models import MessageOperation, MessageTarget
from repo_graph.extraction.scanners.messaging.patterns import (
    MESSAGE_FIRST_ARG_RE,
    MESSAGE_KEY_VALUE_RE,
    QUEUE_METHODS,
)


def message_targets_for_line(line: str, operation: MessageOperation) -> list[MessageTarget]:
    targets: list[MessageTarget] = []
    if operation.generic_target:
        targets.append(message_target(operation.generic_target, "contract", raw_target=operation.generic_target))
    for match in MESSAGE_KEY_VALUE_RE.finditer(line):
        targets.append(
            message_target(match.group("value"), destination_kind_for_key(match.group("key")), match.group("key"))
        )
    if not targets:
        first_arg = MESSAGE_FIRST_ARG_RE.search(line)
        if first_arg:
            targets.append(
                message_target(first_arg.group("value"), destination_kind_for_method(operation.method), "first_arg")
            )
    return dedupe_message_targets(targets)


def message_target(
    value: str,
    destination_kind: str,
    target_key: str | None = None,
    raw_target: str | None = None,
) -> MessageTarget:
    normalized = normalize_message_target(value)
    entity_type = {
        "contract": "message_contract",
        "queue": "message_queue",
        "topic": "message_topic",
    }.get(destination_kind, "message_topic")
    return MessageTarget(
        name=normalized,
        entity_type=entity_type,
        raw_target=raw_target or value,
        destination_kind=destination_kind,
        target_key=target_key,
    )


def destination_kind_for_key(key: str | None) -> str:
    normalized = (key or "").lower()
    if "queue" in normalized or "routing" in normalized:
        return "queue"
    if "topic" in normalized:
        return "topic"
    return "topic"


def destination_kind_for_method(method: str) -> str:
    if method in QUEUE_METHODS:
        return "queue"
    return "topic"


def normalize_message_target(value: str) -> str:
    raw = value.strip()
    parsed = urlparse(raw)
    if parsed.scheme and parsed.path:
        candidate = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        if candidate:
            return candidate
    if raw.lower().startswith("arn:"):
        candidate = raw.rsplit(":", 1)[-1]
        if candidate:
            return candidate
    return raw.strip("\"'")


def dedupe_message_targets(targets: list[MessageTarget]) -> list[MessageTarget]:
    deduped: dict[tuple[str, str], MessageTarget] = {}
    for target in targets:
        deduped[(target.entity_type, target.name)] = target
    return list(deduped.values())
