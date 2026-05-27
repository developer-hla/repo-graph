"""GitHub organization expansion and authentication helpers."""

from __future__ import annotations

import json
import os
import re
from base64 import b64encode
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from repo_graph.config import Source


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
