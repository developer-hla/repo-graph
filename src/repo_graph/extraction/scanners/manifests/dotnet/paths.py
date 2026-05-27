""".NET manifest path helpers."""

from __future__ import annotations

from pathlib import PureWindowsPath


def dotnet_manifest_path_stem(raw_path: str) -> str:
    return PureWindowsPath(raw_path).stem


def dotnet_manifest_path_suffix(raw_path: str) -> str:
    return PureWindowsPath(raw_path).suffix.lower()
