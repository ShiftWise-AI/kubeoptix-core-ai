"""Parsers de recursos Kubernetes/OpenShift."""

from kubeoptix_analyzer.parsers.deployment import parse_deployment
from kubeoptix_analyzer.parsers.hpa import parse_hpa
from kubeoptix_analyzer.parsers.node import parse_node
from kubeoptix_analyzer.parsers.pod import parse_pod
from kubeoptix_analyzer.parsers.pod_metrics import parse_pod_metrics

__all__ = [
    "parse_deployment",
    "parse_hpa",
    "parse_node",
    "parse_pod",
    "parse_pod_metrics",
]
