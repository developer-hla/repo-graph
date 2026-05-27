"""Git checkout and command helpers."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from repo_graph.config import Source
from repo_graph.sources._github import github_git_auth_header, github_token
from repo_graph.sources._paths import git_cache_path


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


def git_repo_present(path: Path | None) -> bool:
    return path is not None and (path / ".git").exists()


def git_commit(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        return run_git(["rev-parse", "HEAD"], cwd=path).strip()
    except RuntimeError:
        return None


def git_origin_url(repo_path: Path) -> str:
    return run_git(["remote", "get-url", "origin"], cwd=repo_path).strip()


def safe_git_origin_url(path: Path) -> str | None:
    try:
        return git_origin_url(path)
    except RuntimeError:
        return None


def run_git(args: list[str], cwd: Path | None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env=git_command_env(),
    )
    if result.returncode != 0:
        message = redact_github_token(result.stderr.strip() or result.stdout.strip())
        raise RuntimeError("git {} failed: {}".format(" ".join(args), message))
    return result.stdout + result.stderr


def git_command_env() -> dict[str, str] | None:
    token = github_token()
    if token is None:
        return None

    env = os.environ.copy()
    header = github_git_auth_header()
    if header is None:
        return None
    config_index = next_git_config_index(env)
    env[f"GIT_CONFIG_KEY_{config_index}"] = "http.https://github.com/.extraheader"
    env[f"GIT_CONFIG_VALUE_{config_index}"] = header
    env["GIT_CONFIG_COUNT"] = str(config_index + 1)
    return env


def next_git_config_index(env: dict[str, str]) -> int:
    try:
        value = int(env.get("GIT_CONFIG_COUNT", "0") or "0")
    except ValueError:
        return 0
    return max(value, 0)


def redact_github_token(message: str) -> str:
    token = github_token()
    if token is None:
        return message
    redacted = message.replace(token, "[redacted]")
    auth_header = github_git_auth_header()
    if auth_header is not None:
        redacted = redacted.replace(auth_header, "AUTHORIZATION: [redacted]")
    return redacted
