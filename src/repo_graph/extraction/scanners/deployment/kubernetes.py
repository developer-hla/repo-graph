"""Deployment manifest scanners."""

from __future__ import annotations

from pathlib import Path

import yaml

from repo_graph.extraction.contracts import FileScanContext, ScannerMetadataMixin, ScannerSpec
from repo_graph.extraction.fact_helpers import scan_issue
from repo_graph.extraction.facts import FactBatch
from repo_graph.extraction.scanners.common import string_value
from repo_graph.extraction.scanners.deployment.kubernetes_ingress import kubernetes_ingress_facts
from repo_graph.extraction.scanners.deployment.kubernetes_resources import (
    KubernetesDeployment,
    KubernetesService,
    kubernetes_deployment_facts,
    kubernetes_service_facts,
)
from repo_graph.extraction.scanners.deployment.kubernetes_selectors import kubernetes_selector_facts


class KubernetesManifestExtractor(ScannerMetadataMixin):
    spec = ScannerSpec(
        name="kubernetes",
        family="deployment",
        target_patterns=("*.yaml", "*.yml"),
        parser_ids=(
            "kubernetes_container",
            "kubernetes_deployment",
            "kubernetes_env",
            "kubernetes_ingress",
            "kubernetes_ingress_route",
            "kubernetes_selector",
            "kubernetes_service",
        ),
        description="Kubernetes services, deployments, ingress, selectors, containers, and env links.",
    )

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".yaml", ".yml"}

    def extract(self, context: FileScanContext, content: str) -> FactBatch:
        facts = FactBatch()
        if "apiVersion:" not in content or "kind:" not in content:
            return facts

        try:
            documents = [document for document in yaml.safe_load_all(content) if isinstance(document, dict)]
        except yaml.YAMLError as exc:
            facts.issues.append(
                scan_issue(
                    context,
                    self.name,
                    f"Invalid Kubernetes YAML {context.source.name}/{context.rel_path}: {exc}",
                )
            )
            return facts

        services: list[KubernetesService] = []
        deployments: list[KubernetesDeployment] = []
        for document in documents:
            kind = string_value(document.get("kind"))
            if kind == "Service":
                service = kubernetes_service_facts(context, document)
                if service:
                    facts.extend(service[0])
                    services.append(service[1])
            elif kind == "Deployment":
                deployment = kubernetes_deployment_facts(context, document)
                if deployment:
                    facts.extend(deployment[0])
                    deployments.append(deployment[1])
            elif kind == "Ingress":
                facts.extend(kubernetes_ingress_facts(context, document))

        facts.relationships.extend(kubernetes_selector_facts(context, services, deployments))
        return facts
