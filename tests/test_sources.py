from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from repo_graph.config import Source
from repo_graph.sources import get_default_branch, git_cache_path, sync_git_source


class SourceSyncTests(unittest.TestCase):
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
