"""Storage scanner data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StorageTarget:
    name: str
    raw_target: str
    storage_kind: str
    bucket: str | None = None
    container: str | None = None
    object_key: str | None = None
    target_key: str | None = None


@dataclass(frozen=True)
class StorageOperation:
    action: str
    method: str
    receiver: str | None = None

    @property
    def edge_type(self) -> str:
        if self.action == "read":
            return "READS_STORAGE_OBJECT"
        return "WRITES_STORAGE_OBJECT"

    @property
    def interaction_kind(self) -> str:
        return f"storage_{self.action}"
