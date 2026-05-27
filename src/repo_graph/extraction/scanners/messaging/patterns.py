"""Messaging scanner regexes and method sets."""

from __future__ import annotations

import re

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
