"""Service, URL, and route naming helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from repo_graph.extraction.scanners.common import string_value

ENV_URL_RE = re.compile(r"(?:process\.env\.|import\.meta\.env\.)([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))")
ENV_NAME_RE = re.compile(r"\b([A-Z][A-Z0-9_]*(?:URL|URI|ENDPOINT|HOST))\b")


def extract_endpoint(raw_target: str) -> str:
    if raw_target.startswith("${"):
        after_base = raw_target.split("}", 1)[-1]
        if after_base.startswith("/"):
            return after_base
    if "}" in raw_target:
        after_template = raw_target.rsplit("}", 1)[-1]
        if after_template.startswith("/"):
            return after_template
    parsed = urlparse(raw_target)
    if parsed.path:
        return parsed.path
    if raw_target.startswith("/"):
        return raw_target
    return raw_target


def service_name_from_env(env_var: str) -> str:
    name = env_var.lower()
    for suffix in ("_base_url", "_api_url", "_url", "_uri", "_endpoint", "_host"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.replace("_", "-")


def url_value(value: object) -> str | None:
    raw_value = string_value(value)
    if not raw_value:
        return None
    parsed = urlparse(raw_value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw_value
    return None


def service_name_from_url(raw_target: str) -> str:
    host = urlparse(raw_target).hostname
    if not host:
        return "external-service"
    first_label = host.split(".", 1)[0]
    return service_name_from_identifier(first_label)


def service_name_from_identifier(value: object) -> str:
    raw_value = string_value(value) or "external-service"
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", raw_value)
    normalized = re.sub(r"(?:Base)?(?:Url|Uri|Endpoint|Host)$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", normalized).strip("-").lower()
    return normalized or "external-service"


def normalize_route_path(value: str) -> str:
    path = extract_endpoint(value)
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"\$\{[^}]+\}", ":param", path)
    path = re.sub(r"\{[^}]+\}", ":param", path)
    parts = []
    for part in path.split("/"):
        if not part:
            continue
        if part.startswith(":") or part.isdigit():
            parts.append(":param")
        else:
            parts.append(part)
    return "/" + "/".join(parts) if parts else "/"
