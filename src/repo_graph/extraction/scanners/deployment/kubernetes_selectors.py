"""Kubernetes selector relationship extraction."""

from __future__ import annotations

from collections.abc import Sequence

from repo_graph.extraction.contracts import FileScanContext
from repo_graph.extraction.fact_helpers import resolved_relationship_fact
from repo_graph.extraction.facts import RelationshipFact
from repo_graph.extraction.scanners.deployment.kubernetes_resources import KubernetesDeployment, KubernetesService


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
