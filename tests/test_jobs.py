"""Tests for in-memory job tracking."""

from __future__ import annotations

import unittest

from repo_graph.jobs import JobRegistry


class JobRegistryTests(unittest.TestCase):
    def test_inline_job_succeeds_with_result(self) -> None:
        registry = JobRegistry(run_inline=True)
        job = registry.submit("build", {"strict": True}, lambda: {"status": "built"})

        self.assertEqual(job["kind"], "build")
        self.assertEqual(job["status"], "succeeded")
        self.assertEqual(job["request"], {"strict": True})
        self.assertEqual(job["result"], {"status": "built"})
        self.assertIsNotNone(job["started_at"])
        self.assertIsNotNone(job["finished_at"])

    def test_inline_job_captures_failure(self) -> None:
        registry = JobRegistry(run_inline=True)

        def fail() -> dict[str, object]:
            raise RuntimeError("boom")

        job = registry.submit("build-load", {}, fail)

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"], {"type": "RuntimeError", "message": "boom"})

    def test_get_unknown_job_raises_key_error(self) -> None:
        registry = JobRegistry(run_inline=True)

        with self.assertRaises(KeyError):
            registry.get("missing")

    def test_list_jobs_filters_by_status_and_kind(self) -> None:
        registry = JobRegistry(run_inline=True)
        registry.submit("build", {}, lambda: {"status": "built"})
        registry.submit("build-load", {}, lambda: {"status": "built_and_loaded"})

        jobs = registry.list_jobs(status="succeeded", kind="build", limit=10)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "build")

    def test_list_jobs_rejects_invalid_limit(self) -> None:
        registry = JobRegistry(run_inline=True)

        with self.assertRaises(ValueError):
            registry.list_jobs(limit=0)


if __name__ == "__main__":
    unittest.main()
