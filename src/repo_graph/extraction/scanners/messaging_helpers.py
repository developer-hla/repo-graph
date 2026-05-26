"""Shared messaging interaction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.sql.helpers import source_context_properties

MESSAGE_NAME_RE = r"[A-Za-z_][\w.]*"
MESSAGE_METHOD_RE = re.compile(
    rf"(?:(?P<receiver>{MESSAGE_NAME_RE})\s*\.\s*)?"
    r"(?P<method>sendToQueue|basic_publish|basic_consume|sendMessage|receiveMessage|send_message|"
    r"receive_message|PublishAsync|SubscribeAsync|ReceiveAsync|ProduceAsync|SendAsync|Publish|Subscribe|"
    r"Receive|Produce|publish|subscribe|consume|produce|send|emit)\s*"
    rf"(?:<\s*(?P<generic>{MESSAGE_NAME_RE})\s*>)?\s*\(",
    re.IGNORECASE,
)
MESSAGE_KEY_VALUE_RE = re.compile(
    r"(?P<key>topic|topics|queue|queue_name|queueName|QueueName|QueueUrl|routing_key|routingKey)"
    r"\s*[:=]\s*(?:\[\s*)?(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)
MESSAGE_FIRST_ARG_RE = re.compile(
    r"\(\s*(?:new\s*\[\]\s*\{\s*)?(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)

PUBLISH_METHODS = frozenset(
    {
        "basic_publish",
        "emit",
        "produce",
        "produceasync",
        "publish",
        "publishasync",
        "send",
        "send_message",
        "sendasync",
        "sendmessage",
        "sendtoqueue",
    }
)
CONSUME_METHODS = frozenset(
    {
        "basic_consume",
        "consume",
        "receive",
        "receive_message",
        "receiveasync",
        "receivemessage",
        "subscribe",
        "subscribeasync",
    }
)
RECEIVER_HINTS = (
    "bus",
    "channel",
    "consumer",
    "event",
    "kafka",
    "message",
    "producer",
    "publisher",
    "queue",
    "rabbit",
    "sns",
    "sqs",
    "subscriber",
    "topic",
)
QUEUE_METHODS = frozenset(
    {
        "basic_consume",
        "receive_message",
        "receivemessage",
        "send_message",
        "sendmessage",
        "sendtoqueue",
    }
)
GENERIC_METHODS = frozenset({"publish", "publishasync", "sendasync", "subscribe", "subscribeasync"})


@dataclass(frozen=True)
class MessageTarget:
    name: str
    entity_type: str
    raw_target: str
    destination_kind: str
    target_key: str | None = None


@dataclass(frozen=True)
class MessageOperation:
    action: str
    method: str
    receiver: str | None = None
    generic_target: str | None = None

    @property
    def edge_type(self) -> str:
        if self.action == "publish":
            return "PUBLISHES_MESSAGE"
        return "CONSUMES_MESSAGE"

    @property
    def interaction_kind(self) -> str:
        return f"message_{self.action}"


def message_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in message_operations_for_line(line):
        for target in message_targets_for_line(line, operation):
            facts.append(message_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


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


def message_relationship_fact(
    context: FileScanContext,
    operation: MessageOperation,
    target: MessageTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "messaging",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        message_destination_type=target.entity_type,
        message_destination_kind=target.destination_kind,
        message_operation=operation.action,
        messaging_method=operation.method,
        messaging_receiver=operation.receiver,
        target_key=target.target_key,
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
        to_type=target.entity_type,
        line_number=line_number,
        properties=properties,
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
