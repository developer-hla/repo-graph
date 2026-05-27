"""Report CLI commands."""

from __future__ import annotations

import argparse

from repo_graph.cli_runtime.common import load_graph_json, print_json
from repo_graph.reports import (
    blast_radius_report_from_graph,
    database_reconciliation_report_from_graph,
    interactions_report_from_graph,
    unresolved_report_from_graph,
)


def cmd_report_unresolved(args: argparse.Namespace) -> int:
    graph_data = load_graph_json(args.graph)
    report = unresolved_report_from_graph(
        graph_data,
        source_name=args.source,
        edge_type=args.edge_type,
        group_limit=args.limit,
        examples_per_group=args.examples,
    )
    print_json(report)
    return 0


def cmd_report_interactions(args: argparse.Namespace) -> int:
    graph_data = load_graph_json(args.graph)
    report = interactions_report_from_graph(
        graph_data,
        source_name=args.source,
        target_source=args.target_source,
        edge_type=args.edge_type,
        group_limit=args.limit,
        examples_per_group=args.examples,
    )
    print_json(report)
    return 0


def cmd_report_database_reconciliation(args: argparse.Namespace) -> int:
    graph_data = load_graph_json(args.graph)
    report = database_reconciliation_report_from_graph(
        graph_data,
        source_name=args.source,
        database_source=args.database_source,
        group_limit=args.limit,
        examples_per_group=args.examples,
    )
    print_json(report)
    return 0


def cmd_report_blast_radius(args: argparse.Namespace) -> int:
    graph_data = load_graph_json(args.graph)
    report = blast_radius_report_from_graph(
        graph_data,
        args.entity_id,
        direction=args.direction,
        edge_type=args.edge_type,
        depth=args.depth,
        limit=args.limit,
        profile=args.profile,
    )
    print_json(report)
    return 0
