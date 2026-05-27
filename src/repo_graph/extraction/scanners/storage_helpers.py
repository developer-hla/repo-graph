"""Shared storage interaction helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_reference, unresolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.sql.properties import source_context_properties

STORAGE_NAME_RE = r"[A-Za-z_][\w.]*"
STORAGE_METHOD_RE = re.compile(
    rf"(?:(?P<receiver>{STORAGE_NAME_RE})\s*\.\s*)?"
    r"(?P<method>readFileSync|writeFileSync|createReadStream|createWriteStream|ReadAllText|"
    r"ReadAllBytes|WriteAllText|WriteAllBytes|OpenRead|OpenWrite|DownloadAsync|UploadAsync|"
    r"downloadToFile|uploadFromFile|getObject|putObject|get_object|put_object|readFile|writeFile|"
    r"appendFile|download|upload)\s*\(",
    re.IGNORECASE,
)
STORAGE_KEY_VALUE_RE = re.compile(
    r"(?P<key>Bucket|bucket|bucketName|Container|container|containerName|Share|share|Key|key|BlobName|"
    r"blobName|Path|path|FilePath|filePath)"
    r"\s*[:=]\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)
STORAGE_FIRST_ARG_RE = re.compile(
    r"\(\s*(?P<prefix>\$@|@\$|\$|@)?(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
    re.IGNORECASE,
)

READ_METHODS = frozenset(
    {
        "createreadstream",
        "download",
        "downloadasync",
        "downloadtofile",
        "get_object",
        "getobject",
        "openread",
        "readallbytes",
        "readalltext",
        "readfile",
        "readfilesync",
    }
)
WRITE_METHODS = frozenset(
    {
        "appendfile",
        "createwritestream",
        "openwrite",
        "put_object",
        "putobject",
        "upload",
        "uploadasync",
        "uploadfromfile",
        "writeallbytes",
        "writealltext",
        "writefile",
        "writefilesync",
    }
)
BROAD_STORAGE_METHODS = frozenset({"appendfile", "download", "readfile", "upload", "writefile"})
RECEIVER_HINTS = (
    "blob",
    "bucket",
    "container",
    "directory",
    "file",
    "fs",
    "ftp",
    "path",
    "s3",
    "share",
    "storage",
)


@dataclass(frozen=True)
class StorageTarget:
    name: str
    raw_target: str
    storage_kind: str
    bucket: str | None = None
    container: str | None = None
    object_key: str | None = None
    target_key: str | None = None


@dataclass(frozen=True)
class StorageOperation:
    action: str
    method: str
    receiver: str | None = None

    @property
    def edge_type(self) -> str:
        if self.action == "read":
            return "READS_STORAGE_OBJECT"
        return "WRITES_STORAGE_OBJECT"

    @property
    def interaction_kind(self) -> str:
        return f"storage_{self.action}"


def storage_facts_for_line(
    context: FileScanContext,
    line: str,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for operation in storage_operations_for_line(line):
        target = storage_target_for_line(line)
        if target:
            facts.append(storage_relationship_fact(context, operation, target, line_number, parser, from_entity))
    return facts


def storage_operations_for_line(line: str) -> list[StorageOperation]:
    operations: list[StorageOperation] = []
    for match in STORAGE_METHOD_RE.finditer(line):
        operation = storage_operation(match.group("method"), receiver=match.group("receiver"))
        if operation:
            operations.append(operation)
    return operations


def storage_operation(method: str | None, receiver: str | None = None) -> StorageOperation | None:
    if not method:
        return None
    normalized_method = method.lower()
    if normalized_method in READ_METHODS:
        action = "read"
    elif normalized_method in WRITE_METHODS:
        action = "write"
    else:
        return None
    if not storage_receiver_is_likely(receiver) and normalized_method not in specific_storage_methods():
        return None
    return StorageOperation(action, normalized_method, receiver=receiver)


def storage_receiver_is_likely(receiver: str | None) -> bool:
    if not receiver:
        return False
    normalized = receiver.lower()
    return any(hint in normalized for hint in RECEIVER_HINTS)


def specific_storage_methods() -> frozenset[str]:
    return (READ_METHODS | WRITE_METHODS) - BROAD_STORAGE_METHODS


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


def storage_relationship_fact(
    context: FileScanContext,
    operation: StorageOperation,
    target: StorageTarget,
    line_number: int,
    parser: str,
    from_entity: EntityFact | None = None,
    extra_properties: dict[str, Any] | None = None,
) -> RelationshipFact:
    properties = interaction_properties(
        "storage",
        "runtime",
        operation.interaction_kind,
        raw_target=target.raw_target,
        normalized_target=target.name,
        storage_kind=target.storage_kind,
        storage_operation=operation.action,
        storage_method=operation.method,
        storage_receiver=operation.receiver,
        bucket=target.bucket,
        container=target.container,
        object_key=target.object_key,
        target_key=target.target_key,
    )
    properties.update(source_context_properties(from_entity))
    if extra_properties:
        properties.update(extra_properties)
    return unresolved_relationship_fact(
        entity_reference(from_entity or context.file_entity),
        target.name,
        operation.edge_type,
        context,
        parser,
        to_type="storage_location",
        line_number=line_number,
        properties=properties,
    )


def normalize_storage_target(value: str) -> str:
    raw = value.strip().strip("\"'")
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path = parsed.path.strip("/")
        return f"{parsed.netloc}/{path}" if path else parsed.netloc
    return raw.replace("\\", "/")
