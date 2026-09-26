"""祈祷与饮食时间冲突的提前发现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TimeWindow:
    name: str
    kind: str  # prayer / meal
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Conflict:
    item_id: str
    window_name: str
    kind: str
    overlap_minutes: int


def detect_conflicts(items, windows, buffer_minutes: int = 10) -> list[Conflict]:
    """在方案确认前检查行程项与祈祷、用餐窗口（含缓冲）的重叠。"""
    findings: list[Conflict] = []
    margin = timedelta(minutes=buffer_minutes)
    for item in items:
        for window in windows:
            start = window.start - margin
            end = window.end + margin
            overlap = min(item.end, end) - max(item.start, start)
            minutes = int(overlap.total_seconds() // 60)
            if minutes > 0:
                findings.append(Conflict(item.item_id, window.name, window.kind, minutes))
    return findings
