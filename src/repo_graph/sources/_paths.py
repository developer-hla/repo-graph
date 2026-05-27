"""Source path helpers."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

from repo_graph.config import RepoGraphConfig, Source


def source_path(config: RepoGraphConfig, source: Source) -> Path | None:
    if source.source_type == "local_path":
        return source.path
    if source.source_type == "git":
        return git_cache_path(config.cache_dir, source)
    return None


def git_cache_path(cache_dir: Path, source: Source) -> Path:
    if source.source_type == "git" and source.url:
        url_hash = sha256(source.url.encode("utf-8")).hexdigest()[:10]
        return cache_dir / (f"{safe_path_name(source.name)}-{url_hash}")
    return cache_dir / safe_path_name(source.name)


def safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return safe.strip("-") or "repo"
