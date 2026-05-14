from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from repo_graph.config import load_config
from repo_graph.refresh import refresh_graph
from repo_graph.storage.neo4j import Neo4jSettings


class RefreshTests(unittest.TestCase):
    def test_refresh_writes_cached_graph_without_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            output_path = root / "graph.json"

            first = refresh_graph(config, output_path)
            second = refresh_graph(config, output_path)

            self.assertEqual(first["status"], "refreshed")
            self.assertEqual(first["changes"]["changed_count"], 2)
            self.assertEqual(first["load"]["action"], "not_requested")
            self.assertTrue(output_path.exists())
            self.assertEqual(second["changes"]["changed_count"], 0)
            self.assertEqual(second["cache"]["reused_count"], 2)

    def test_refresh_loads_full_graph_when_store_has_no_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            calls = LoaderCalls()

            result = refresh_graph(
                config,
                root / "graph.json",
                load=True,
                settings=fake_settings(),
                scope_reader=lambda _settings: {},
                graph_loader=calls.load,
            )

        self.assertEqual(result["load"]["action"], "full_load")
        self.assertEqual(result["load"]["reason"], "graph_not_loaded")
        self.assertTrue(calls.calls[0]["clear_existing"])
        self.assertIsNone(calls.calls[0]["replace_sources"])

    def test_refresh_replaces_only_changed_sources_when_scope_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            refresh_graph(config, root / "graph.json")
            calls = LoaderCalls()
            (root / "service" / "src" / "index.ts").write_text(
                'import { shared } from "@example/shared";\nexport const value = shared + "-changed";\n',
                encoding="utf-8",
            )

            result = refresh_graph(
                config,
                root / "graph.json",
                load=True,
                settings=fake_settings(),
                scope_reader=lambda _settings: loaded_scope(),
                graph_loader=calls.load,
            )

        self.assertEqual(result["changes"]["changed_sources"], ["service"])
        self.assertEqual(result["load"]["action"], "replace_sources")
        self.assertFalse(calls.calls[0]["clear_existing"])
        self.assertEqual(calls.calls[0]["replace_sources"], ["service"])

    def test_refresh_skips_load_when_scope_is_loaded_and_sources_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            refresh_graph(config, root / "graph.json")
            calls = LoaderCalls()

            result = refresh_graph(
                config,
                root / "graph.json",
                load=True,
                settings=fake_settings(),
                scope_reader=lambda _settings: loaded_scope(),
                graph_loader=calls.load,
            )

        self.assertEqual(result["load"]["action"], "skipped")
        self.assertEqual(result["load"]["reason"], "no_changed_sources")
        self.assertEqual(calls.calls, [])

    def test_refresh_full_loads_when_loaded_sources_do_not_match_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_workspace(root)
            config = load_config(write_config(root))
            refresh_graph(config, root / "graph.json")
            calls = LoaderCalls()

            result = refresh_graph(
                config,
                root / "graph.json",
                load=True,
                settings=fake_settings(),
                scope_reader=lambda _settings: {
                    "loaded": True,
                    "scope_name": "test-scope",
                    "sources": [{"name": "shared"}],
                },
                graph_loader=calls.load,
            )

        self.assertEqual(result["load"]["action"], "full_load")
        self.assertEqual(result["load"]["reason"], "loaded_sources_mismatch")
        self.assertTrue(calls.calls[0]["clear_existing"])


class FakeLoadSummary:
    def __init__(self, clear_existing: bool, replace_sources: list[str] | None) -> None:
        self.clear_existing = clear_existing
        self.replace_sources = replace_sources

    def to_dict(self) -> dict[str, Any]:
        return {
            "clear_existing": self.clear_existing,
            "replace_sources": self.replace_sources or [],
        }


class LoaderCalls:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def load(
        self,
        graph_path: Path,
        settings: Neo4jSettings,
        clear_existing: bool = True,
        replace_sources: list[str] | None = None,
    ) -> FakeLoadSummary:
        self.calls.append(
            {
                "graph_path": graph_path,
                "settings": settings,
                "clear_existing": clear_existing,
                "replace_sources": replace_sources,
            }
        )
        return FakeLoadSummary(clear_existing, replace_sources)


def fake_settings() -> Neo4jSettings:
    return Neo4jSettings(uri="bolt://example:7687", user="neo4j", password="password")


def loaded_scope() -> dict[str, Any]:
    return {
        "loaded": True,
        "scope_name": "test-scope",
        "sources": [{"name": "shared"}, {"name": "service"}],
    }


def write_workspace(root: Path) -> None:
    shared = root / "shared"
    shared.mkdir()
    (shared / "package.json").write_text('{"name": "@example/shared"}', encoding="utf-8")
    (shared / "index.ts").write_text("export const shared = 'shared';\n", encoding="utf-8")

    service = root / "service"
    (service / "src").mkdir(parents=True)
    (service / "package.json").write_text(
        '{"name": "@example/service", "dependencies": {"@example/shared": "1.0.0"}}',
        encoding="utf-8",
    )
    (service / "src" / "index.ts").write_text(
        'import { shared } from "@example/shared";\nexport const value = shared;\n',
        encoding="utf-8",
    )


def write_config(root: Path) -> Path:
    config_path = root / "sources.yaml"
    config_path.write_text(
        """
name: test-scope
output_dir: .repo-graph/output
sources:
  - type: local_path
    name: shared
    path: shared
  - type: local_path
    name: service
    path: service
""",
        encoding="utf-8",
    )
    return config_path


if __name__ == "__main__":
    unittest.main()
