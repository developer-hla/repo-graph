"""Runtime and agent-instruction CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from repo_graph import __version__
from repo_graph.api import RuntimeSettings, create_app
from repo_graph.cli_runtime.common import print_json
from repo_graph.storage import read_graph_stats

DEFAULT_API_URL = "http://localhost:8000"


def cmd_serve(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env(config_path=args.config)
    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env().neo4j_settings()
    print_json(read_graph_stats(settings))
    return 0


def cmd_agent_instructions(args: argparse.Namespace) -> int:
    print(agent_instructions_markdown(args.api_url, args.config))
    return 0


def agent_instructions_markdown(api_url: str, config_path: Path | None = None) -> str:
    lines = [
        "## Repo Graph",
        "",
        "Repo Graph may be available as a local architecture graph for this codebase.",
        "Treat the runtime manifest as the source of truth for supported endpoints.",
        "",
        f"- API base URL: `{api_url}`",
        f"- Manifest: `{api_url}/manifest`",
    ]
    if config_path is not None:
        lines.append(f"- Expected config path: `{config_path}`")
    lines.extend(
        [
            f"- Configured source status: `{api_url}/sources/configured`",
            f"- Loaded graph scope: `{api_url}/scope`",
            f"- Loaded sources: `{api_url}/sources`",
            f"- Entity search: `{api_url}/entities/search`",
            f"- Interaction report: `{api_url}/reports/interactions`",
            f"- Unresolved edges: `{api_url}/edges/unresolved`",
            f"- Unresolved report: `{api_url}/reports/unresolved`",
            f"- Repo Graph version used to generate these instructions: `{__version__}`",
            "",
            "Before answering architecture questions, call the manifest, then check `/scope`",
            "and `/sources`. Use `/sources/configured` when you need to know which",
            "repositories are configured or missing locally before a graph has been loaded.",
            "Unresolved edges are discovered references that were not linked in the current",
            "graph scope; do not treat them as unused code by default. Use",
            "`/reports/unresolved` to group them into missing-source, ambiguous-target,",
            "and parser-coverage hints.",
        ]
    )
    return "\n".join(lines)
