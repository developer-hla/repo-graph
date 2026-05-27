"""Source, sync, snapshot, and source graph CLI commands."""

from __future__ import annotations

import argparse

from repo_graph.cli_runtime.common import print_json
from repo_graph.config import load_config
from repo_graph.extraction import snapshot_status, write_snapshots, write_source_graphs
from repo_graph.sources import resolve_sources, sync_sources


def cmd_inspect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = resolve_sources(config)
    print_json(
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
        }
    )
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    sources = sync_sources(config)
    print_json({"count": len(sources), "synced": [source.name for source in sources]}, sort_keys=False)
    return 0


def cmd_snapshot_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print_json(snapshot_status(config, sync_first=args.sync, max_file_bytes=args.max_file_bytes))
    return 0


def cmd_snapshot_write(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print_json(write_snapshots(config, sync_first=args.sync, max_file_bytes=args.max_file_bytes))
    return 0


def cmd_source_graphs_write(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print_json(write_source_graphs(config, sync_first=args.sync, max_file_bytes=args.max_file_bytes))
    return 0
