"""Deployment manifest scanner helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.legacy_graph_helpers import interaction_properties, resolved_edge, unresolved_edge
from repo_graph.extraction.scanners.common import object_mapping, string_value
from repo_graph.extraction.scanners.interaction_helpers import (
    ENV_NAME_RE,
    http_target,
    route_entity,
    service_name_from_env,
    service_name_from_url,
    url_value,
)
from repo_graph.graph import Edge, Entity


@dataclass(frozen=True)
class KubernetesService:
    entity: Entity
    selector: dict[str, str]


@dataclass(frozen=True)
class KubernetesDeployment:
    entity: Entity
    pod_labels: dict[str, str]


def kubernetes_service_result(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[ScanResult, KubernetesService] | None:
    name = kubernetes_resource_name(document)
    if not name:
        return None
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    selector = string_dict(spec.get("selector"))
    service = Entity(
        entity_type="service",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Service",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "selector": selector,
            "ports": kubernetes_service_ports(spec.get("ports")),
            "project": context.project.name if context.project else None,
        },
    )
    result = ScanResult(
        entities=[service],
        edges=[
            resolved_edge(
                context.file_entity,
                service,
                "DECLARES_SERVICE",
                context.source.name,
                context.rel_path,
                "kubernetes_service",
            )
        ],
    )
    return result, KubernetesService(service, selector)


def kubernetes_deployment_result(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[ScanResult, KubernetesDeployment] | None:
    name = kubernetes_resource_name(document)
    if not name:
        return None
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    template = object_mapping(spec.get("template"))
    pod_metadata = object_mapping(template.get("metadata"))
    pod_spec = object_mapping(template.get("spec"))
    namespace = kubernetes_namespace(metadata)
    pod_labels = string_dict(pod_metadata.get("labels"))
    deployment = Entity(
        entity_type="deployment",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Deployment",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "selector": kubernetes_match_labels(spec.get("selector")),
            "pod_labels": pod_labels,
            "replicas": spec.get("replicas"),
            "project": context.project.name if context.project else None,
        },
    )
    result = ScanResult(
        entities=[deployment],
        edges=[
            resolved_edge(
                context.file_entity,
                deployment,
                "DECLARES_DEPLOYMENT",
                context.source.name,
                context.rel_path,
                "kubernetes_deployment",
            )
        ],
    )
    for container in mapping_list(pod_spec.get("containers")):
        result.extend(kubernetes_container_result(context, deployment, namespace, container))
    return result, KubernetesDeployment(deployment, pod_labels)


def kubernetes_container_result(
    context: FileScanContext,
    deployment: Entity,
    namespace: str,
    container: dict[str, Any],
) -> ScanResult:
    result = ScanResult()
    container_name = string_value(container.get("name"))
    if not container_name:
        return result
    image = string_value(container.get("image"))
    container_entity = Entity(
        entity_type="container",
        name=f"{deployment.name}:{container_name}",
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={container_name, *(set() if not image else {image})},
        properties={
            "ecosystem": "kubernetes",
            "namespace": namespace,
            "deployment": deployment.name,
            "image": image,
            "env_names": [
                env_name
                for env in mapping_list(container.get("env"))
                if (env_name := string_value(env.get("name"))) is not None
            ],
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(container_entity)
    result.edges.append(
        resolved_edge(
            deployment,
            container_entity,
            "RUNS_CONTAINER",
            context.source.name,
            context.rel_path,
            "kubernetes_container",
        )
    )
    for env in mapping_list(container.get("env")):
        result.extend(kubernetes_env_result(context, container_entity, deployment.name, env))
    return result


def kubernetes_env_result(
    context: FileScanContext,
    container: Entity,
    deployment_name: str,
    env: dict[str, Any],
) -> ScanResult:
    result = ScanResult()
    env_name = string_value(env.get("name"))
    if not env_name:
        return result
    env_value = string_value(env.get("value"))
    target_url = url_value(env_value)
    config_value = Entity(
        entity_type="config_value",
        name=f"env:{deployment_name}:{container.name.rsplit(':', 1)[-1]}:{env_name}",
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases={env_name},
        properties={
            "display_name": env_name,
            "value_kind": "environment_variable",
            "key": env_name,
            "has_value": env_value is not None,
            "target_url": target_url,
            "project": context.project.name if context.project else None,
            "container": container.name,
            "deployment": deployment_name,
        },
    )
    result.entities.append(config_value)
    result.edges.append(
        resolved_edge(
            container,
            config_value,
            "DECLARES_CONFIG",
            context.source.name,
            context.rel_path,
            "kubernetes_env",
        )
    )
    service_edge = kubernetes_env_service_edge(config_value, context)
    if service_edge:
        result.edges.append(service_edge)
    return result


def kubernetes_env_service_edge(config_value: Entity, context: FileScanContext) -> Edge | None:
    key = config_value.properties.get("key")
    raw_target = config_value.properties.get("target_url")
    service_name: str | None = None
    if isinstance(raw_target, str):
        service_name = service_name_from_url(raw_target)
    elif isinstance(key, str) and ENV_NAME_RE.fullmatch(key):
        raw_target = key
        service_name = service_name_from_env(key)
    if not service_name or not isinstance(raw_target, str):
        return None
    target = http_target(raw_target, "GET")
    target["dependency_scope"] = "configuration"
    target["interaction_kind"] = "service_configuration"
    target["config_key"] = key
    target["service_name"] = service_name
    return unresolved_edge(
        config_value,
        service_name,
        "CONFIGURES_SERVICE",
        context.source.name,
        context.rel_path,
        "kubernetes_env",
        to_type="service",
        properties=target,
    )


def kubernetes_ingress_result(context: FileScanContext, document: dict[str, Any]) -> ScanResult:
    result = ScanResult()
    name = kubernetes_resource_name(document)
    if not name:
        return result
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    ingress = Entity(
        entity_type="ingress",
        name=name,
        source_name=context.source.name,
        file_path=context.rel_path,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Ingress",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "project": context.project.name if context.project else None,
        },
    )
    result.entities.append(ingress)
    result.edges.append(
        resolved_edge(
            context.file_entity,
            ingress,
            "DECLARES_INGRESS",
            context.source.name,
            context.rel_path,
            "kubernetes_ingress",
        )
    )
    for rule in mapping_list(spec.get("rules")):
        result.extend(kubernetes_ingress_rule_result(context, ingress, rule))
    return result


def kubernetes_ingress_rule_result(context: FileScanContext, ingress: Entity, rule: dict[str, Any]) -> ScanResult:
    result = ScanResult()
    host = string_value(rule.get("host"))
    http = object_mapping(rule.get("http"))
    for path_item in mapping_list(http.get("paths")):
        path = string_value(path_item.get("path")) or "/"
        route = route_entity(context, "ANY", path, 1, "kubernetes_ingress_route", operation_name=None)
        if host:
            route.aliases.add(f"{host}{path}")
            route.properties["host"] = host
        route.properties["path_type"] = string_value(path_item.get("pathType"))
        result.entities.append(route)
        result.edges.append(
            resolved_edge(
                context.file_entity,
                route,
                "DECLARES_ROUTE",
                context.source.name,
                context.rel_path,
                "kubernetes_ingress_route",
                1,
            )
        )
        result.edges.append(
            resolved_edge(
                ingress,
                route,
                "EXPOSES_ROUTE",
                context.source.name,
                context.rel_path,
                "kubernetes_ingress_route",
                1,
            )
        )
        service_name = kubernetes_ingress_backend_service_name(path_item.get("backend"))
        if service_name:
            result.edges.append(
                unresolved_edge(
                    route,
                    service_name,
                    "ROUTES_TO_SERVICE",
                    context.source.name,
                    context.rel_path,
                    "kubernetes_ingress_route",
                    to_type="service",
                    line_number=1,
                    properties=interaction_properties(
                        "application",
                        "deployment",
                        "ingress_route",
                        protocol="http",
                        raw_target=service_name,
                        normalized_target=service_name,
                        service_name=service_name,
                    ),
                )
            )
    return result


def kubernetes_selector_edges(
    context: FileScanContext,
    services: Sequence[KubernetesService],
    deployments: Sequence[KubernetesDeployment],
) -> list[Edge]:
    edges: list[Edge] = []
    for service in services:
        if not service.selector:
            continue
        for deployment in deployments:
            if labels_match_selector(deployment.pod_labels, service.selector):
                edges.append(
                    resolved_edge(
                        service.entity,
                        deployment.entity,
                        "SELECTS_DEPLOYMENT",
                        context.source.name,
                        context.rel_path,
                        "kubernetes_selector",
                    )
                )
    return edges


def labels_match_selector(labels: dict[str, str], selector: dict[str, str]) -> bool:
    return bool(selector) and all(labels.get(key) == value for key, value in selector.items())


def kubernetes_ingress_backend_service_name(value: object) -> str | None:
    backend = object_mapping(value)
    service = object_mapping(backend.get("service"))
    service_name = string_value(service.get("name"))
    if service_name:
        return service_name
    return string_value(backend.get("serviceName"))


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
