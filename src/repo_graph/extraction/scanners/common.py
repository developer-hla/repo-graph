"""Common scanner helpers."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import yaml

from repo_graph.sources import ResolvedSource


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def read_toml_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def read_yaml_object(content: str) -> dict[str, Any] | None:
    data = yaml.safe_load(content) or {}
    return data if isinstance(data, dict) else None


def project_name_from_path(source: ResolvedSource, path: Path) -> str:
    return source.name if path == source.path else path.name


def string_value(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def object_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
