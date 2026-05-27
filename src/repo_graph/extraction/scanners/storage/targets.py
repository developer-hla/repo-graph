"""Storage target extraction."""

from __future__ import annotations

from urllib.parse import urlparse

from repo_graph.extraction.scanners.storage.models import StorageTarget
from repo_graph.extraction.scanners.storage.patterns import STORAGE_FIRST_ARG_RE, STORAGE_KEY_VALUE_RE


def storage_target_for_line(line: str) -> StorageTarget | None:
    values: dict[str, str] = {}
    for match in STORAGE_KEY_VALUE_RE.finditer(line):
        values[match.group("key").lower()] = match.group("value")
    if values:
        return storage_target_from_parts(values)
    first_arg = STORAGE_FIRST_ARG_RE.search(line)
    if first_arg:
        return storage_target(first_arg.group("value"), storage_kind="path", target_key="first_arg")
    return None


def storage_target_from_parts(values: dict[str, str]) -> StorageTarget | None:
    bucket = first_value(values, "bucket", "bucketname")
    container = first_value(values, "container", "containername", "share")
    object_key = first_value(values, "key", "blobname", "path", "filepath")
    if bucket and object_key:
        return storage_target(f"{bucket}/{object_key}", "bucket_object", bucket=bucket, object_key=object_key)
    if container and object_key:
        return storage_target(
            f"{container}/{object_key}",
            "container_object",
            container=container,
            object_key=object_key,
        )
    raw_target = object_key or bucket or container
    if not raw_target:
        return None
    return storage_target(raw_target, "path", bucket=bucket, container=container, object_key=object_key)


def first_value(values: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


def storage_target(
    value: str,
    storage_kind: str,
    bucket: str | None = None,
    container: str | None = None,
    object_key: str | None = None,
    target_key: str | None = None,
) -> StorageTarget:
    normalized = normalize_storage_target(value)
    return StorageTarget(
        name=normalized,
        raw_target=value,
        storage_kind=storage_kind,
        bucket=bucket,
        container=container,
        object_key=object_key,
        target_key=target_key,
    )


def normalize_storage_target(value: str) -> str:
    raw = value.strip().strip("\"'")
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
        return f"{parsed.netloc}/{path}" if path else parsed.netloc
    return raw.replace("\\", "/")
