"""Deployment manifest scanners."""

from __future__ import annotations

from pathlib import Path

import yaml

from repo_graph.extraction.contracts import FileScanContext, ScanResult
from repo_graph.extraction.scanners.shared import (
    KubernetesDeployment,
    KubernetesService,
    kubernetes_deployment_result,
    kubernetes_ingress_result,
    kubernetes_selector_edges,
    kubernetes_service_result,
    string_value,
)


class KubernetesManifestExtractor:
    name = "kubernetes"

    def can_process(self, rel_path: str) -> bool:
        return Path(rel_path).suffix.lower() in {".yaml", ".yml"}

    def extract(self, context: FileScanContext, content: str) -> ScanResult:
        result = ScanResult()
        if "apiVersion:" not in content or "kind:" not in content:
            return result

        try:
            documents = [document for document in yaml.safe_load_all(content) if isinstance(document, dict)]
        except yaml.YAMLError as exc:
            result.errors.append(f"Invalid Kubernetes YAML {context.source.name}/{context.rel_path}: {exc}")
            return result

        services: list[KubernetesService] = []
        deployments: list[KubernetesDeployment] = []
        for document in documents:
            kind = string_value(document.get("kind"))
            if kind == "Service":
                service = kubernetes_service_result(context, document)
                if service:
                    result.extend(service[0])
                    services.append(service[1])
            elif kind == "Deployment":
                deployment = kubernetes_deployment_result(context, document)
                if deployment:
                    result.extend(deployment[0])
                    deployments.append(deployment[1])
            elif kind == "Ingress":
                result.extend(kubernetes_ingress_result(context, document))

        result.edges.extend(kubernetes_selector_edges(context, services, deployments))
        return result
