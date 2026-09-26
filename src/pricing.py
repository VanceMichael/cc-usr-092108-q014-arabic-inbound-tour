"""报价失效、合计与方案改版差异。"""

from datetime import datetime
from typing import Any


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def quote_status(quote: dict, now: datetime) -> str:
    """报价在锁定后保持锁定；否则到期即失效（口头报价典型场景）。"""
    if quote.get("status") == "confirmed_locked":
        return "confirmed_locked"
    expires = _parse(quote["expires_at"])
    return "valid" if now < expires else "expired"


def quote_total(quote: dict) -> int:
    return sum(c["amount"] for c in quote["price_components"])


def expired_quotes(quotes: dict, now: datetime) -> list[dict]:
    return [q for q in quotes["quote_samples"] if quote_status(q, now) == "expired"]


def plan_version(bundle: dict, number: int) -> dict[str, Any]:
    versions = {v["version"]: v for v in bundle["plan"]["versions"]}
    if number not in versions:
        raise KeyError(f"方案版本不存在: v{number}")
    return versions[number]


def diff_between(bundle: dict, old: int, new: int) -> list[dict]:
    """返回两版之间的价格与可用性变化；报价合计由组件重新算出并校验。"""
    v_old = plan_version(bundle, old)
    v_new = plan_version(bundle, new)
    recorded = next(
        (d for d in bundle["plan"]["diffs"] if d["from"] == old and d["to"] == new),
        None,
    )
    changes = recorded["changes"] if recorded else [
        {"type": "availability", "field": k, "before": v_old["availability"].get(k), "after": v_new["availability"].get(k)}
        for k in v_new["availability"]
        if v_old["availability"].get(k) != v_new["availability"].get(k)
    ]
    # 合计金额必须与报价组件一致，防止改版后口径漂移。
    for v in (v_old, v_new):
        quote = next(q for q in bundle["quotes"]["quote_samples"] if q["quote_id"] == v["based_on_quote"])
        if quote_total(quote) != v["total_amount"]:
            raise ValueError(f"方案 v{v['version']} 合计与报价组件不符")
    return changes


def availability_gaps(version: dict) -> list[str]:
    """列出尚未确认的资源；未确认即不能视为可履约。"""
    gaps = []
    for key, value in version["availability"].items():
        if value in ("pending", "tentative") or value is False:
            gaps.append(key)
        if isinstance(value, int) and value < 2 and key == "accessible_rooms":
            gaps.append("accessible_rooms_shortfall")
    return gaps
