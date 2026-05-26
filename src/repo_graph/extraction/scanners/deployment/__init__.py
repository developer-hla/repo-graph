"""Public deployment manifest scanner API."""

from repo_graph.extraction.scanners.deployment.kubernetes import KubernetesManifestExtractor

__all__ = ["KubernetesManifestExtractor"]
