"""Kubernetes manifest value normalization helpers."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.scanners.common import object_mapping, string_value


def kubernetes_resource_name(document: dict[str, Any]) -> str | None:
    metadata = object_mapping(document.get("metadata"))
    return string_value(metadata.get("name"))


def kubernetes_namespace(metadata: dict[str, Any]) -> str:
    return string_value(metadata.get("namespace")) or "default"


def kubernetes_scoped_aliases(name: str, namespace: str) -> set[str]:
    return {
        name,
        f"{name}.{namespace}",
        f"{name}.{namespace}.svc",
        f"{name}.{namespace}.svc.cluster.local",
    }


def kubernetes_service_ports(value: object) -> list[dict[str, Any]]:
    ports = []
    for port in mapping_list(value):
        ports.append(
            {
                "name": string_value(port.get("name")),
                "port": port.get("port"),
                "target_port": port.get("targetPort"),
                "protocol": string_value(port.get("protocol")),
            }
        )
    return ports


def kubernetes_match_labels(value: object) -> dict[str, str]:
    return string_dict(object_mapping(value).get("matchLabels"))


def mapping_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}
