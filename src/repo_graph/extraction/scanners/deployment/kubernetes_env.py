"""Kubernetes environment variable fact extraction."""

from __future__ import annotations

from typing import Any

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import entity_fact, resolved_relationship_fact
from repo_graph.extraction.facts import EntityFact, FactBatch, RelationshipFact
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.interactions.naming import (
    ENV_NAME_RE,
    service_name_from_env,
    service_name_from_url,
    url_value,
)
from repo_graph.extraction.scanners.interactions.services import service_configuration_fact


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
    return service_configuration_fact(
        config_value.reference,
        raw_target,
        context,
        "kubernetes_env",
        service_name=service_name,
        extra_properties={"config_key": key},
    )
