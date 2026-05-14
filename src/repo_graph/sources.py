"""Source checkout and metadata helpers."""

from __future__ import annotations

import json
import os
import re
import subprocess
from base64 import b64encode
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

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
        "dependency_filter": {
            "package_include_patterns": list(config.dependency_filter.package_include_patterns),
            "package_exclude_patterns": list(config.dependency_filter.package_exclude_patterns),
            "include_relative_imports": config.dependency_filter.include_relative_imports,
        },
    }


def inspect_sources(config: RepoGraphConfig) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for source in config.sources:
        try:
            statuses.extend(source_status(config, expanded_source) for expanded_source in expand_one_source(source))
        except Exception as exc:
            statuses.append(source_expansion_failure_status(source, exc))
    return statuses


def sync_sources_with_status(config: RepoGraphConfig) -> list[dict[str, Any]]:
    config.cache_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict[str, Any]] = []
    for source in config.sources:
        try:
            expanded_sources = expand_one_source(source)
        except Exception as exc:
            status = source_expansion_failure_status(source, exc)
            status["sync"] = {"status": "failed", "error": str(exc)}
            statuses.append(status)
            continue
        for expanded_source in expanded_sources:
            try:
                sync_one_source(config, expanded_source)
            except Exception as exc:
                status = source_status(config, expanded_source)
                status["sync"] = {"status": "failed", "error": str(exc)}
                statuses.append(status)
                continue
            status = source_status(config, expanded_source)
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


def configured_source_payload(source: Source) -> dict[str, Any]:
    payload = {
        "path": str(source.path) if source.path is not None else None,
        "url": source.url,
        "ref": source.ref,
    }
    if source.source_type == "github_org":
        payload.update(
            {
                "org": source.org,
                "visibility": source.visibility,
                "include_archived": source.include_archived,
                "include_forks": source.include_forks,
                "include_name_patterns": list(source.include_name_patterns),
                "exclude_name_patterns": list(source.exclude_name_patterns),
                "limit": source.limit,
            }
        )
    return payload


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
    return resolve_expanded_sources(config, expand_sources(config.sources))


def resolve_expanded_sources(config: RepoGraphConfig, sources: list[Source]) -> list[ResolvedSource]:
    resolved: list[ResolvedSource] = []
    for source in sources:
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
    expanded_sources = expand_sources(config.sources)
    for source in expanded_sources:
        if source.source_type == "git":
            sync_git_source(config.cache_dir, source)
        elif source.source_type == "local_path":
            if source.path is None or not source.path.exists():
                raise FileNotFoundError(f"Local source path does not exist: {source.path}")
        else:
            raise ValueError(f"Unsupported source type: {source.source_type}")
    return resolve_expanded_sources(config, expanded_sources)


def expand_sources(sources: tuple[Source, ...] | list[Source]) -> list[Source]:
    expanded: list[Source] = []
    seen_names: set[str] = set()
    for source in sources:
        for expanded_source in expand_one_source(source):
            if expanded_source.name in seen_names:
                raise ValueError(f"Duplicate expanded source name: {expanded_source.name}")
            seen_names.add(expanded_source.name)
            expanded.append(expanded_source)
    return expanded


def expand_one_source(source: Source) -> list[Source]:
    if source.source_type == "github_org":
        return github_org_sources(source)
    return [source]


def source_expansion_failure_status(source: Source, exc: Exception) -> dict[str, Any]:
    return {
        "name": source.name,
        "type": source.source_type,
        "ref": source.ref,
        "configured": configured_source_payload(source),
        "resolved_path": None,
        "exists": False,
        "git_repo_present": False,
        "current_commit": None,
        "ready": False,
        "problems": ["source_expansion_failed"],
        "error": str(exc),
    }


def github_org_sources(source: Source) -> list[Source]:
    if not source.org:
        raise ValueError(f"GitHub org source '{source.name}' is missing an org.")
    repos = [
        repo for repo in github_org_repositories(source.org, source.visibility) if github_repo_selected(repo, source)
    ]
    if source.limit is not None:
        repos = repos[: source.limit]
    return [
        Source(
            name=github_repo_name(repo),
            source_type="git",
            url=github_repo_url(repo),
            ref=source.ref,
        )
        for repo in repos
    ]


def github_org_repositories(org: str, visibility: str) -> list[dict[str, Any]]:
    query = urlencode({"per_page": "100", "type": visibility})
    url = f"https://api.github.com/orgs/{quote(org, safe='')}/repos?{query}"
    return github_api_pages(url)


def github_api_pages(url: str) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    next_url: str | None = url
    while next_url:
        data, link_header = github_api_get(next_url)
        if not isinstance(data, list):
            raise RuntimeError("GitHub repositories response must be a JSON list.")
        repos.extend(repo for repo in data if isinstance(repo, dict))
        next_url = github_next_link(link_header)
    return repos


def github_api_get(url: str) -> tuple[Any, str | None]:
    request = Request(url, headers=github_api_headers())
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload), response.headers.get("Link")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="ignore").strip() or exc.reason
        raise RuntimeError(f"GitHub API request failed with HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub API returned invalid JSON: {exc}") from exc


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-graph",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_git_auth_header() -> str | None:
    token = github_token()
    if token is None:
        return None
    encoded = b64encode(f"x-access-token:{token}".encode()).decode("ascii")
    return f"AUTHORIZATION: basic {encoded}"


def github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token is None or not token.strip():
        return None
    return token.strip()


def github_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for item in link_header.split(","):
        url_part, _, rel_part = item.partition(";")
        if 'rel="next"' not in rel_part:
            continue
        url = url_part.strip()
        if url.startswith("<") and url.endswith(">"):
            return url[1:-1]
    return None


def github_repo_selected(repo: dict[str, Any], source: Source) -> bool:
    name = github_repo_name(repo)
    if not name:
        return False
    if bool(repo.get("archived")) and not source.include_archived:
        return False
    if bool(repo.get("fork")) and not (source.include_forks or source.visibility == "forks"):
        return False
    if source.include_name_patterns and not any(re.search(pattern, name) for pattern in source.include_name_patterns):
        return False
    return not (
        source.exclude_name_patterns and any(re.search(pattern, name) for pattern in source.exclude_name_patterns)
    )


def github_repo_name(repo: dict[str, Any]) -> str:
    name = repo.get("name")
    return name.strip() if isinstance(name, str) else ""


def github_repo_url(repo: dict[str, Any]) -> str:
    for key in ("clone_url", "ssh_url"):
        value = repo.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    html_url = repo.get("html_url")
    if isinstance(html_url, str) and html_url.strip():
        return html_url.rstrip("/") + ".git"
    raise ValueError(f"GitHub repository '{github_repo_name(repo)}' is missing a clone URL.")


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
