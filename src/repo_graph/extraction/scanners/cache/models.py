"""Cache scanner data models."""

from __future__ import annotations

from dataclasses import dataclass


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
