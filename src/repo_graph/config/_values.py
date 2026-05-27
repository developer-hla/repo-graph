"""Scalar config parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def resolve_config_path(config_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def validate_regex_patterns(patterns: tuple[str, ...], field_name: str) -> None:
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"{field_name} contains invalid regex '{pattern}': {exc}") from exc


def normalize_extension(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("File extensions must be non-empty strings.")
    extension = value.strip().lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    return extension


def object_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise ValueError(f"{field_name} must be a mapping.")


def string_tuple(value: Any, field_name: str = "Name patterns") -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple | set):
        raise ValueError(f"{field_name} must be a list.")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} must contain non-empty strings.")
        items.append(item.strip())
    return tuple(items)


def required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError("Boolean config values must be true or false.")


def optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return value
