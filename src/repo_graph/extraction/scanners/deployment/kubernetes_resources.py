"""Kubernetes workload and service fact extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, entity_reference, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.common import object_mapping, string_value
from repo_graph.extraction.scanners.deployment.kubernetes_env import kubernetes_env_facts
from repo_graph.extraction.scanners.deployment.kubernetes_values import (
    kubernetes_match_labels,
    kubernetes_namespace,
    kubernetes_resource_name,
    kubernetes_scoped_aliases,
    kubernetes_service_ports,
    mapping_list,
    string_dict,
)


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
