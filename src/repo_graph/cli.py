"""Command line entrypoint for RepoGraph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from repo_graph import __version__
from repo_graph.api import RuntimeSettings, create_app
from repo_graph.config import RepoGraphConfig, load_config
from repo_graph.reports import unresolved_report_from_graph
from repo_graph.scanner import MAX_FILE_BYTES, build_graph
from repo_graph.sources import resolve_sources, sync_sources
from repo_graph.storage.neo4j import load_graph_path, read_graph_stats

DEFAULT_API_URL = "http://localhost:8000"


def cmd_inspect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = resolve_sources(config)
    print(
        json.dumps(
            {
                "name": config.name,
                "cache_dir": str(config.cache_dir),
                "output_dir": str(config.output_dir),
                "source_count": len(sources),
                "sources": [
                    {
                        "name": source.name,
                        "type": source.source_type,
                        "ref": source.ref,
                        "path": str(source.path),
                        "url": source.url,
                        "commit": source.commit,
                    }
                    for source in sources
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = sync_sources(config)
    print(json.dumps({"count": len(sources), "synced": [source.name for source in sources]}, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    graph = build_graph(config, sync_first=args.sync, max_file_bytes=args.max_file_bytes, strict=args.strict)
    output_path = resolve_output_path(config, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_data = graph.to_dict()
    output_path.write_text(json.dumps(graph_data, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "summary": graph_data["summary"]}, indent=2, sort_keys=True))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env(config_path=args.config)
    uvicorn.run(create_app(settings), host=args.host, port=args.port)
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env().neo4j_settings()
    summary = load_graph_path(args.graph, settings, clear_existing=not args.append)
    print(json.dumps({"status": "loaded", "graph_path": str(args.graph), "summary": summary.to_dict()}, indent=2))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env().neo4j_settings()
    print(json.dumps(read_graph_stats(settings), indent=2, sort_keys=True))
    return 0


def cmd_agent_instructions(args: argparse.Namespace) -> int:
    print(agent_instructions_markdown(args.api_url, args.config))
    return 0


def cmd_report_unresolved(args: argparse.Namespace) -> int:
    graph_data = load_graph_json(args.graph)
    report = unresolved_report_from_graph(
        graph_data,
        source_name=args.source,
        edge_type=args.edge_type,
        group_limit=args.limit,
        examples_per_group=args.examples,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def load_graph_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Graph JSON root must be an object.")
    return data


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


def resolve_output_path(config: RepoGraphConfig, output: Path | None) -> Path:
    if output is None:
        return config.output_dir / "graph.json"
    if output.is_absolute():
        return output
    return (Path.cwd() / output).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and query repository interaction graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Validate and summarize a source config.")
    inspect_parser.add_argument("--config", type=Path, required=True)
    inspect_parser.set_defaults(func=cmd_inspect)

    sync_parser = subparsers.add_parser("sync", help="Clone or update Git sources into the local cache.")
    sync_parser.add_argument("--config", type=Path, required=True)
    sync_parser.set_defaults(func=cmd_sync)

    build_parser = subparsers.add_parser("build", help="Build a portable graph JSON file.")
    build_parser.add_argument("--config", type=Path, required=True)
    build_parser.add_argument("--output", type=Path)
    build_parser.add_argument("--sync", action="store_true", help="Sync Git sources before scanning.")
    build_parser.add_argument("--strict", action="store_true", help="Fail if any configured source cannot be scanned.")
    build_parser.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES)
    build_parser.set_defaults(func=cmd_build)

    serve_parser = subparsers.add_parser("serve", help="Run the local Repo Graph HTTP API.")
    serve_parser.add_argument("--config", type=Path)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.set_defaults(func=cmd_serve)

    load_parser = subparsers.add_parser("load", help="Load a graph JSON export into Neo4j.")
    load_parser.add_argument("--graph", type=Path, required=True)
    load_parser.add_argument("--append", action="store_true", help="Keep existing Repo Graph data in Neo4j.")
    load_parser.set_defaults(func=cmd_load)

    stats_parser = subparsers.add_parser("stats", help="Read Repo Graph counts from Neo4j.")
    stats_parser.set_defaults(func=cmd_stats)

    agent_parser = subparsers.add_parser("agent-instructions", help="Print a Markdown Repo Graph agent snippet.")
    agent_parser.add_argument("--api-url", default=DEFAULT_API_URL)
    agent_parser.add_argument("--config", type=Path)
    agent_parser.set_defaults(func=cmd_agent_instructions)

    report_parser = subparsers.add_parser("report", help="Generate reports from a graph JSON export.")
    report_subparsers = report_parser.add_subparsers(dest="report", required=True)
    unresolved_parser = report_subparsers.add_parser("unresolved", help="Group unresolved graph edges.")
    unresolved_parser.add_argument("--graph", type=Path, required=True)
    unresolved_parser.add_argument("--source")
    unresolved_parser.add_argument("--edge-type", dest="edge_type")
    unresolved_parser.add_argument("--limit", type=int, default=50)
    unresolved_parser.add_argument("--examples", type=int, default=3)
    unresolved_parser.set_defaults(func=cmd_report_unresolved)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
