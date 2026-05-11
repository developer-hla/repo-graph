"""Source checkout and metadata helpers."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from repo_graph.config import RepoGraphConfig, Source


@dataclass(frozen=True)
class ResolvedSource:
    name: str
    source_type: str
    path: Path
    url: str | None
    ref: str
    commit: str | None


def config_summary(config: RepoGraphConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "config_path": str(config.config_path),
        "cache_dir": str(config.cache_dir),
        "output_dir": str(config.output_dir),
        "source_count": len(config.sources),
        "include": {"file_extensions": sorted(config.include.file_extensions)},
        "exclude": {
            "directories": sorted(config.exclude.directories),
            "files": sorted(config.exclude.files),
        },
    }


def inspect_sources(config: RepoGraphConfig) -> list[dict[str, Any]]:
    return [source_status(config, source) for source in config.sources]


def sync_sources_with_status(config: RepoGraphConfig) -> list[dict[str, Any]]:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    for source in config.sources:
        try:
            sync_one_source(config, source)
        except Exception as exc:
            status = source_status(config, source)
            status["sync"] = {"status": "failed", "error": str(exc)}
            statuses.append(status)
            continue
        status = source_status(config, source)
        status["sync"] = {"status": "succeeded"}
        statuses.append(status)
    return statuses


def sync_one_source(config: RepoGraphConfig, source: Source) -> None:
    if source.source_type == "git":
        sync_git_source(config.cache_dir, source)
        return
    if source.source_type == "local_path":
        if source.path is None or not source.path.exists():
            raise FileNotFoundError(f"Local source path does not exist: {source.path}")
        return
    raise ValueError(f"Unsupported source type: {source.source_type}")


def source_status(config: RepoGraphConfig, source: Source) -> dict[str, Any]:
    path = source_path(config, source)
    status: dict[str, Any] = {
        "name": source.name,
        "type": source.source_type,
        "ref": source.ref,
        "configured": configured_source_payload(source),
        "resolved_path": str(path) if path is not None else None,
        "exists": path.exists() if path is not None else False,
        "git_repo_present": git_repo_present(path),
        "current_commit": git_commit(path) if path is not None else None,
    }
    if source.url is not None:
        status["url"] = source.url
    if path is not None and git_repo_present(path):
        status["origin_url"] = safe_git_origin_url(path)
    status["ready"] = source_ready(status, source)
    status["problems"] = source_problems(status, source)
    return status


def configured_source_payload(source: Source) -> dict[str, str | None]:
    return {
        "path": str(source.path) if source.path is not None else None,
        "url": source.url,
        "ref": source.ref,
    }


def source_path(config: RepoGraphConfig, source: Source) -> Path | None:
    if source.source_type == "local_path":
        return source.path
    if source.source_type == "git":
        return git_cache_path(config.cache_dir, source)
    return None


def git_repo_present(path: Path | None) -> bool:
    return path is not None and (path / ".git").exists()


def safe_git_origin_url(path: Path) -> str | None:
    try:
        return git_origin_url(path)
    except RuntimeError:
        return None


def source_ready(status: dict[str, Any], source: Source) -> bool:
    if source.source_type == "local_path":
        return bool(status["exists"])
    if source.source_type == "git":
        return bool(status["exists"] and status["git_repo_present"] and status.get("current_commit"))
    return False


def source_problems(status: dict[str, Any], source: Source) -> list[str]:
    problems: list[str] = []
    if not status["exists"]:
        problems.append("path_missing")
    if source.source_type == "git":
        if status["exists"] and not status["git_repo_present"]:
            problems.append("path_exists_but_not_git_repo")
        if source.url and status.get("origin_url") and status["origin_url"] != source.url:
            problems.append("origin_url_mismatch")
        if not status.get("current_commit"):
            problems.append("commit_unknown")
    return problems


def resolve_sources(config: RepoGraphConfig) -> list[ResolvedSource]:
    resolved: list[ResolvedSource] = []
    for source in config.sources:
        if source.source_type == "local_path":
            if source.path is None:
                raise ValueError(f"Local source '{source.name}' is missing a path.")
            resolved.append(
                ResolvedSource(
                    name=source.name,
                    source_type=source.source_type,
                    path=source.path,
                    url=None,
                    ref=source.ref,
                    commit=git_commit(source.path),
                )
            )
        elif source.source_type == "git":
            path = git_cache_path(config.cache_dir, source)
            resolved.append(
                ResolvedSource(
                    name=source.name,
                    source_type=source.source_type,
                    path=path,
                    url=source.url,
                    ref=source.ref,
                    commit=git_commit(path),
                )
            )
        else:
            raise ValueError(f"Unsupported source type: {source.source_type}")
    return resolved


def sync_sources(config: RepoGraphConfig) -> list[ResolvedSource]:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    for source in config.sources:
        if source.source_type == "git":
            sync_git_source(config.cache_dir, source)
        elif source.source_type == "local_path":
            if source.path is None or not source.path.exists():
                raise FileNotFoundError(f"Local source path does not exist: {source.path}")
        else:
            raise ValueError(f"Unsupported source type: {source.source_type}")
    return resolve_sources(config)


def sync_git_source(cache_dir: Path, source: Source) -> Path:
    if source.url is None:
        raise ValueError(f"Git source '{source.name}' is missing a URL.")

    repo_path = git_cache_path(cache_dir, source)
    if not repo_path.exists():
        run_git(["clone", source.url, str(repo_path)], cwd=None)
    else:
        if not (repo_path / ".git").exists():
            raise RuntimeError(f"Git cache path exists but is not a repository: {repo_path}")
        origin_url = git_origin_url(repo_path)
        if origin_url != source.url:
            raise RuntimeError(
                f"Git cache origin mismatch for source '{source.name}': expected {source.url}, found {origin_url}"
            )
        run_git(["fetch", "origin", "--prune"], cwd=repo_path)

    checkout_ref(repo_path, source.ref)
    return repo_path


def checkout_ref(repo_path: Path, ref: str) -> None:
    if ref == "default":
        default_branch = get_default_branch(repo_path)
        checkout_branch(repo_path, default_branch)
        run_git(["merge", "--ff-only", f"origin/{default_branch}"], cwd=repo_path)
        return

    if git_ref_exists(repo_path, f"refs/remotes/origin/{ref}"):
        checkout_branch(repo_path, ref)
        run_git(["merge", "--ff-only", f"origin/{ref}"], cwd=repo_path)
        return

    run_git(["checkout", ref], cwd=repo_path)


def get_default_branch(repo_path: Path) -> str:
    branch = git_symbolic_ref(repo_path, "refs/remotes/origin/HEAD")
    if branch and branch.startswith("origin/"):
        return branch.removeprefix("origin/")

    remote_output = run_git(["remote", "set-head", "origin", "--auto"], cwd=repo_path)
    branch = git_symbolic_ref(repo_path, "refs/remotes/origin/HEAD")
    if branch and branch.startswith("origin/"):
        return branch.removeprefix("origin/")

    match = re.search(r"origin/HEAD set to (.+)", remote_output)
    if match:
        return match.group(1).strip()

    raise RuntimeError(f"Could not determine default branch for {repo_path}")


def checkout_branch(repo_path: Path, branch: str) -> None:
    if git_ref_exists(repo_path, f"refs/heads/{branch}"):
        run_git(["checkout", branch], cwd=repo_path)
        return
    if git_ref_exists(repo_path, f"refs/remotes/origin/{branch}"):
        run_git(["checkout", "--track", f"origin/{branch}"], cwd=repo_path)
        return
    run_git(["checkout", branch], cwd=repo_path)


def git_symbolic_ref(repo_path: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", ref],
        cwd=repo_path,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def git_ref_exists(repo_path: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        cwd=repo_path,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def git_commit(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        return run_git(["rev-parse", "HEAD"], cwd=path).strip()
    except RuntimeError:
        return None


def git_cache_path(cache_dir: Path, source: Source) -> Path:
    if source.source_type == "git" and source.url:
        url_hash = sha256(source.url.encode("utf-8")).hexdigest()[:10]
        return cache_dir / (f"{safe_path_name(source.name)}-{url_hash}")
    return cache_dir / safe_path_name(source.name)


def git_origin_url(repo_path: Path) -> str:
    return run_git(["remote", "get-url", "origin"], cwd=repo_path).strip()


def safe_path_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return safe.strip("-") or "repo"


def run_git(args: list[str], cwd: Path | None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError("git {} failed: {}".format(" ".join(args), message))
    return result.stdout + result.stderr
