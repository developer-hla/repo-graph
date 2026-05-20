"""Generate deterministic reference documentation from code."""

from __future__ import annotations

import argparse
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

from repo_graph.api import RuntimeSettings, manifest_payload
from repo_graph.config import load_config
from repo_graph.scanner import build_graph

GENERATED_DIR = Path("docs/generated")
LOCAL_EXAMPLE_CONFIG = Path("config/local-example.yaml")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Repo Graph reference docs.")
    parser.add_argument("--check", action="store_true", help="Fail if generated docs are stale.")
    args = parser.parse_args()

    documents = generated_documents()
    if args.check:
        return check_documents(documents)

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in documents.items():
        path.write_text(content, encoding="utf-8")
    print(f"Generated {len(documents)} reference docs in {GENERATED_DIR}.")
    return 0


def generated_documents() -> dict[Path, str]:
    return {
        GENERATED_DIR / "api-endpoints.md": api_endpoints_doc(),
        GENERATED_DIR / "graph-types.md": graph_types_doc(),
        GENERATED_DIR / "pixi-tasks.md": pixi_tasks_doc(),
    }


def check_documents(documents: dict[Path, str]) -> int:
    stale: list[Path] = []
    for path, expected in documents.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale.append(path)

    if not stale:
        print(f"Generated docs check passed for {len(documents)} files.")
        return 0

    print("Generated docs are stale. Run `pixi run generate-docs`.")
    for path in stale:
        print(f"  - {path}")
    return 1


def api_endpoints_doc() -> str:
    manifest = manifest_payload(RuntimeSettings())
    endpoints = manifest["endpoints"]
    guidance = manifest["agent_guidance"]

    lines = [
        generated_header("API Endpoints"),
        "This file is generated from `repo_graph.api.manifest_payload`.",
        "",
        f"- Service: `{manifest['service']}`",
        f"- Runtime schema version: `{manifest['schema_version']}`",
        f"- Endpoint count: `{len(endpoints)}`",
        "",
        "## Endpoints",
        "",
        "| Method | Path | Status |",
        "| --- | --- | --- |",
    ]
    for endpoint in endpoints:
        status = "available" if endpoint["available"] else "planned"
        lines.append(f"| `{endpoint['method']}` | `{endpoint['path']}` | {status} |")

    lines.extend(
        [
            "",
            "## Agent Guidance Fields",
            "",
            "| Field | Value |",
            "| --- | --- |",
        ]
    )
    for key, value in sorted(guidance.items()):
        lines.append(f"| `{key}` | {format_markdown_value(value)} |")

    return "\n".join(lines) + "\n"


def graph_types_doc() -> str:
    graph = build_graph(load_config(LOCAL_EXAMPLE_CONFIG), strict=True)
    graph_data = graph.to_dict()
    entity_counts = graph_data["entity_counts"]
    edge_counts = graph_data["edge_counts"]
    parser_counts = Counter(edge["parser"] for edge in graph_data["edges"])
    confidence_counts = Counter(edge["confidence"] for edge in graph_data["edges"])

    lines = [
        generated_header("Graph Types"),
        "This file is generated from a strict scan of `config/local-example.yaml`.",
        "It documents the graph types exercised by the synthetic examples, not a private source set.",
        "",
        f"- Graph schema version: `{graph_data['metadata']['schema_version']}`",
        f"- Entity count: `{graph_data['summary']['entity_count']}`",
        f"- Edge count: `{graph_data['summary']['edge_count']}`",
        f"- Resolved edge count: `{graph_data['summary']['resolved_edge_count']}`",
        f"- Unresolved edge count: `{graph_data['summary']['unresolved_edge_count']}`",
        "",
        "## Entity Types",
        "",
        "| Entity Type | Example Count |",
        "| --- | ---: |",
    ]
    lines.extend(count_rows(entity_counts, "entity type"))
    lines.extend(
        [
            "",
            "## Edge Types",
            "",
            "| Edge Type | Example Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(count_rows(edge_counts, "edge type"))
    lines.extend(
        [
            "",
            "## Parsers",
            "",
            "| Parser | Example Edge Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(count_rows(parser_counts, "parser"))
    lines.extend(
        [
            "",
            "## Confidence Values",
            "",
            "| Confidence | Example Edge Count |",
            "| --- | ---: |",
        ]
    )
    lines.extend(count_rows(confidence_counts, "confidence value"))

    return "\n".join(lines) + "\n"


def pixi_tasks_doc() -> str:
    pixi = tomllib.loads(Path("pixi.toml").read_text(encoding="utf-8"))
    tasks = pixi["tasks"]

    lines = [
        generated_header("Pixi Tasks"),
        "This file is generated from `pixi.toml`.",
        "",
        f"- Task count: `{len(tasks)}`",
        "",
        "| Task | Definition |",
        "| --- | --- |",
    ]
    for name in sorted(tasks):
        lines.append(f"| `{name}` | {format_task(tasks[name])} |")

    return "\n".join(lines) + "\n"


def generated_header(title: str) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            "<!-- Generated by scripts/generate-docs.py. Do not edit by hand. -->",
        ]
    )


def count_rows(counts: Counter[str] | dict[str, int], label: str) -> list[str]:
    if not counts:
        return [f"| No {label}s found | 0 |"]
    return [f"| `{key}` | {counts[key]} |" for key in sorted(counts)]


def format_task(value: Any) -> str:
    if isinstance(value, str):
        return f"`{escape_markdown_cell(value)}`"
    if isinstance(value, dict):
        parts: list[str] = []
        if "cmd" in value:
            parts.append(f"cmd: `{escape_markdown_cell(str(value['cmd']))}`")
        if "depends-on" in value:
            depends = ", ".join(f"`{item}`" for item in value["depends-on"])
            parts.append(f"depends on: {depends}")
        return "<br>".join(parts)
    return f"`{escape_markdown_cell(str(value))}`"


def format_markdown_value(value: Any) -> str:
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    if isinstance(value, list):
        return ", ".join(f"`{escape_markdown_cell(str(item))}`" for item in value)
    return f"`{escape_markdown_cell(str(value))}`"


def escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
