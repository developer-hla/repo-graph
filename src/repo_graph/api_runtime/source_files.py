"""Source file snippet response helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from repo_graph.api_runtime.constants import SOURCE_SNIPPET_MAX_BYTES, SOURCE_SNIPPET_MAX_CONTEXT
from repo_graph.api_runtime.settings import RuntimeSettings
from repo_graph.config import load_config
from repo_graph.sources import source_path
from repo_graph.storage import read_graph_scope


def source_file_snippet_response(
    settings: RuntimeSettings,
    source_name: str,
    file_path: str,
    line: int,
    context: int,
) -> dict[str, Any]:
    normalized_source_name = required_non_empty(source_name, "Source name")
    normalized_file_path = required_non_empty(file_path, "File path")
    normalized_line = normalize_snippet_line(line)
    normalized_context = normalize_snippet_context(context)
    source_root = source_root_path(settings, normalized_source_name)
    snippet_path = safe_source_file_path(source_root, normalized_file_path)
    lines = read_snippet_lines(snippet_path)
    if normalized_line > len(lines):
        raise ValueError(f"Line number {normalized_line} is outside file with {len(lines)} lines.")
    start_line = max(1, normalized_line - normalized_context)
    end_line = min(len(lines), normalized_line + normalized_context)
    selected_lines = [
        {
            "number": number,
            "text": lines[number - 1],
            "highlight": number == normalized_line,
        }
        for number in range(start_line, end_line + 1)
    ]
    return {
        "source_name": normalized_source_name,
        "source_path": str(source_root),
        "file_path": normalized_file_path,
        "line": normalized_line,
        "context": normalized_context,
        "start_line": start_line,
        "end_line": end_line,
        "highlight_line": normalized_line,
        "line_count": len(lines),
        "lines": selected_lines,
        "text": "\n".join(item["text"] for item in selected_lines),
    }


def source_root_path(settings: RuntimeSettings, source_name: str) -> Path:
    config_root = source_root_from_config(settings, source_name)
    if config_root is not None:
        return config_root
    graph_root = source_root_from_loaded_graph(settings, source_name)
    if graph_root is not None:
        return graph_root
    raise KeyError(source_name)


def source_root_from_config(settings: RuntimeSettings, source_name: str) -> Path | None:
    if settings.config_path is None:
        return None
    try:
        config = load_config(settings.config_path)
    except FileNotFoundError:
        return None
    for source in config.sources:
        if source.name != source_name:
            continue
        root = source_path(config, source)
        if root is None:
            return None
        return root.resolve()
    return None


def source_root_from_loaded_graph(settings: RuntimeSettings, source_name: str) -> Path | None:
    try:
        scope = read_graph_scope(settings.neo4j_settings())
    except ValueError:
        return None
    sources = scope.get("sources", [])
    if not isinstance(sources, list):
        return None
    for source in sources:
        if not isinstance(source, Mapping) or source.get("name") != source_name:
            continue
        path = source.get("path")
        if isinstance(path, str) and path.strip():
            return Path(path).expanduser().resolve()
    return None


def safe_source_file_path(source_root: Path, file_path: str) -> Path:
    requested_path = Path(file_path)
    if requested_path.is_absolute():
        raise ValueError("File path must be relative to the source root.")
    resolved_root = source_root.resolve()
    resolved_path = (resolved_root / requested_path).resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError("File path escapes the source root.")
    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(f"Source file not found: {file_path}")
    file_size = resolved_path.stat().st_size
    if file_size > SOURCE_SNIPPET_MAX_BYTES:
        raise ValueError(f"Source file is too large for snippets: {file_size} bytes.")
    return resolved_path


def read_snippet_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def normalize_snippet_line(value: int) -> int:
    if value < 1:
        raise ValueError("Line must be at least 1.")
    return value


def normalize_snippet_context(value: int) -> int:
    if value < 0:
        raise ValueError("Context must be at least 0.")
    if value > SOURCE_SNIPPET_MAX_CONTEXT:
        raise ValueError(f"Context must be at most {SOURCE_SNIPPET_MAX_CONTEXT}.")
    return value


def required_non_empty(value: str, label: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{label} is required.")
    return value.strip()


__all__ = [
    "normalize_snippet_context",
    "normalize_snippet_line",
    "read_snippet_lines",
    "required_non_empty",
    "safe_source_file_path",
    "source_file_snippet_response",
    "source_root_from_config",
    "source_root_from_loaded_graph",
    "source_root_path",
]
