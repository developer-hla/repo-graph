"""Kubernetes ingress fact extraction."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import (
    entity_fact,
    entity_reference,
    resolved_relationship_fact,
)
from repo_graph.extraction.facts import EntityFact, FactBatch
from repo_graph.extraction.scanners.common import object_mapping, string_value
from repo_graph.extraction.scanners.deployment.kubernetes_values import (
    kubernetes_namespace,
    kubernetes_resource_name,
    kubernetes_scoped_aliases,
    mapping_list,
    string_dict,
)
from repo_graph.extraction.scanners.interactions.routes import route_entity_fact
from repo_graph.extraction.scanners.interactions.services import route_to_service_fact


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
                route_to_service_fact(
                    route.reference,
                    service_name,
                    context,
                    "kubernetes_ingress_route",
                    line_number=1,
                )
            )
    return facts


def kubernetes_ingress_backend_service_name(value: object) -> str | None:
    backend = object_mapping(value)
    service = object_mapping(backend.get("service"))
    service_name = string_value(service.get("name"))
    if service_name:
        return service_name
    return string_value(backend.get("serviceName"))
