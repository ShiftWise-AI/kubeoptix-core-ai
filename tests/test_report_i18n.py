from __future__ import annotations

import io
import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from kubeoptix_core_ai.errors import ConfigurationError
from kubeoptix_core_ai.report import i18n
from kubeoptix_core_ai.visualization.builders import _localize_numeric
from kubeoptix_core_ai.visualization.models import ChartDataset, ChartPoint, ChartSeries


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


def test_translation_does_not_replace_singular_terms_inside_plurals() -> None:
    translated = i18n.translate_report(
        "**Evidências:** Valores agregados. Referências utilizadas.",
        "it-IT",
    )

    assert translated == "**Evidenze:** Valori aggregati. Riferimenti utilizzati."
    assert "Evidenzas" not in translated
    assert "Valorees" not in translated
    assert "Riferimentos" not in translated


def test_visualization_dataset_is_localized_before_rendering() -> None:
    dataset = ChartDataset(
        title="Distribuição de QoS",
        question="Como os workloads se distribuem entre classes QoS?",
        x_labels=("Memória",),
        x_axis_label="Recurso",
        y_axis_label="Quantidade",
        series=(
            ChartSeries(
                name="Valores",
                points=(ChartPoint(label="Memória", value=1, unit="MiB"),),
            ),
        ),
    )

    localized = _localize_numeric(dataset, "it-IT")

    assert localized.title == "Distribuzione QoS"
    assert localized.question == "Come sono distribuiti i workload tra le classi QoS?"
    assert localized.x_labels == ("Memoria",)
    assert localized.x_axis_label == "Risorsa"
    assert localized.y_axis_label == "Quantità"
    assert localized.series[0].name == "Valori"


@pytest.mark.parametrize("language", [None, "", "pt-br", "fr-FR", 123])
def test_validate_locale_rejects_missing_empty_and_unsupported_values(
    language: object,
) -> None:
    with pytest.raises(
        ConfigurationError,
        match=rf"Locale não suportado recebido de /system-settings: {language!r}",
    ):
        i18n.validate_locale(language)


def test_resolve_system_locale_reads_language(monkeypatch: pytest.MonkeyPatch) -> None:
    response = io.BytesIO(json.dumps({"language": "it-IT"}).encode())
    requested_urls: list[str] = []

    def respond(request: Request, timeout: float) -> io.BytesIO:
        del timeout
        requested_urls.append(request.full_url)
        return response

    monkeypatch.setattr(i18n, "urlopen", respond)

    assert i18n.resolve_system_locale(url="http://configurations-api:8000") == "it-IT"
    assert requested_urls == ["http://configurations-api:8000/system-settings"]


def test_resolve_system_locale_accepts_full_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = io.BytesIO(b'{"language":"en-US"}')
    requested_urls: list[str] = []

    def respond(request: Request, timeout: float) -> io.BytesIO:
        del timeout
        requested_urls.append(request.full_url)
        return response

    monkeypatch.setattr(i18n, "urlopen", respond)

    assert (
        i18n.resolve_system_locale(
            url="http://configurations-api:8000/system-settings"
        )
        == "en-US"
    )
    assert requested_urls == ["http://configurations-api:8000/system-settings"]


def test_resolve_system_locale_rejects_missing_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = io.BytesIO(b"{}")

    def respond(_request: object, timeout: float) -> io.BytesIO:
        del _request
        del timeout
        return response

    monkeypatch.setattr(i18n, "urlopen", respond)

    with pytest.raises(ConfigurationError, match="Locale não suportado"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_surfaces_api_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_request: object, timeout: float) -> object:
        del _request
        del timeout
        raise OSError("connection refused")

    monkeypatch.setattr(i18n, "urlopen", unavailable)

    with pytest.raises(ConfigurationError, match="Não foi possível consultar"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_surfaces_http_status_and_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failed(_request: object, timeout: float) -> object:
        del _request
        del timeout
        raise HTTPError(
            "http://configurations-api:8000/system-settings",
            503,
            "Service Unavailable",
            {},
            io.BytesIO(b'{"message":"database unavailable"}'),
        )

    monkeypatch.setattr(i18n, "urlopen", failed)

    with pytest.raises(
        ConfigurationError,
        match=r"HTTP 503.*database unavailable",
    ):
        i18n.resolve_system_locale()
