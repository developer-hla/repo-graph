"""Source checkout and metadata helpers."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from repo_graph.config import RepoGraphConfig, Source


@dataclass(frozen=True)
class ResolvedSource:
    name: str
    source_type: str
    path: Path
    url: str | None
    ref: str
    commit: str | None


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
