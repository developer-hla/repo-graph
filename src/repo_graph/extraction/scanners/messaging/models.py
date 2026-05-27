"""Messaging scanner data models."""

from __future__ import annotations

from dataclasses import dataclass


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
