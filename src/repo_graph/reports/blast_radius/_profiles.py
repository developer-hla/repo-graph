"""Blast-radius profiles and request validation."""

from __future__ import annotations

from repo_graph.vocabulary import IMPACT_PROFILES

DEFAULT_BLAST_RADIUS_LIMIT = 100
DEFAULT_BLAST_RADIUS_DEPTH = 2


def normalize_blast_radius_profile(value: str) -> str:
    profile = value.strip().lower()
    if profile not in IMPACT_PROFILES:
        raise ValueError("Impact profile must be one of: all, impact, structural.")
    return profile


def blast_radius_profile_edge_types(profile: str, edge_type: str | None) -> frozenset[str] | None:
    if edge_type:
        return None
    return IMPACT_PROFILES[profile]


def normalize_blast_radius_direction(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"in", "out", "both"}:
        raise ValueError("Direction must be one of: in, out, both.")
    return normalized


def validate_blast_radius_depth(value: int) -> None:
    if value < 1:
        raise ValueError("Depth must be at least 1.")
    if value > 3:
        raise ValueError("Depth must be at most 3.")
