from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_graph.config import RepoGraphConfig, Source
from repo_graph.sources import (
    config_summary,
    get_default_branch,
    git_cache_path,
    inspect_sources,
    sync_git_source,
    sync_sources_with_status,
)


class SourceSyncTests(unittest.TestCase):
    def test_config_summary_describes_source_profile(self) -> None:
        root = Path("/repo")
        config = RepoGraphConfig(
            name="test",
            config_path=root / "repo-graph.yaml",
            cache_dir=root / ".repo-graph/cache/repos",
            output_dir=root / ".repo-graph/output",
            sources=(Source(name="service", source_type="local_path", path=root / "service"),),
        )

        payload = config_summary(config)

        self.assertEqual(payload["name"], "test")
        self.assertEqual(payload["config_path"], "/repo/repo-graph.yaml")
        self.assertEqual(payload["source_count"], 1)
        self.assertIn(".ts", payload["include"]["file_extensions"])

    def test_inspect_sources_reports_local_source_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "service"
            source_dir.mkdir()
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(
                    Source(name="service", source_type="local_path", path=source_dir),
                    Source(name="missing", source_type="local_path", path=root / "missing"),
                ),
            )

            payload = inspect_sources(config)

        self.assertEqual(len(payload), 2)
        self.assertTrue(payload[0]["exists"])
        self.assertTrue(payload[0]["ready"])
        self.assertFalse(payload[1]["exists"])
        self.assertFalse(payload[1]["ready"])
        self.assertIn("path_missing", payload[1]["problems"])

    def test_sync_sources_with_status_captures_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = RepoGraphConfig(
                name="test",
                config_path=root / "repo-graph.yaml",
                cache_dir=root / ".repo-graph/cache/repos",
                output_dir=root / ".repo-graph/output",
                sources=(Source(name="missing", source_type="local_path", path=root / "missing"),),
            )

            payload = sync_sources_with_status(config)

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["sync"]["status"], "failed")
        self.assertIn("Local source path does not exist", payload[0]["sync"]["error"])

    def test_git_cache_path_includes_url_identity(self) -> None:
        cache_dir = Path("/tmp/repo-graph-cache")
        source_a = Source(
            name="service",
            source_type="git",
            url="https://github.com/example/service-a.git",
        )
        source_b = Source(
            name="service",
            source_type="git",
            url="https://github.com/example/service-b.git",
        )

        self.assertNotEqual(git_cache_path(cache_dir, source_a), git_cache_path(cache_dir, source_b))

    def test_sync_git_source_rejects_mismatched_cached_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            source = Source(
                name="service",
                source_type="git",
                url="https://github.com/example/service.git",
            )
            cached_repo = git_cache_path(cache_dir, source)
            run(["git", "init", str(cached_repo)])
            run(["git", "remote", "add", "origin", "https://github.com/example/other.git"], cwd=cached_repo)

            with self.assertRaisesRegex(RuntimeError, "origin mismatch"):
                sync_git_source(cache_dir, source)

    def test_get_default_branch_recovers_missing_origin_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            work = root / "work"
            origin = root / "origin.git"
            clone = root / "clone"

            run(["git", "init", str(work)])
            run(["git", "checkout", "-b", "main"], cwd=work)
            run(["git", "config", "user.email", "test@example.com"], cwd=work)
            run(["git", "config", "user.name", "Test User"], cwd=work)
            (work / "README.md").write_text("# Test\n", encoding="utf-8")
            run(["git", "add", "README.md"], cwd=work)
            run(["git", "commit", "-m", "initial"], cwd=work)
            run(["git", "init", "--bare", str(origin)])
            run(["git", "remote", "add", "origin", str(origin)], cwd=work)
            run(["git", "push", "-u", "origin", "main"], cwd=work)
            run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=origin)
            run(["git", "clone", str(origin), str(clone)])
            run(["git", "symbolic-ref", "--delete", "refs/remotes/origin/HEAD"], cwd=clone)

            self.assertEqual(get_default_branch(clone), "main")


def run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
