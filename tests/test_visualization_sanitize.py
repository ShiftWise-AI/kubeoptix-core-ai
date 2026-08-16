"""Testes de sanitização de IDs Mermaid."""

from __future__ import annotations

from kubeoptix_analyzer.visualization.sanitize import sanitize_mermaid_id, sanitize_mermaid_label


def test_sanitize_mermaid_id_replaces_invalid_chars() -> None:
    assert sanitize_mermaid_id("backend-acesso-app") == "backend_acesso_app"


def test_sanitize_mermaid_id_prefixes_leading_digit() -> None:
    assert sanitize_mermaid_id("123-app").startswith("n_")


def test_sanitize_mermaid_id_empty_fallback() -> None:
    assert sanitize_mermaid_id("---") == "n"


def test_sanitize_mermaid_label_escapes_quotes() -> None:
    assert '"' not in sanitize_mermaid_label('say "hello"')


def test_sanitize_mermaid_label_preserves_slashes() -> None:
    assert sanitize_mermaid_label("Service/backend-acesso-app") == "Service/backend-acesso-app"


def test_flowchart_quotes_labels_with_special_chars() -> None:
    from kubeoptix_analyzer.visualization.mermaid.flowchart import _node_shape

    line = _node_shape("route", "route_x", "Route/backend-acesso-app")
    assert '    route_x{{"Route/backend-acesso-app"}}' == line

    line = _node_shape("service", "svc_x", "Service/foo :8081")
    assert '    svc_x[("Service/foo :8081")]' == line

    edge_line = _node_shape("external", "ext_x", "Cliente<br/>host.com")
    assert '    ext_x(["Cliente<br/>host.com"])' == edge_line


def test_flowchart_rect_fallback_for_parens() -> None:
    from kubeoptix_analyzer.visualization.mermaid.flowchart import _node_shape

    line = _node_shape("database", "dep_x", "Oracle Database (JDBC)")
    assert '    dep_x["Oracle Database (JDBC)"]' == line

    line = _node_shape("external", "img_x", "Image (registry)")
    assert '    img_x["Image (registry)"]' == line


def test_flowchart_rect_fallback_for_brackets() -> None:
    from kubeoptix_analyzer.visualization.mermaid.flowchart import _node_shape
    from kubeoptix_analyzer.visualization.sanitize import label_needs_rect_node_shape

    label = "Image<br/>registry:4567[CAMINHO_REMOVIDO]"
    assert label_needs_rect_node_shape(label)
    line = _node_shape("external", "img_x", label)
    assert '    img_x["Image<br/>registry:4567(CAMINHO_REMOVIDO)"]' == line


def test_sanitize_mermaid_edge_label_quotes_when_needed() -> None:
    from kubeoptix_analyzer.visualization.sanitize import sanitize_mermaid_edge_label

    assert sanitize_mermaid_edge_label("selector") == "selector"
    assert sanitize_mermaid_edge_label("TLS edge (HTTP permitido)") == (
        '"TLS edge (HTTP permitido)"'
    )


def test_sanitize_mermaid_pie_title_without_quotes() -> None:
    from kubeoptix_analyzer.visualization.sanitize import sanitize_mermaid_pie_title

    assert '"' not in sanitize_mermaid_pie_title('Distribuição de QoS')
    assert sanitize_mermaid_pie_title("A: B") == "A - B"
