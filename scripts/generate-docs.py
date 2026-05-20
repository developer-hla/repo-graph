"""Generate deterministic reference documentation from code."""

from __future__ import annotations

import argparse
import tomllib
from collections import Counter
from dataclasses import MISSING, Field, fields
from pathlib import Path
from typing import Any

from repo_graph.api import RuntimeSettings, create_app, manifest_payload
from repo_graph.cli import build_parser
from repo_graph.config import (
    DEFAULT_CACHE_DIR,
    DEFAULT_EXCLUDED_DIRECTORIES,
    DEFAULT_FILE_EXTENSIONS,
    DEFAULT_OUTPUT_DIR,
    GITHUB_ORG_VISIBILITIES,
    DependencyFilter,
    ExcludeRules,
    IncludeRules,
    Source,
    load_config,
)
from repo_graph.scanner import build_graph

GENERATED_DIR = Path("docs/generated")
LOCAL_EXAMPLE_CONFIG = Path("config/local-example.yaml")


class GeneratedHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=120)


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
        GENERATED_DIR / "cli-reference.md": cli_reference_doc(),
        GENERATED_DIR / "config-reference.md": config_reference_doc(),
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
    openapi = create_app(RuntimeSettings()).openapi()

    lines = [
        generated_header("API Endpoints"),
        "This file is generated from `repo_graph.api.manifest_payload` and the FastAPI OpenAPI schema.",
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

    lines.extend(openapi_route_details(openapi))
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


def openapi_route_details(openapi: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## FastAPI Route Details",
        "",
        "Routes marked `planned` in the manifest are omitted until they exist in the FastAPI app.",
        "",
        "| Method | Path | Path Parameters | Query Parameters | Request Body |",
        "| --- | --- | --- | --- | --- |",
    ]
    for path in sorted(openapi["paths"]):
        operations = openapi["paths"][path]
        for method in sorted(operations):
            operation = operations[method]
            parameters = operation.get("parameters", [])
            lines.append(
                "| "
                f"`{method.upper()}` | "
                f"`{path}` | "
                f"{format_openapi_parameters(parameters, 'path')} | "
                f"{format_openapi_parameters(parameters, 'query')} | "
                f"{format_openapi_request_body(operation)} |"
            )
    return lines


def format_openapi_parameters(parameters: list[dict[str, Any]], location: str) -> str:
    values: list[str] = []
    for parameter in parameters:
        if parameter.get("in") != location:
            continue
        schema = parameter.get("schema", {})
        values.append(
            "`"
            + escape_markdown_cell(parameter["name"])
            + "` "
            + format_openapi_schema(schema)
            + format_openapi_required(parameter)
        )
    return "<br>".join(values) if values else ""


def format_openapi_required(parameter: dict[str, Any]) -> str:
    return " required" if parameter.get("required") else ""


def format_openapi_request_body(operation: dict[str, Any]) -> str:
    request_body = operation.get("requestBody")
    if not request_body:
        return ""
    content = request_body.get("content", {})
    schema = content.get("application/json", {}).get("schema", {})
    body = format_openapi_schema(schema)
    if request_body.get("required"):
        return f"{body} required"
    return body


def format_openapi_schema(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return f"`{schema['$ref'].rsplit('/', 1)[-1]}`"
    if "anyOf" in schema:
        return " or ".join(format_openapi_schema(item) for item in schema["anyOf"])

    schema_type = schema.get("type", "value")
    parts = [f"`{schema_type}`"]
    if "default" in schema:
        parts.append(f"default `{escape_markdown_cell(str(schema['default']))}`")
    if "minimum" in schema or "maximum" in schema:
        bounds: list[str] = []
        if "minimum" in schema:
            bounds.append(f"min `{schema['minimum']}`")
        if "maximum" in schema:
            bounds.append(f"max `{schema['maximum']}`")
        parts.append(", ".join(bounds))
    if "minLength" in schema:
        parts.append(f"min length `{schema['minLength']}`")
    return " ".join(parts)


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


def cli_reference_doc() -> str:
    parser = build_parser()
    normalize_cli_progs(parser, "repo-graph")
    commands = list(command_docs(parser))

    lines = [
        generated_header("CLI Reference"),
        "This file is generated from `repo_graph.cli.build_parser`.",
        "",
        "## Root Usage",
        "",
        "```text",
        format_usage(parser),
        "```",
        "",
        "## Command Tree",
        "",
        "| Command | Help |",
        "| --- | --- |",
    ]
    for command_path, _, help_text in commands:
        lines.append(f"| `{command_path}` | {escape_markdown_cell(help_text)} |")

    for command_path, command_parser, help_text in commands:
        lines.extend(command_section(command_path, command_parser, help_text))

    return "\n".join(lines) + "\n"


def config_reference_doc() -> str:
    lines = [
        generated_header("Config Reference"),
        "This file is generated from `repo_graph.config` defaults and dataclass fields.",
        "",
        "## Top-Level Fields",
        "",
        "| Field | Required | Default | Description |",
        "| --- | --- | --- | --- |",
        "| `name` | yes |  | Non-empty graph scope name. |",
        f"| `cache_dir` | no | `{DEFAULT_CACHE_DIR}` | Directory for cloned Git sources. "
        "Relative paths resolve from the config file directory. |",
        f"| `output_dir` | no | `{DEFAULT_OUTPUT_DIR}` | Directory for generated graph output. "
        "Relative paths resolve from the config file directory. |",
        "| `sources` | no | `[]` | Source definitions to scan. |",
        "| `include` | no | built-in defaults | Include rules for scannable files. |",
        "| `exclude` | no | built-in defaults | Exclude rules for directories and files. |",
        "| `dependency_filter` | no | built-in defaults | Package/import filtering applied after graph resolution. |",
        "",
        "## Source Types",
        "",
        "| Type | Required Fields | Optional Fields | Description |",
        "| --- | --- | --- | --- |",
        "| `local_path` | `type`, `name`, `path` | `ref` | Scan a repository already present on disk. "
        "Relative `path` values resolve from the config file directory. |",
        "| `git` | `type`, `name`, `url` | `ref` | Clone or update one explicit Git repository into `cache_dir`. |",
        "| `github_org` | `type`, `name`, `org` | `ref`, `visibility`, `include`, `exclude`, `limit` | "
        "Expand repositories from a GitHub organization through the GitHub REST API. |",
        "",
        "## Source Dataclass Fields",
        "",
        "YAML source `type` values are loaded into the `source_type` field.",
        "",
        *dataclass_field_table(Source),
        "",
        "## GitHub Organization Source",
        "",
        f"- Supported `visibility` values: {format_inline_values(sorted(GITHUB_ORG_VISIBILITIES))}",
        "- `include.archived` defaults to `false`.",
        "- `include.forks` defaults to `false`.",
        "- `include.name_patterns` and `exclude.name_patterns` are regular expression lists matched against "
        "repository names.",
        "- `limit` must be a positive integer when set.",
        "",
        "## Include Rules",
        "",
        *dataclass_field_table(IncludeRules),
        "",
        "Default file extensions:",
        "",
        *bullet_values(sorted(DEFAULT_FILE_EXTENSIONS)),
        "",
        "## Exclude Rules",
        "",
        *dataclass_field_table(ExcludeRules),
        "",
        "Default excluded directories:",
        "",
        *bullet_values(sorted(DEFAULT_EXCLUDED_DIRECTORIES)),
        "",
        "## Dependency Filter",
        "",
        *dataclass_field_table(DependencyFilter),
        "",
        "- `package_include_patterns` and `package_exclude_patterns` must be valid regular expressions.",
        "- Resolved package/import edges are retained because they point to sources in the graph.",
        "- Unresolved package references are retained only when they match include patterns, unless no include "
        "patterns are configured.",
        "- `include_relative_imports` controls unresolved relative import edges.",
    ]
    return "\n".join(lines) + "\n"


def dataclass_field_table(model: type[Any]) -> list[str]:
    lines = [
        "| Field | Type | Default |",
        "| --- | --- | --- |",
    ]
    for field in fields(model):
        lines.append(f"| `{field.name}` | `{format_field_type(field)}` | {format_field_default(field)} |")
    return lines


def format_field_type(field: Field[Any]) -> str:
    return str(field.type).replace("typing.", "")


def format_field_default(field: Field[Any]) -> str:
    if field.default is not MISSING:
        if isinstance(field.default, bool):
            return f"`{str(field.default).lower()}`"
        return f"`{escape_markdown_cell(str(field.default))}`"
    if field.default_factory is not MISSING:
        value = field.default_factory()
        if isinstance(value, set | tuple | list):
            values = sorted(str(item) for item in value)
            if not values:
                return "`empty`"
            return format_inline_values(values)
        if isinstance(value, bool):
            return f"`{str(value).lower()}`"
        return f"`{escape_markdown_cell(str(value))}`"
    return ""


def format_inline_values(values: list[str]) -> str:
    return ", ".join(f"`{escape_markdown_cell(value)}`" for value in values)


def bullet_values(values: list[str]) -> list[str]:
    return [f"- `{escape_markdown_cell(value)}`" for value in values]


def normalize_cli_progs(parser: argparse.ArgumentParser, prog: str) -> None:
    parser.prog = prog
    parser.formatter_class = GeneratedHelpFormatter
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                normalize_cli_progs(child, f"{prog} {name}")


def command_docs(
    parser: argparse.ArgumentParser,
) -> list[tuple[str, argparse.ArgumentParser, str]]:
    docs: list[tuple[str, argparse.ArgumentParser, str]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            help_by_name = {choice.dest: choice.help or "" for choice in action._choices_actions}
            for name, child in action.choices.items():
                docs.append((child.prog, child, help_by_name.get(name, "")))
                docs.extend(command_docs(child))
    return docs


def command_section(command_path: str, parser: argparse.ArgumentParser, help_text: str) -> list[str]:
    lines = [
        "",
        f"## `{command_path}`",
        "",
    ]
    if help_text:
        lines.extend([help_text, ""])
    lines.extend(
        [
            "```text",
            format_usage(parser),
            "```",
        ]
    )

    options = [action for action in parser._actions if include_cli_option(action)]
    if options:
        lines.extend(
            [
                "",
                "| Option | Required | Default | Help |",
                "| --- | --- | --- | --- |",
            ]
        )
        for option in options:
            lines.append(
                "| "
                f"{format_cli_option_names(option)} | "
                f"{format_required(option)} | "
                f"{format_default(option)} | "
                f"{format_cli_help(option)} |"
            )

    subcommands = subcommand_rows(parser)
    if subcommands:
        lines.extend(
            [
                "",
                "| Subcommand | Help |",
                "| --- | --- |",
            ]
        )
        for name, help_text in subcommands:
            lines.append(f"| `{name}` | {escape_markdown_cell(help_text)} |")

    return lines


def include_cli_option(action: argparse.Action) -> bool:
    return bool(action.option_strings) and not isinstance(action, argparse._HelpAction)


def subcommand_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return [(choice.dest, choice.help or "") for choice in action._choices_actions]
    return []


def format_usage(parser: argparse.ArgumentParser) -> str:
    return parser.format_usage().replace("usage: ", "", 1).strip()


def format_cli_option_names(action: argparse.Action) -> str:
    return ", ".join(f"`{name}`" for name in action.option_strings)


def format_required(action: argparse.Action) -> str:
    return "yes" if getattr(action, "required", False) else "no"


def format_default(action: argparse.Action) -> str:
    default = getattr(action, "default", None)
    if default is None or default == argparse.SUPPRESS:
        return ""
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    return f"`{escape_markdown_cell(str(default))}`"


def format_cli_help(action: argparse.Action) -> str:
    return escape_markdown_cell(action.help or "")


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
