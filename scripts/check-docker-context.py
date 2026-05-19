"""Check that local-only files stay out of the Docker build context."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

REQUIRED_PATTERNS = (
    ".git/",
    ".pixi/",
    ".repo-graph/",
    ".env",
    ".env.*",
    "graph.json",
    "config/*.local.yaml",
    "config/private*.yaml",
)

SENSITIVE_SENTINELS = (
    ".git/config",
    ".pixi/env/conda-meta/history",
    ".repo-graph/output/graph.json",
    ".repo-graph/cache/repos/private-source/file.py",
    ".env",
    ".env.local",
    ".env.private",
    "graph.json",
    "config/service.local.yaml",
    "config/private-sources.yaml",
)


def main() -> int:
    dockerignore = Path(".dockerignore")
    if not dockerignore.exists():
        print("Missing .dockerignore.")
        return 1

    patterns = dockerignore_patterns(dockerignore)
    missing = [pattern for pattern in REQUIRED_PATTERNS if pattern not in patterns]
    exposed = [path for path in SENSITIVE_SENTINELS if not is_ignored(path, patterns)]

    if not missing and not exposed:
        print("Docker context privacy check passed.")
        return 0

    if missing:
        print("Missing required .dockerignore patterns:")
        for pattern in missing:
            print(f"  - {pattern}")
    if exposed:
        print("Sensitive sentinel paths are not ignored by .dockerignore:")
        for path in exposed:
            print(f"  - {path}")
    return 1


def dockerignore_patterns(path: Path) -> list[str]:
    return [
        stripped
        for line in path.read_text(encoding="utf-8").splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    ]


def is_ignored(path: str, patterns: list[str]) -> bool:
    ignored = False
    for raw_pattern in patterns:
        negated = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negated else raw_pattern
        if pattern_matches(pattern, path):
            ignored = not negated
    return ignored


def pattern_matches(pattern: str, path: str) -> bool:
    normalized = normalize_path(path)
    normalized_pattern = normalize_path(pattern)
    directory_pattern = normalized_pattern.endswith("/")
    if directory_pattern:
        normalized_pattern = normalized_pattern.rstrip("/")

    if "/" in normalized_pattern:
        return path_pattern_matches(normalized_pattern, normalized, directory_pattern)
    return basename_pattern_matches(normalized_pattern, normalized, directory_pattern)


def path_pattern_matches(pattern: str, path: str, directory_pattern: bool) -> bool:
    if directory_pattern:
        return path == pattern or path.startswith(f"{pattern}/")
    return fnmatchcase(path, pattern)


def basename_pattern_matches(pattern: str, path: str, directory_pattern: bool) -> bool:
    parts = path.split("/")
    if directory_pattern:
        return any(part == pattern for part in parts[:-1])
    return any(fnmatchcase(part, pattern) for part in parts)


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
