from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from repo_graph.cli import agent_instructions_markdown, build_parser


class CliTests(unittest.TestCase):
    def test_agent_instructions_markdown_points_to_manifest(self) -> None:
        markdown = agent_instructions_markdown("http://repo-graph:8000", Path("repo-graph.yaml"))

        self.assertIn("## Repo Graph", markdown)
        self.assertIn("`http://repo-graph:8000/manifest`", markdown)
        self.assertIn("`repo-graph.yaml`", markdown)
        self.assertIn("runtime manifest as the source of truth", markdown)
        self.assertIn("do not treat them as unused code by default", markdown)

    def test_agent_instructions_command_prints_markdown(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "agent-instructions",
                "--api-url",
                "http://repo-graph:8000",
                "--config",
                "repo-graph.yaml",
            ]
        )
        output = io.StringIO()

        with redirect_stdout(output):
            result = args.func(args)

        self.assertEqual(result, 0)
        self.assertIn("http://repo-graph:8000/sources/configured", output.getvalue())


if __name__ == "__main__":
    unittest.main()
