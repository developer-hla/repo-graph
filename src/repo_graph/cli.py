"""Command line entrypoint for RepoGraph."""

from __future__ import annotations

from repo_graph.cli_runtime.parser import build_parser
from repo_graph.cli_runtime.runtime import agent_instructions_markdown


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


__all__ = [
    "agent_instructions_markdown",
    "build_parser",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
