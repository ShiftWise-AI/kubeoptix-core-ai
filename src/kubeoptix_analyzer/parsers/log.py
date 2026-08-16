"""Parser de logs de pods (texto plano)."""

from __future__ import annotations

import re
from pathlib import Path

from kubeoptix_analyzer.models.inventory import PodLogSummary

_LOG_LEVEL_RE = re.compile(r"\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|TRACE)\b")
_RUNTIME_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "oracle.jdbc": re.compile(r"oracle\.jdbc\.driver"),
}
_MAX_LINES = 5000


def _detect_runtime_signals(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for signal_id, pattern in _RUNTIME_SIGNAL_PATTERNS.items():
        if pattern.search(text):
            found.append(signal_id)
    return tuple(sorted(found))


def parse_pod_log(file_path: Path, *, app_group: str | None = None) -> PodLogSummary:
    group = app_group or file_path.parent.parent.name
    pod_name = file_path.stem

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    lines = text.splitlines()
    if len(lines) > _MAX_LINES:
        lines = lines[:_MAX_LINES]

    if not lines or not text.strip():
        return PodLogSummary(
            app_group=group,
            pod_name=pod_name,
            file_path=str(file_path),
            line_count=0,
            levels={},
            empty=True,
        )

    levels: dict[str, int] = {}
    for line in lines:
        for match in _LOG_LEVEL_RE.finditer(line):
            level = match.group(1)
            if level == "WARNING":
                level = "WARN"
            levels[level] = levels.get(level, 0) + 1

    return PodLogSummary(
        app_group=group,
        pod_name=pod_name,
        file_path=str(file_path),
        line_count=len(lines),
        levels=levels,
        empty=False,
        runtime_signals=_detect_runtime_signals(text),
    )
