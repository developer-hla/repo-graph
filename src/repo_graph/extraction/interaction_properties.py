"""Shared relationship property helpers."""

from __future__ import annotations

from typing import Any


def interaction_properties(
    target_boundary: str,
    dependency_scope: str,
    interaction_kind: str,
    **evidence: Any,
) -> dict[str, Any]:
    return {
        "target_boundary": target_boundary,
        "dependency_scope": dependency_scope,
        "interaction_kind": interaction_kind,
        **{key: value for key, value in evidence.items() if value is not None},
    }
