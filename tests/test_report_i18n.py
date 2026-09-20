from __future__ import annotations

import io
import json

import pytest

from kubeoptix_core_ai.errors import ConfigurationError
from kubeoptix_core_ai.report import i18n


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("pt-BR", "Relatório de Assessment"),
        ("en-US", "Assessment Report"),
        ("es-ES", "Informe de evaluación"),
        ("it-IT", "Rapporto di valutazione"),
    ],
)
def test_report_catalogs_use_supported_bcp47_locales(
    locale: str, expected: str
) -> None:
    assert i18n.translate_report("Relatório de Assessment", locale) == expected


@pytest.mark.parametrize("language", [None, "", "pt-br", "fr-FR", 123])
def test_validate_locale_rejects_missing_empty_and_unsupported_values(
    language: object,
) -> None:
    with pytest.raises(ConfigurationError, match="Locale não suportado"):
        i18n.validate_locale(language)


def test_resolve_system_locale_reads_language(monkeypatch: pytest.MonkeyPatch) -> None:
    response = io.BytesIO(json.dumps({"language": "it-IT"}).encode())
    monkeypatch.setattr(i18n, "urlopen", lambda request, timeout: response)

    assert i18n.resolve_system_locale() == "it-IT"


def test_resolve_system_locale_rejects_missing_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = io.BytesIO(b"{}")
    monkeypatch.setattr(i18n, "urlopen", lambda request, timeout: response)

    with pytest.raises(ConfigurationError, match="Locale não suportado"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_surfaces_api_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(request: object, timeout: float) -> object:
        raise OSError("connection refused")

    monkeypatch.setattr(i18n, "urlopen", unavailable)

    with pytest.raises(ConfigurationError, match="Não foi possível consultar"):
        i18n.resolve_system_locale()
