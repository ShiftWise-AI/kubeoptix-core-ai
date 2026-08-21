"""Pós-processamento de PNGs de relatório: reduz margens excedentes preservando dimensões."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, UnidentifiedImageError

from kubeoptix_core_ai.visualization.png.export_config import (
    REPORT_CHART_MAX_HEIGHT_PX,
    REPORT_CHART_MAX_WIDTH_PX,
    REPORT_DIAGRAM_MAX_HEIGHT_PX,
    REPORT_DIAGRAM_MAX_WIDTH_PX,
)

logger = logging.getLogger(__name__)

_DEFAULT_MARGIN_RATIO = 0.012
_DEFAULT_MARGIN_MIN_PX = 3
_DEFAULT_MARGIN_MAX_PX = 12
_DEFAULT_BACKGROUND = (255, 255, 255)
_DEFAULT_WHITE_THRESHOLD = 248
_DEFAULT_ALPHA_THRESHOLD = 8
_MIN_FILL_RATIO_TO_SKIP = 0.92


def _margin_px(
    width: int,
    height: int,
    *,
    ratio: float,
    min_px: int,
    max_px: int,
) -> int:
    base = max(width, height)
    return max(min_px, min(max_px, int(base * ratio)))


def _content_bbox(
    image: Image.Image,
    *,
    white_threshold: int = _DEFAULT_WHITE_THRESHOLD,
    alpha_threshold: int = _DEFAULT_ALPHA_THRESHOLD,
) -> tuple[int, int, int, int]:
    """Retorna ``(left, top, right, bottom)`` do conteúdo não vazio."""
    rgba = np.asarray(image.convert("RGBA"))
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]

    near_white = np.all(rgb >= white_threshold, axis=2)
    transparent = alpha <= alpha_threshold
    background = near_white | transparent
    content = ~background

    if not content.any():
        return 0, 0, image.width, image.height

    rows = np.any(content, axis=1)
    cols = np.any(content, axis=0)
    top = int(np.argmax(rows))
    bottom = int(len(rows) - np.argmax(rows[::-1]))
    left = int(np.argmax(cols))
    right = int(len(cols) - np.argmax(cols[::-1]))
    return left, top, right, bottom


def optimize_png_canvas(
    path: Path,
    *,
    margin_ratio: float = _DEFAULT_MARGIN_RATIO,
    margin_min_px: int = _DEFAULT_MARGIN_MIN_PX,
    margin_max_px: int = _DEFAULT_MARGIN_MAX_PX,
    background: tuple[int, int, int] = _DEFAULT_BACKGROUND,
    min_fill_ratio_to_skip: float = _MIN_FILL_RATIO_TO_SKIP,
) -> bool:
    """
    Remove espaço vazio excedente e amplia o conteúdo proporcionalmente.

    A imagem final mantém exatamente a mesma largura e altura em pixels.
    Retorna ``True`` se a imagem foi alterada.
    """
    if not path.is_file() or path.stat().st_size <= 0:
        return False

    try:
        with Image.open(path) as source:
            orig_w, orig_h = source.size
            left, top, right, bottom = _content_bbox(source)

            content_w = right - left
            content_h = bottom - top
            if content_w <= 0 or content_h <= 0:
                return False

            fill_ratio = (content_w * content_h) / (orig_w * orig_h)
            if fill_ratio >= min_fill_ratio_to_skip:
                return False

            margin = _margin_px(
                orig_w,
                orig_h,
                ratio=margin_ratio,
                min_px=margin_min_px,
                max_px=margin_max_px,
            )
            inner_w = max(1, orig_w - 2 * margin)
            inner_h = max(1, orig_h - 2 * margin)
            scale = min(inner_w / content_w, inner_h / content_h)
            if scale <= 1.0 + 1e-6:
                return False

            cropped = source.crop((left, top, right, bottom))
            new_w = max(1, int(round(content_w * scale)))
            new_h = max(1, int(round(content_h * scale)))
            resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

            canvas = Image.new("RGB", (orig_w, orig_h), background)
            paste_x = (orig_w - new_w) // 2
            paste_y = (orig_h - new_h) // 2
            resized_rgba = resized.convert("RGBA")
            alpha_min, _alpha_max = resized_rgba.getchannel("A").getextrema()
            if alpha_min < 255:
                canvas.paste(resized_rgba, (paste_x, paste_y), resized_rgba)
            else:
                canvas.paste(resized_rgba.convert("RGB"), (paste_x, paste_y))

            canvas.save(path, format="PNG")
            return True
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        logger.debug("Ignorando pós-processamento de PNG inválido %s: %s", path, exc)
        return False


def cap_png_dimensions(
    path: Path,
    *,
    max_width: int,
    max_height: int,
) -> bool:
    """Reduz proporcionalmente PNGs acima do limite (sem ampliar imagens menores)."""
    if not path.is_file() or path.stat().st_size <= 0:
        return False

    try:
        with Image.open(path) as source:
            orig_w, orig_h = source.size
            if orig_w <= max_width and orig_h <= max_height:
                return False

            scale = min(max_width / orig_w, max_height / orig_h)
            new_w = max(1, int(round(orig_w * scale)))
            new_h = max(1, int(round(orig_h * scale)))
            resized = source.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized.save(path, format="PNG", optimize=True)
            return True
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        logger.debug("Ignorando redimensionamento de PNG inválido %s: %s", path, exc)
        return False


def finalize_report_png(
    path: Path,
    *,
    profile: Literal["chart", "diagram"] = "chart",
) -> None:
    """Normaliza margens e aplica limites de dimensão para edição Markdown/PDF."""
    optimize_png_canvas(path)
    if profile == "diagram":
        cap_png_dimensions(
            path,
            max_width=REPORT_DIAGRAM_MAX_WIDTH_PX,
            max_height=REPORT_DIAGRAM_MAX_HEIGHT_PX,
        )
        return
    cap_png_dimensions(
        path,
        max_width=REPORT_CHART_MAX_WIDTH_PX,
        max_height=REPORT_CHART_MAX_HEIGHT_PX,
    )
