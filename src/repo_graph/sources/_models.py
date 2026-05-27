"""Source resolver data models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedSource:
    name: str
    source_type: str
    path: Path
    url: str | None
    ref: str
    commit: str | None
