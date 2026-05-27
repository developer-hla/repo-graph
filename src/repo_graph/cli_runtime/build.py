"""Build, load, and refresh CLI commands."""

from __future__ import annotations

import argparse

from repo_graph.api import RuntimeSettings
from repo_graph.cli_runtime.common import format_json, print_json, resolve_output_path
from repo_graph.config import load_config
from repo_graph.extraction import build_cached_graph, build_graph
from repo_graph.refresh import refresh_graph
from repo_graph.storage import load_graph_path


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    cache_summary = None
    if args.cached:
        cached_result = build_cached_graph(
            config,
            sync_first=args.sync,
            max_file_bytes=args.max_file_bytes,
            strict=args.strict,
        )
        graph = cached_result.graph
        cache_summary = cached_result.cache_summary
    else:
        graph = build_graph(config, sync_first=args.sync, max_file_bytes=args.max_file_bytes, strict=args.strict)
    output_path = resolve_output_path(config, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_data = graph.to_dict()
    if cache_summary is not None:
        graph_data["metadata"].update(
            {
                "build_mode": "cached",
                "source_artifact_dir": cache_summary["artifact_dir"],
                "source_artifact_reused_count": cache_summary["reused_count"],
                "source_artifact_rebuilt_count": cache_summary["rebuilt_count"],
            }
        )
    output_path.write_text(format_json(graph_data), encoding="utf-8")
    payload: dict[str, object] = {"output": str(output_path), "summary": graph_data["summary"]}
    if cache_summary is not None:
        payload["cache"] = cache_summary
    print_json(payload)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    settings = RuntimeSettings.from_env().neo4j_settings() if args.load else None
    print_json(
        refresh_graph(
            config,
            resolve_output_path(config, args.output),
            sync_first=args.sync,
            max_file_bytes=args.max_file_bytes,
            strict=args.strict,
            load=args.load,
            settings=settings,
        )
    )
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    settings = RuntimeSettings.from_env().neo4j_settings()
    summary = load_graph_path(
        args.graph,
        settings,
        clear_existing=not args.append and not args.replace_source,
        replace_sources=args.replace_source,
    )
    status = "source_replaced" if args.replace_source else "loaded"
    print_json(
        {
            "status": status,
            "graph_path": str(args.graph),
            "replace_sources": args.replace_source or [],
            "summary": summary.to_dict(),
        },
        sort_keys=False,
    )
    return 0
