from __future__ import annotations

from collections.abc import Callable

import httpx
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


@pytest.fixture
def settings_http(monkeypatch: pytest.MonkeyPatch):
    real_client = httpx.Client

    def configure(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        monkeypatch.setattr(
            i18n.httpx,
            "Client",
            lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
        )

    return configure


def test_resolve_system_locale_reads_language(settings_http) -> None:
    requested_urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        assert request.headers["Accept"] == "application/json"
        assert request.extensions["timeout"]["read"] == 5.0
        return httpx.Response(200, json={"language": "it-IT"})

    settings_http(respond)

    assert i18n.resolve_system_locale(url="http://configurations-api:8000") == "it-IT"
    assert requested_urls == ["http://configurations-api:8000/system-settings"]


def test_resolve_system_locale_accepts_full_endpoint(
    settings_http,
) -> None:
    requested_urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"language": "en-US"})

    settings_http(respond)

    assert (
        i18n.resolve_system_locale(
            url="http://configurations-api:8000/system-settings"
        )
        == "en-US"
    )
    assert requested_urls == ["http://configurations-api:8000/system-settings"]


def test_resolve_system_locale_rejects_missing_language(
    settings_http,
) -> None:
    settings_http(lambda request: httpx.Response(200, json={}))

    with pytest.raises(ConfigurationError, match="Locale não suportado"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_surfaces_api_unavailability(
    settings_http,
) -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise OSError("connection refused")

    settings_http(unavailable)

    with pytest.raises(ConfigurationError, match="Não foi possível consultar"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_surfaces_http_status_and_body(
    settings_http,
) -> None:
    settings_http(
        lambda request: httpx.Response(503, json={"message": "database unavailable"})
    )

    with pytest.raises(
        ConfigurationError,
        match=r"HTTP 503.*database unavailable",
    ):
        i18n.resolve_system_locale()


def test_resolve_system_locale_follows_http_redirects(settings_http) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system-settings":
            return httpx.Response(302, headers={"Location": "/settings"})
        return httpx.Response(200, json={"language": "es-ES"})

    settings_http(respond)
    assert i18n.resolve_system_locale() == "es-ES"


@pytest.mark.parametrize("payload", [b"not-json", b"[]"])
def test_resolve_system_locale_rejects_invalid_response(settings_http, payload: bytes) -> None:
    settings_http(lambda request: httpx.Response(200, content=payload))
    with pytest.raises(ConfigurationError):
        i18n.resolve_system_locale()


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_resolve_system_locale_wraps_transport_errors(settings_http, error_type) -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        raise error_type("service unavailable", request=request)

    settings_http(unavailable)
    with pytest.raises(ConfigurationError, match="Não foi possível acessar"):
        i18n.resolve_system_locale()


def test_resolve_system_locale_rejects_file_urls() -> None:
    with pytest.raises(ConfigurationError):
        i18n.resolve_system_locale(url="file:///etc/passwd")
