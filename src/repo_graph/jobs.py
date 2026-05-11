"""In-memory job tracking for local Repo Graph runtimes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any
from uuid import uuid4

JobTask = Callable[[], dict[str, Any]]


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str
    created_at: str
    request: dict[str, Any]
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "request": self.request,
            "result": self.result,
            "error": self.error,
        }


class JobRegistry:
    def __init__(self, max_workers: int = 1, run_inline: bool = False) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = RLock()
        self._run_inline = run_inline
        self._executor = (
            None if run_inline else ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="repo-graph")
        )

    def submit(self, kind: str, request: Mapping[str, Any], task: JobTask) -> dict[str, Any]:
        job_id = uuid4().hex
        job = JobRecord(
            job_id=job_id,
            kind=kind,
            status="queued",
            created_at=utc_now(),
            request=dict(request),
        )
        with self._lock:
            self._jobs[job_id] = job

        if self._run_inline:
            self._run_job(job_id, task)
        elif self._executor is not None:
            self._executor.submit(self._run_job, job_id, task)
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return job.to_dict()

    def list_jobs(
        self,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("Limit must be at least 1.")
        if limit > 200:
            raise ValueError("Limit must be at most 200.")

        with self._lock:
            jobs = [job for job in self._jobs.values() if matches_job(job, status=status, kind=kind)]
            jobs.sort(key=lambda job: job.created_at, reverse=True)
            return [job.to_dict() for job in jobs[:limit]]

    def _run_job(self, job_id: str, task: JobTask) -> None:
        self._update(job_id, status="running", started_at=utc_now())
        try:
            result = task()
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                finished_at=utc_now(),
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
            return
        self._update(job_id, status="succeeded", finished_at=utc_now(), result=result)

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)


def matches_job(job: JobRecord, status: str | None, kind: str | None) -> bool:
    if status is not None and job.status != status:
        return False
    return not (kind is not None and job.kind != kind)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
