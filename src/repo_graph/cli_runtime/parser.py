"""Argparse setup for RepoGraph CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from repo_graph.cli_runtime.build import cmd_build, cmd_load, cmd_refresh
from repo_graph.cli_runtime.common import max_file_bytes_argument
from repo_graph.cli_runtime.reports import (
    cmd_report_blast_radius,
    cmd_report_database_reconciliation,
    cmd_report_interactions,
    cmd_report_unresolved,
)
from repo_graph.cli_runtime.runtime import DEFAULT_API_URL, cmd_agent_instructions, cmd_serve, cmd_stats
from repo_graph.cli_runtime.sources import (
    cmd_inspect,
    cmd_snapshot_status,
    cmd_snapshot_write,
    cmd_source_graphs_write,
    cmd_sync,
)
from repo_graph.extraction import MAX_FILE_BYTES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and query repository interaction graphs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_source_commands(subparsers)
    add_build_commands(subparsers)
    add_serve_command(subparsers)
    add_load_command(subparsers)
    add_runtime_commands(subparsers)
    add_report_commands(subparsers)
    add_snapshot_commands(subparsers)
    add_source_graph_commands(subparsers)

    return parser


def add_source_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    inspect_parser = subparsers.add_parser("inspect", help="Validate and summarize a source config.")
    inspect_parser.add_argument("--config", type=Path, required=True, help="Path to the Repo Graph source config.")
    inspect_parser.set_defaults(func=cmd_inspect)

    sync_parser = subparsers.add_parser("sync", help="Clone or update Git sources into the local cache.")
    sync_parser.add_argument("--config", type=Path, required=True, help="Path to the Repo Graph source config.")
    sync_parser.set_defaults(func=cmd_sync)


def add_build_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    build_parser = subparsers.add_parser("build", help="Build a portable graph JSON file.")
    build_parser.add_argument("--config", type=Path, required=True, help="Path to the Repo Graph source config.")
    build_parser.add_argument("--output", type=Path, help="Graph JSON output path.")
    build_parser.add_argument("--sync", action="store_true", help="Sync Git sources before scanning.")
    build_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if source, scanner, database, or fact-validation errors occur.",
    )
    build_parser.add_argument("--cached", action="store_true", help="Reuse unchanged source graph artifacts.")
    build_parser.add_argument(
        "--max-file-bytes",
        type=max_file_bytes_argument,
        default=MAX_FILE_BYTES,
        help="Maximum file size to scan.",
    )
    build_parser.set_defaults(func=cmd_build)

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Build from source artifacts and optionally load changed sources into Neo4j.",
    )
    refresh_parser.add_argument("--config", type=Path, required=True, help="Path to the Repo Graph source config.")
    refresh_parser.add_argument("--output", type=Path, help="Graph JSON output path.")
    refresh_parser.add_argument("--sync", action="store_true", help="Sync Git sources before scanning.")
    refresh_parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if source, scanner, database, or fact-validation errors occur.",
    )
    refresh_parser.add_argument("--load", action="store_true", help="Load the refreshed graph into Neo4j.")
    refresh_parser.add_argument(
        "--max-file-bytes",
        type=max_file_bytes_argument,
        default=MAX_FILE_BYTES,
        help="Maximum file size to scan.",
    )
    refresh_parser.set_defaults(func=cmd_refresh)


def add_serve_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    serve_parser = subparsers.add_parser("serve", help="Run the local Repo Graph HTTP API.")
    serve_parser.add_argument("--config", type=Path, help="Path to the Repo Graph source config.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    serve_parser.set_defaults(func=cmd_serve)


def add_load_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    load_parser = subparsers.add_parser("load", help="Load a graph JSON export into Neo4j.")
    load_parser.add_argument("--graph", type=Path, required=True, help="Graph JSON file to load.")
    load_parser.add_argument("--append", action="store_true", help="Keep existing Repo Graph data in Neo4j.")
    load_parser.add_argument(
        "--replace-source",
        action="append",
        help="Replace one source's Neo4j data from a globally resolved graph. Repeat for multiple sources.",
    )
    load_parser.set_defaults(func=cmd_load)


def add_runtime_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    stats_parser = subparsers.add_parser("stats", help="Read Repo Graph counts from Neo4j.")
    stats_parser.set_defaults(func=cmd_stats)

    agent_parser = subparsers.add_parser("agent-instructions", help="Print a Markdown Repo Graph agent snippet.")
    agent_parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Base URL agents should use.")
    agent_parser.add_argument("--config", type=Path, help="Expected Repo Graph source config path.")
    agent_parser.set_defaults(func=cmd_agent_instructions)


def add_report_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    report_parser = subparsers.add_parser("report", help="Generate reports from a graph JSON export.")
    report_subparsers = report_parser.add_subparsers(dest="report", required=True)

    unresolved_parser = report_subparsers.add_parser("unresolved", help="Group unresolved graph edges.")
    unresolved_parser.add_argument("--graph", type=Path, required=True, help="Graph JSON file to report on.")
    unresolved_parser.add_argument("--source", help="Only include unresolved edges from this source.")
    unresolved_parser.add_argument("--edge-type", dest="edge_type", help="Only include unresolved edges of this type.")
    unresolved_parser.add_argument("--limit", type=int, default=50, help="Maximum unresolved groups to return.")
    unresolved_parser.add_argument("--examples", type=int, default=3, help="Examples to include per unresolved group.")
    unresolved_parser.set_defaults(func=cmd_report_unresolved)

    interactions_parser = report_subparsers.add_parser(
        "interactions",
        help="Group application and database interaction edges.",
    )
    interactions_parser.add_argument("--graph", type=Path, required=True, help="Graph JSON file to report on.")
    interactions_parser.add_argument("--source", help="Only include interactions from this source.")
    interactions_parser.add_argument("--target-source", help="Only include interactions targeting this source.")
    interactions_parser.add_argument("--edge-type", dest="edge_type", help="Only include interactions of this type.")
    interactions_parser.add_argument("--limit", type=int, default=50, help="Maximum interaction groups to return.")
    interactions_parser.add_argument("--examples", type=int, default=3, help="Examples to include per group.")
    interactions_parser.set_defaults(func=cmd_report_interactions)

    reconciliation_parser = report_subparsers.add_parser(
        "database-reconciliation",
        help="Compare code and SQL evidence with current database metadata.",
    )
    reconciliation_parser.add_argument("--graph", type=Path, required=True, help="Graph JSON file to report on.")
    reconciliation_parser.add_argument("--source", help="Only include code and schema evidence from this source.")
    reconciliation_parser.add_argument(
        "--database-source", help="Only include current database metadata from this source."
    )
    reconciliation_parser.add_argument("--limit", type=int, default=50, help="Maximum reconciliation groups to return.")
    reconciliation_parser.add_argument("--examples", type=int, default=3, help="Examples to include per group.")
    reconciliation_parser.set_defaults(func=cmd_report_database_reconciliation)

    blast_radius_parser = report_subparsers.add_parser(
        "blast-radius",
        help="Trace dependency paths around one graph entity.",
    )
    blast_radius_parser.add_argument("--graph", type=Path, required=True, help="Graph JSON file to report on.")
    blast_radius_parser.add_argument("--entity-id", required=True, help="Entity ID to use as the blast-radius root.")
    blast_radius_parser.add_argument(
        "--direction",
        choices=["in", "out", "both"],
        default="in",
        help="Traversal direction from the root entity.",
    )
    blast_radius_parser.add_argument("--edge-type", dest="edge_type", help="Only traverse this edge type.")
    blast_radius_parser.add_argument(
        "--profile",
        choices=["all", "impact", "structural"],
        default="impact",
        help="Edge profile to traverse when --edge-type is not set.",
    )
    blast_radius_parser.add_argument("--depth", type=int, default=2, help="Traversal depth, from 1 to 3.")
    blast_radius_parser.add_argument("--limit", type=int, default=100, help="Maximum paths to return.")
    blast_radius_parser.set_defaults(func=cmd_report_blast_radius)


def add_snapshot_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    snapshot_parser = subparsers.add_parser("snapshot", help="Inspect or write source snapshots.")
    snapshot_subparsers = snapshot_parser.add_subparsers(dest="snapshot", required=True)

    snapshot_status_parser = snapshot_subparsers.add_parser("status", help="Compare current sources to snapshots.")
    snapshot_status_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the Repo Graph source config.",
    )
    snapshot_status_parser.add_argument("--sync", action="store_true", help="Sync Git sources before snapshotting.")
    snapshot_status_parser.add_argument(
        "--max-file-bytes",
        type=max_file_bytes_argument,
        default=MAX_FILE_BYTES,
        help="Maximum file size to include in snapshot hashing.",
    )
    snapshot_status_parser.set_defaults(func=cmd_snapshot_status)

    snapshot_write_parser = snapshot_subparsers.add_parser("write", help="Write current source snapshots.")
    snapshot_write_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the Repo Graph source config.",
    )
    snapshot_write_parser.add_argument("--sync", action="store_true", help="Sync Git sources before snapshotting.")
    snapshot_write_parser.add_argument(
        "--max-file-bytes",
        type=max_file_bytes_argument,
        default=MAX_FILE_BYTES,
        help="Maximum file size to include in snapshot hashing.",
    )
    snapshot_write_parser.set_defaults(func=cmd_snapshot_write)


def add_source_graph_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    source_graphs_parser = subparsers.add_parser("source-graphs", help="Build source-level graph artifacts.")
    source_graphs_subparsers = source_graphs_parser.add_subparsers(dest="source_graphs", required=True)
    source_graphs_write_parser = source_graphs_subparsers.add_parser(
        "write",
        help="Write one graph artifact per source.",
    )
    source_graphs_write_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the Repo Graph source config.",
    )
    source_graphs_write_parser.add_argument("--sync", action="store_true", help="Sync Git sources before scanning.")
    source_graphs_write_parser.add_argument(
        "--max-file-bytes",
        type=max_file_bytes_argument,
        default=MAX_FILE_BYTES,
        help="Maximum file size to scan.",
    )
    source_graphs_write_parser.set_defaults(func=cmd_source_graphs_write)
