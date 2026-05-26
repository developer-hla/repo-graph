"""Neo4j storage data models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LoadSummary:
    scope_name: str | None
    schema_version: str | None
    source_count: int
    entity_count: int
    edge_count: int
    resolved_edge_count: int
    unresolved_edge_count: int
    unresolved_target_count: int
    clear_existing: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreparedGraphRecords:
    source_records: list[dict[str, Any]]
    entity_records: list[dict[str, Any]]
    edge_records: list[dict[str, Any]]
    target_records: list[dict[str, Any]]


__all__ = [
    "LoadSummary",
    "PreparedGraphRecords",
]
