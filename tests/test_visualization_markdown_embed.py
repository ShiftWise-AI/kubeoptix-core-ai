"""Testes de incorporação de imagens no Markdown."""

from __future__ import annotations

from pathlib import Path

from kubeoptix_core_ai.visualization.markdown import (
    _markdown_architecture_image,
    _markdown_image,
    embed_markdown_images,
)


def test_markdown_image_uses_relative_prefix() -> None:
    assert _markdown_image("CPU", "ns_assets/cpu.png") == "![CPU](./ns_assets/cpu.png)"


def test_markdown_architecture_image_uses_full_page_width() -> None:
    rendered = _markdown_architecture_image(
        "Arquitetura",
        "ns_assets/namespace_architecture.png",
    )
    assert "![Arquitetura](./ns_assets/namespace_architecture.png)" in rendered
    assert "width=100%" in rendered
    assert "<img" not in rendered


def test_embed_markdown_images_strips_legacy_width_attribute(tmp_path: Path) -> None:
    assets = tmp_path / "ns_assets"
    assets.mkdir()
    png = assets / "arch.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = "![Architecture](./ns_assets/arch.png){ width=100% }\n"
    embedded = embed_markdown_images(content, markdown_dir=tmp_path)

    assert "data:image/png;base64," in embedded
    assert "{ width=100% }" not in embedded


def test_embed_markdown_images_inlines_html_full_width(tmp_path: Path) -> None:
    assets = tmp_path / "ns_assets"
    assets.mkdir()
    png = assets / "arch.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = (
        '<img src="./ns_assets/arch.png" alt="Arquitetura" '
        'style="width:100%;max-width:100%;height:auto;" />\n'
    )
    embedded = embed_markdown_images(content, markdown_dir=tmp_path)

    assert "data:image/png;base64," in embedded
    assert "width:100%" in embedded
    assert "./ns_assets/" not in embedded


def test_embed_markdown_images_inlines_local_png(tmp_path: Path) -> None:
    assets = tmp_path / "ns_assets"
    assets.mkdir()
    png = assets / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    content = "![Chart](./ns_assets/chart.png)\n"
    embedded = embed_markdown_images(content, markdown_dir=tmp_path)

    assert "data:image/png;base64," in embedded
    assert "./ns_assets/" not in embedded
