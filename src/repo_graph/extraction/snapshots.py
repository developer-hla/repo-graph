"""Source snapshot helpers for incremental graph builds."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from repo_graph import __version__
from repo_graph.config import RepoGraphConfig
from repo_graph.extraction.orchestrator import MAX_FILE_BYTES, config_without_unsupported_sources
from repo_graph.extraction.registry import default_extractors
from repo_graph.extraction.scanners.common import safe_relative_path
from repo_graph.extraction.source_scanner import iter_scannable_files
from repo_graph.schema import GRAPH_SCHEMA_VERSION, SOURCE_SNAPSHOT_SCHEMA_VERSION
from repo_graph.sources import ResolvedSource, resolve_sources, sync_sources


@dataclass(frozen=True)
class SnapshotComparison:
    source_name: str
    changed: bool
    status: str
    reasons: tuple[str, ...]
    added_files: tuple[str, ...]
    modified_files: tuple[str, ...]
    removed_files: tuple[str, ...]
    current: dict[str, Any]
    previous: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "changed": self.changed,
            "status": self.status,
            "reasons": list(self.reasons),
            "added_files": list(self.added_files),
            "modified_files": list(self.modified_files),
            "removed_files": list(self.removed_files),
            "current": self.current,
            "previous": self.previous,
        }


def snapshot_status(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    scannable_config = config_without_unsupported_sources(config)
    sources = sync_sources(scannable_config) if sync_first else resolve_sources(scannable_config)
    items = [compare_source_snapshot(config, source, max_file_bytes=max_file_bytes).to_dict() for source in sources]
    items.extend(database_snapshot_items(config))
    return {
        "config": {
            "name": config.name,
            "path": str(config.config_path),
            "cache_dir": str(config.cache_dir),
            "output_dir": str(config.output_dir),
        },
        "snapshot_dir": str(snapshot_root(config)),
        "count": len(items),
        "changed_count": sum(1 for item in items if item["changed"]),
        "unchanged_count": sum(1 for item in items if not item["changed"]),
        "items": items,
    }


def write_snapshots(
    config: RepoGraphConfig,
    sync_first: bool = False,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    scannable_config = config_without_unsupported_sources(config)
    sources = sync_sources(scannable_config) if sync_first else resolve_sources(scannable_config)
    root = snapshot_root(config)
    root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for source in sources:
        snapshot = source_snapshot(config, source, max_file_bytes=max_file_bytes)
        path = source_snapshot_path(config, source)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        items.append({"source_name": source.name, "snapshot_path": str(path), "file_count": len(snapshot["files"])})
    return {
        "snapshot_dir": str(root),
        "count": len(items),
        "items": items,
    }


def database_snapshot_items(config: RepoGraphConfig) -> list[dict[str, Any]]:
    return [
        {
            "source_name": source.name,
            "changed": True,
            "status": "changed",
            "reasons": ["database_metadata_external"],
            "added_files": [],
            "modified_files": [],
            "removed_files": [],
            "current": {
                "source": {
                    "name": source.name,
                    "type": source.source_type,
                    "engine": source.engine,
                    "ref": source.ref,
                    "schemas": list(source.schemas),
                    "include_object_types": list(source.include_object_types),
                    "query_timeout_seconds": source.query_timeout_seconds,
                    "max_metadata_rows": source.max_metadata_rows,
                }
            },
            "previous": None,
        }
        for source in config.sources
        if source.source_type == "database"
    ]


def compare_source_snapshot(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> SnapshotComparison:
    current = source_snapshot(config, source, max_file_bytes=max_file_bytes)
    previous = read_source_snapshot(config, source)
    if previous is None:
        return SnapshotComparison(
            source_name=source.name,
            changed=True,
            status="new",
            reasons=("snapshot_missing",),
            added_files=tuple(sorted(file_hashes(current))),
            modified_files=(),
            removed_files=(),
            current=current,
            previous=None,
        )

    reasons = metadata_change_reasons(current, previous)
    current_files = file_hashes(current)
    previous_files = file_hashes(previous)
    added = tuple(sorted(set(current_files) - set(previous_files)))
    removed = tuple(sorted(set(previous_files) - set(current_files)))
    modified = tuple(
        sorted(path for path in set(current_files) & set(previous_files) if current_files[path] != previous_files[path])
    )
    all_reasons = (*reasons, *file_change_reasons(added, modified, removed))
    return SnapshotComparison(
        source_name=source.name,
        changed=bool(all_reasons),
        status="changed" if all_reasons else "unchanged",
        reasons=all_reasons,
        added_files=added,
        modified_files=modified,
        removed_files=removed,
        current=current,
        previous=previous,
    )


def source_snapshot(
    config: RepoGraphConfig,
    source: ResolvedSource,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> dict[str, Any]:
    scannable_files = iter_scannable_files(config, source.path, max_file_bytes)
    files = [file_snapshot(source, file_path) for file_path in scannable_files]
    files.sort(key=lambda item: item["path"])
    return {
        "snapshot_schema_version": SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "tool_version": __version__,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "parser_fingerprint": parser_fingerprint(),
        "source": {
            "name": source.name,
            "type": source.source_type,
            "path": str(source.path),
            "url": source.url,
            "ref": source.ref,
            "commit": source.commit,
        },
        "files": files,
        "file_count": len(files),
    }


def file_snapshot(source: ResolvedSource, file_path: Path) -> dict[str, Any]:
    stat = file_path.stat()
    return {
        "path": safe_relative_path(source.path, file_path),
        "sha256": file_hash(file_path),
        "size_bytes": stat.st_size,
    }


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_snapshot(config: RepoGraphConfig, source: ResolvedSource) -> dict[str, Any] | None:
    path = source_snapshot_path(config, source)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Source snapshot must be a JSON object: {path}")
    return data


def source_snapshot_path(config: RepoGraphConfig, source: ResolvedSource) -> Path:
    return snapshot_root(config) / safe_snapshot_name(source.name) / "snapshot.json"


def snapshot_root(config: RepoGraphConfig) -> Path:
    return config.output_dir.parent / "sources"


def safe_snapshot_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "._-" else "-" for character in value.strip())
    return safe.strip("-") or "source"


def metadata_change_reasons(current: Mapping[str, Any], previous: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for key in (
        "snapshot_schema_version",
        "tool_version",
        "graph_schema_version",
        "parser_fingerprint",
    ):
        if current.get(key) != previous.get(key):
            reasons.append(f"{key}_changed")
    current_source = mapping_value(current.get("source"))
    previous_source = mapping_value(previous.get("source"))
    for key in ("name", "type", "path", "url", "ref", "commit"):
        if current_source.get(key) != previous_source.get(key):
            reasons.append(f"source_{key}_changed")
    return tuple(reasons)


def file_change_reasons(
    added: tuple[str, ...],
    modified: tuple[str, ...],
    removed: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if added:
        reasons.append("files_added")
    if modified:
        reasons.append("files_modified")
    if removed:
        reasons.append("files_removed")
    return tuple(reasons)


def file_hashes(snapshot: Mapping[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for item in snapshot.get("files", []):
        if not isinstance(item, Mapping):
            continue
        path = item.get("path")
        digest = item.get("sha256")
        if isinstance(path, str) and isinstance(digest, str):
            hashes[path] = digest
    return hashes


def mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def parser_fingerprint() -> str:
    return sha256(parser_fingerprint_payload().encode("utf-8")).hexdigest()[:16]


def parser_fingerprint_payload() -> str:
    extractor_names = [extractor.name for extractor in default_extractors()]
    return "|".join([__version__, GRAPH_SCHEMA_VERSION, *extractor_names])
