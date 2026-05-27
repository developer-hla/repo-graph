"""Shared helpers for Neo4j read operations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def records_as_dicts(records: Iterable[Any]) -> list[dict[str, Any]]:
    return [dict(record) for record in records]
