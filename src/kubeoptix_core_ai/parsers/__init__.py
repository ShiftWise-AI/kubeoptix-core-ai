"""Parsers de recursos Kubernetes/OpenShift."""

from kubeoptix_core_ai.parsers.deployment import parse_deployment
from kubeoptix_core_ai.parsers.hpa import parse_hpa
from kubeoptix_core_ai.parsers.node import parse_node
from kubeoptix_core_ai.parsers.pod import parse_pod
from kubeoptix_core_ai.parsers.pod_metrics import parse_pod_metrics

__all__ = [
    "parse_deployment",
    "parse_hpa",
    "parse_node",
    "parse_pod",
    "parse_pod_metrics",
]
