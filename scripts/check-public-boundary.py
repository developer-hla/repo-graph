"""Scan public files for private-boundary leaks."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

SCAN_TARGETS = (
    ".dockerignore",
    ".env.example",
    ".github",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "config",
    "docker-compose.yaml",
    "docs",
    "examples",
    "pixi.toml",
    "scripts",
    "src",
    "tests",
)

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pixi",
    ".pytest_cache",
    ".repo-graph",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
}

EXCLUDED_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.egg-info/*",
    "pixi.lock",
)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    description: str


@dataclass(frozen=True)
class AllowlistEntry:
    rule_name: str
    path_pattern: str
    match_pattern: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    path: str
    line_number: int
    rule_name: str
    description: str


BUILT_IN_RULES = (
    Rule(
        "github_token_value",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
        "GitHub token value",
    ),
    Rule(
        "private_key_block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "private key block",
    ),
    Rule(
        "credential_in_url",
        re.compile(r"https?://[^/\s:@]+:[^@\s]+@"),
        "credential embedded in URL",
    ),
    Rule(
        "absolute_home_path",
        re.compile(r"\b(?:/Users|/home)/[A-Za-z0-9._-]+"),
        "absolute local home path",
    ),
    Rule(
        "private_placeholder",
        re.compile(r"\b(?:PRIVATE_TERM|ORG_NAME|INTERNAL_DB|INTERNAL_ONLY|DO_NOT_COMMIT)\b"),
        "private placeholder marker",
    ),
    Rule(
        "token_handling_identifier",
        re.compile(r"\b(?:GITHUB_TOKEN|GH_TOKEN|AUTHORIZATION|x-access-token|secret-token)\b"),
        "token-handling identifier outside an approved file",
    ),
)

ALLOWLIST = (
    AllowlistEntry("private_placeholder", "scripts/check-public-boundary.py", re.compile(r".*")),
    AllowlistEntry("token_handling_identifier", ".env.example", re.compile(r"\bGITHUB_TOKEN\b")),
    AllowlistEntry("token_handling_identifier", "README.md", re.compile(r"\bGITHUB_TOKEN\b")),
    AllowlistEntry("token_handling_identifier", "docs/agent-usage.md", re.compile(r"\bGITHUB_TOKEN\b")),
    AllowlistEntry(
        "token_handling_identifier",
        "docker-compose.yaml",
        re.compile(r"\b(?:GITHUB_TOKEN|GH_TOKEN)\b"),
    ),
    AllowlistEntry(
        "token_handling_identifier",
        "scripts/docker-smoke.sh",
        re.compile(r"\b(?:GITHUB_TOKEN|GH_TOKEN)\b"),
    ),
    AllowlistEntry("token_handling_identifier", "scripts/check-public-boundary.py", re.compile(r".*")),
    AllowlistEntry(
        "token_handling_identifier",
        "src/repo_graph/sources.py",
        re.compile(r"\b(?:GITHUB_TOKEN|GH_TOKEN|AUTHORIZATION|x-access-token)\b"),
    ),
    AllowlistEntry("token_handling_identifier", "tests/test_sources.py", re.compile(r".*")),
)


def main() -> int:
    files = list(candidate_files(Path("."), SCAN_TARGETS))
    rules = (*BUILT_IN_RULES, *local_private_term_rules())
    findings = sorted(scan_files(files, rules, ALLOWLIST), key=finding_key)

    if not findings:
        print(f"Public boundary check passed across {len(files)} files.")
        return 0

    print("Public boundary check failed.")
    print("Matches are reported without line contents to avoid echoing sensitive values.")
    for finding in findings:
        print(f"  - {finding.path}:{finding.line_number} [{finding.rule_name}] {finding.description}")
    return 1


def candidate_files(root: Path, targets: Iterable[str]) -> Iterable[Path]:
    for target in targets:
        path = root / target
        if not path.exists():
            continue
        if path.is_file():
            if should_scan_file(path):
                yield path
            continue
        for child in path.rglob("*"):
            if child.is_file() and should_scan_file(child):
                yield child


def should_scan_file(path: Path) -> bool:
    relative = normalize_path(path)
    parts = relative.split("/")
    if any(part in EXCLUDED_DIRS for part in parts):
        return False
    return not any(fnmatchcase(relative, pattern) for pattern in EXCLUDED_FILE_PATTERNS)


def scan_files(
    files: Iterable[Path],
    rules: Iterable[Rule],
    allowlist: Iterable[AllowlistEntry],
) -> Iterable[Finding]:
    for path in files:
        relative_path = normalize_path(path)
        for line_number, line in read_lines(path):
            for rule in rules:
                for match in rule.pattern.finditer(line):
                    if not is_allowed(rule.name, relative_path, match.group(0), allowlist):
                        yield Finding(relative_path, line_number, rule.name, rule.description)


def read_lines(path: Path) -> Iterable[tuple[int, str]]:
    try:
        with path.open(encoding="utf-8") as file:
            yield from enumerate(file, start=1)
    except UnicodeDecodeError:
        return


def is_allowed(
    rule_name: str,
    path: str,
    match: str,
    allowlist: Iterable[AllowlistEntry],
) -> bool:
    return any(
        entry.rule_name == rule_name and fnmatchcase(path, entry.path_pattern) and entry.match_pattern.search(match)
        for entry in allowlist
    )


def local_private_term_rules() -> tuple[Rule, ...]:
    terms_path = os.environ.get("REPO_GRAPH_PUBLIC_BOUNDARY_TERMS")
    if not terms_path:
        return ()

    path = Path(terms_path).expanduser()
    if not path.exists():
        raise SystemExit(f"Local public-boundary terms file not found: {path}")

    terms = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return tuple(
        Rule(
            f"local_private_term_{index}",
            re.compile(re.escape(term), re.IGNORECASE),
            "local private term",
        )
        for index, term in enumerate(terms, start=1)
    )


def finding_key(finding: Finding) -> tuple[str, int, str]:
    return (finding.path, finding.line_number, finding.rule_name)


def normalize_path(path: Path | str) -> str:
    normalized = str(path).replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
