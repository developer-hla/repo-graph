"""SQL object naming helpers."""

from __future__ import annotations


def normalize_sql_name(value: str) -> str:
    return value.strip().replace("[", "").replace("]", "")


def split_schema_name(value: str) -> tuple[str | None, str]:
    parts = value.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, value
