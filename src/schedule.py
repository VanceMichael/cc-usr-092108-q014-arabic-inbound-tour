"""礼拜与餐饮时刻冲突的提前发现。"""

from typing import Any


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return _minutes(a_start) < _minutes(b_end) and _minutes(b_start) < _minutes(a_end)


# 每个礼拜时段与"邻近餐饮"的最小缓冲（分钟）：昏礼/晌礼前后应留出礼拜窗口。
PRAYER_WINDOWS = {
    "fajr": 0,
    "dhuhr": 20,
    "asr": 0,
    "maghrib": 10,
    "isha": 10,
    "jumuah_khutbah": 45,  # 主麻呼图白前后整体聚礼窗口
}


def detect_conflicts(prayer: dict) -> list[dict[str, Any]]:
    """对每一天求礼拜时段与餐饮时段的交集，输出冲突清单。"""
    meals_by_date = {m["date"]: m for m in prayer["meal_times"]}
    conflicts = []
    for day in prayer["prayer_times"]:
        date = day["date"]
        meals = meals_by_date.get(date, {})
        # 周五主麻聚礼替代晌礼：当日有呼图白时刻就不再单独报晌礼冲突。
        prayer_names = [n for n in PRAYER_WINDOWS if not (n == "dhuhr" and day.get("jumuah_khutbah"))]
        for prayer_name in prayer_names:
            buffer_min = PRAYER_WINDOWS[prayer_name]
            moment = day.get(prayer_name)
            if not moment:
                continue
            p_start = _minutes(moment) - buffer_min
            p_end = _minutes(moment) + (60 if prayer_name == "jumuah_khutbah" else buffer_min)
            for meal_name, window in meals.items():
                if not isinstance(window, dict) or "start" not in window:
                    continue
                m_start, m_end = _minutes(window["start"]), _minutes(window["end"])
                if m_start < p_end and p_start < m_end:
                    conflicts.append({
                        "date": date,
                        "prayer": prayer_name,
                        "prayer_at": moment,
                        "meal": meal_name,
                        "meal_window": f"{window['start']}-{window['end']}",
                        "kind": "jumuah" if prayer_name == "jumuah_khutbah" else "overlap",
                    })
    return conflicts


def conflict_dates_resolved(prayer: dict) -> set[str]:
    """样例中已知冲突都应给出书面解决安排。"""
    return {c["date"] for c in prayer.get("known_conflicts_demo", []) if c.get("resolution")}
