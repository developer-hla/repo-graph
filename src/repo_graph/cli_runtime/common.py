"""Shared CLI helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from repo_graph.config import RepoGraphConfig
from repo_graph.validation import positive_int


def format_json(payload: object, sort_keys: bool = True) -> str:
    return json.dumps(payload, indent=2, sort_keys=sort_keys)


def print_json(payload: object, sort_keys: bool = True) -> None:
    print(format_json(payload, sort_keys=sort_keys))


def load_graph_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Graph JSON root must be an object.")
    return data


def resolve_output_path(config: RepoGraphConfig, output: Path | None) -> Path:
    if output is None:
        return config.output_dir / "graph.json"
    if output.is_absolute():
        return output
    return (Path.cwd() / output).resolve()


def max_file_bytes_argument(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max-file-bytes must be an integer.") from exc
    try:
        return positive_int(parsed, "max-file-bytes")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
