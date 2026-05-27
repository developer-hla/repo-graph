"""Default config values and enum sets."""

from __future__ import annotations

from repo_graph.database import supported_database_engines

DEFAULT_CACHE_DIR = ".repo-graph/cache/repos"
DEFAULT_OUTPUT_DIR = ".repo-graph/output"
GITHUB_ORG_VISIBILITIES = {"all", "public", "private", "forks", "sources", "member"}
DATABASE_ENGINES = supported_database_engines()
DATABASE_OBJECT_TYPES = {
    "dependency",
    "foreign_key",
    "function",
    "stored_procedure",
    "table",
    "trigger",
    "view",
}
DEFAULT_DATABASE_OBJECT_TYPES = tuple(sorted(DATABASE_OBJECT_TYPES))

DEFAULT_FILE_EXTENSIONS = {
    ".cs",
    ".csproj",
    ".asmx",
    ".config",
    ".fsproj",
    ".js",
    ".json",
    ".jsx",
    ".py",
    ".props",
    ".sln",
    ".sql",
    ".svc",
    ".targets",
    ".toml",
    ".ts",
    ".tsx",
    ".vb",
    ".vbproj",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".repo-graph",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "out",
}
