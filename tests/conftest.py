"""Configuração compartilhada dos testes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXAMPLE_NAMESPACE = "example-ns-prd"


@pytest.fixture(autouse=True)
def system_locale_for_report_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests local; integration tests override this client explicitly."""
    monkeypatch.setattr(
        "kubeoptix_core_ai.api.assessment.resolve_system_locale",
        lambda: "pt-BR",
    )
    monkeypatch.setattr(
        "kubeoptix_core_ai.report.markdown.resolve_system_locale",
        lambda: "pt-BR",
    )


@pytest.fixture(autouse=True)
def disable_external_kubediagrams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "kubeoptix_core_ai.visualization.kubediagrams.renderer.is_kubediagrams_available",
        lambda: False,
    )
