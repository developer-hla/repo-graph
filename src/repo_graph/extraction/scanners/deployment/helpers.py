"""Deployment manifest scanner helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
    unresolved_relationship_fact,
)
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.interaction_properties import interaction_properties
from repo_graph.extraction.scanners.common import object_mapping, string_value
from repo_graph.extraction.scanners.interactions.http import http_target
from repo_graph.extraction.scanners.interactions.naming import (
    ENV_NAME_RE,
    service_name_from_env,
    service_name_from_url,
    url_value,
)
from repo_graph.extraction.scanners.interactions.routes import route_entity_fact


@dataclass(frozen=True)
class KubernetesService:
    entity: EntityFact
    selector: dict[str, str]


@dataclass(frozen=True)
class KubernetesDeployment:
    entity: EntityFact
    pod_labels: dict[str, str]


def kubernetes_service_facts(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[FactBatch, KubernetesService] | None:
    name = kubernetes_resource_name(document)
    if not name:
        return None
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    selector = string_dict(spec.get("selector"))
    service = entity_fact(
        context,
        entity_type="service",
        name=name,
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
    facts = FactBatch(
        entities=[service],
        relationships=[
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                service.reference,
                "DECLARES_SERVICE",
                context,
                "kubernetes_service",
            )
        ],
    )
    return facts, KubernetesService(service, selector)


def kubernetes_deployment_facts(
    context: FileScanContext,
    document: dict[str, Any],
) -> tuple[FactBatch, KubernetesDeployment] | None:
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
    deployment = entity_fact(
        context,
        entity_type="deployment",
        name=name,
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
    facts = FactBatch(
        entities=[deployment],
        relationships=[
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                deployment.reference,
                "DECLARES_DEPLOYMENT",
                context,
                "kubernetes_deployment",
            )
        ],
    )
    for container in mapping_list(pod_spec.get("containers")):
        facts.extend(kubernetes_container_facts(context, deployment, namespace, container))
    return facts, KubernetesDeployment(deployment, pod_labels)


def kubernetes_container_facts(
    context: FileScanContext,
    deployment: EntityFact,
    namespace: str,
    container: dict[str, Any],
) -> FactBatch:
    facts = FactBatch()
    container_name = string_value(container.get("name"))
    if not container_name:
        return facts
    image = string_value(container.get("image"))
    container_entity = entity_fact(
        context,
        entity_type="container",
        name=f"{deployment.name}:{container_name}",
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
    facts.entities.append(container_entity)
    facts.relationships.append(
        resolved_relationship_fact(
            deployment.reference,
            container_entity.reference,
            "RUNS_CONTAINER",
            context,
            "kubernetes_container",
        )
    )
    for env in mapping_list(container.get("env")):
        facts.extend(kubernetes_env_facts(context, container_entity, deployment.name, env))
    return facts


def kubernetes_env_facts(
    context: FileScanContext,
    container: EntityFact,
    deployment_name: str,
    env: dict[str, Any],
) -> FactBatch:
    facts = FactBatch()
    env_name = string_value(env.get("name"))
    if not env_name:
        return facts
    env_value = string_value(env.get("value"))
    target_url = url_value(env_value)
    config_value = entity_fact(
        context,
        entity_type="config_value",
        name=f"env:{deployment_name}:{container.name.rsplit(':', 1)[-1]}:{env_name}",
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
    facts.entities.append(config_value)
    facts.relationships.append(
        resolved_relationship_fact(
            container.reference,
            config_value.reference,
            "DECLARES_CONFIG",
            context,
            "kubernetes_env",
        )
    )
    service_fact = kubernetes_env_service_fact(config_value, context)
    if service_fact:
        facts.relationships.append(service_fact)
    return facts


def kubernetes_env_service_fact(config_value: EntityFact, context: FileScanContext) -> RelationshipFact | None:
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
    return unresolved_relationship_fact(
        config_value.reference,
        service_name,
        "CONFIGURES_SERVICE",
        context,
        "kubernetes_env",
        to_type="service",
        properties=target,
    )


def kubernetes_ingress_facts(context: FileScanContext, document: dict[str, Any]) -> FactBatch:
    facts = FactBatch()
    name = kubernetes_resource_name(document)
    if not name:
        return facts
    metadata = object_mapping(document.get("metadata"))
    spec = object_mapping(document.get("spec"))
    namespace = kubernetes_namespace(metadata)
    ingress = entity_fact(
        context,
        entity_type="ingress",
        name=name,
        aliases=kubernetes_scoped_aliases(name, namespace),
        properties={
            "ecosystem": "kubernetes",
            "kind": "Ingress",
            "namespace": namespace,
            "labels": string_dict(metadata.get("labels")),
            "project": context.project.name if context.project else None,
        },
    )
    facts.entities.append(ingress)
    facts.relationships.append(
        resolved_relationship_fact(
            entity_reference(context.file_entity),
            ingress.reference,
            "DECLARES_INGRESS",
            context,
            "kubernetes_ingress",
        )
    )
    for rule in mapping_list(spec.get("rules")):
        facts.extend(kubernetes_ingress_rule_facts(context, ingress, rule))
    return facts


def kubernetes_ingress_rule_facts(context: FileScanContext, ingress: EntityFact, rule: dict[str, Any]) -> FactBatch:
    facts = FactBatch()
    host = string_value(rule.get("host"))
    http = object_mapping(rule.get("http"))
    for path_item in mapping_list(http.get("paths")):
        path = string_value(path_item.get("path")) or "/"
        route = route_entity_fact(context, "ANY", path, 1, "kubernetes_ingress_route", operation_name=None)
        route_aliases = set(route.aliases)
        route_properties = dict(route.properties)
        if host:
            route_aliases.add(f"{host}{path}")
            route_properties["host"] = host
        route_properties["path_type"] = string_value(path_item.get("pathType"))
        route = replace(route, aliases=frozenset(route_aliases), properties=route_properties)
        facts.entities.append(route)
        facts.relationships.append(
            resolved_relationship_fact(
                entity_reference(context.file_entity),
                route.reference,
                "DECLARES_ROUTE",
                context,
                "kubernetes_ingress_route",
                1,
            )
        )
        facts.relationships.append(
            resolved_relationship_fact(
                ingress.reference,
                route.reference,
                "EXPOSES_ROUTE",
                context,
                "kubernetes_ingress_route",
                1,
            )
        )
        service_name = kubernetes_ingress_backend_service_name(path_item.get("backend"))
        if service_name:
            facts.relationships.append(
                unresolved_relationship_fact(
                    route.reference,
                    service_name,
                    "ROUTES_TO_SERVICE",
                    context,
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
    return facts


def kubernetes_selector_facts(
    context: FileScanContext,
    services: Sequence[KubernetesService],
    deployments: Sequence[KubernetesDeployment],
) -> list[RelationshipFact]:
    facts: list[RelationshipFact] = []
    for service in services:
        if not service.selector:
            continue
        for deployment in deployments:
            if labels_match_selector(deployment.pod_labels, service.selector):
                facts.append(
                    resolved_relationship_fact(
                        service.entity.reference,
                        deployment.entity.reference,
                        "SELECTS_DEPLOYMENT",
                        context,
                        "kubernetes_selector",
                    )
                )
    return facts


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
