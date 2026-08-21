"""Testes do pós-processamento de PNG para relatórios."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from kubeoptix_core_ai.visualization.models import (
    ChartDataset,
    ChartPoint,
    ChartSeries,
    CompositionDataset,
    PieSlice,
)
from kubeoptix_core_ai.visualization.png import PngRenderer
from kubeoptix_core_ai.visualization.png.export_config import (
    REPORT_CHART_MAX_HEIGHT_PX,
    REPORT_CHART_MAX_WIDTH_PX,
)
from kubeoptix_core_ai.visualization.png.postprocess import (
    _content_bbox,
    cap_png_dimensions,
    optimize_png_canvas,
)


def _fill_ratio(path: Path) -> float:
    with Image.open(path) as image:
        left, top, right, bottom = _content_bbox(image)
        return ((right - left) * (bottom - top)) / (image.width * image.height)


def test_optimize_png_canvas_preserves_dimensions_and_increases_fill(tmp_path: Path) -> None:
    path = tmp_path / "sparse.png"
    Image.new("RGB", (400, 300), (255, 255, 255)).save(path)
    canvas = Image.open(path)
    draw = Image.new("RGB", (80, 60), (30, 90, 200))
    canvas.paste(draw, (160, 120))
    canvas.save(path)

    before_ratio = _fill_ratio(path)
    changed = optimize_png_canvas(path)
    after_ratio = _fill_ratio(path)

    with Image.open(path) as image:
        assert image.size == (400, 300)
    assert changed is True
    assert after_ratio > before_ratio
    assert after_ratio >= 0.55


def test_optimize_png_canvas_skips_already_tight_canvas(tmp_path: Path) -> None:
    path = tmp_path / "tight.png"
    Image.new("RGB", (200, 100), (255, 255, 255)).save(path)
    canvas = Image.open(path)
    canvas.paste(Image.new("RGB", (196, 96), (10, 10, 10)), (2, 2))
    canvas.save(path)

    before = path.read_bytes()
    changed = optimize_png_canvas(path)
    after = path.read_bytes()

    assert changed is False
    assert before == after


def test_cap_png_dimensions_downscales_large_images(tmp_path: Path) -> None:
    path = tmp_path / "large.png"
    Image.new("RGB", (1600, 900), (10, 10, 10)).save(path)

    changed = cap_png_dimensions(
        path,
        max_width=REPORT_CHART_MAX_WIDTH_PX,
        max_height=REPORT_CHART_MAX_HEIGHT_PX,
    )

    with Image.open(path) as image:
        width, height = image.size
    assert changed is True
    assert width <= REPORT_CHART_MAX_WIDTH_PX
    assert height <= REPORT_CHART_MAX_HEIGHT_PX


def test_rendered_charts_respect_report_size_limits(tmp_path: Path) -> None:
    numeric = ChartDataset(
        title="CPU request",
        question="Test",
        x_labels=("wl-a", "wl-b", "wl-c"),
        y_axis_label="millicores",
        series=(
            ChartSeries(
                name="Request",
                points=(
                    ChartPoint(label="wl-a", value=100, unit="m"),
                    ChartPoint(label="wl-b", value=200, unit="m"),
                    ChartPoint(label="wl-c", value=150, unit="m"),
                ),
            ),
        ),
    )
    composition = CompositionDataset(
        title="QoS",
        question="Test",
        slices=(
            PieSlice(label="Burstable", value=2),
            PieSlice(label="Guaranteed", value=1),
        ),
    )
    renderer = PngRenderer(tmp_path)
    renderer.render_numeric("cpu_request", numeric)
    renderer.render_composition("qos", composition)

    for name in ("cpu_request.png", "qos.png"):
        path = tmp_path / name
        with Image.open(path) as image:
            width, height = image.size
            assert width <= REPORT_CHART_MAX_WIDTH_PX
            assert height <= REPORT_CHART_MAX_HEIGHT_PX
            fill_ratio = _fill_ratio(path)
            assert fill_ratio >= 0.35, f"{name} fill ratio too low: {fill_ratio:.2f}"
