"""Cache target extraction."""

from __future__ import annotations

from repo_graph.extraction.scanners.cache.models import CacheTarget
from repo_graph.extraction.scanners.cache.patterns import CACHE_FIRST_ARG_RE


def cache_target_for_line(line: str) -> CacheTarget | None:
    match = CACHE_FIRST_ARG_RE.search(line)
    if not match:
        return None
    return cache_target(match.group("value"))


def cache_target(value: str) -> CacheTarget:
    normalized = normalize_cache_key(value)
    return CacheTarget(name=normalized, raw_target=value)


def normalize_cache_key(value: str) -> str:
    return value.strip().strip("\"'")
