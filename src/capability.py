"""把履约经验沉淀为不含个人资料的服务能力记录。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .audit import Commitment

# 能力记录中禁止出现的个人资料字段
FORBIDDEN_FIELDS = {"member_id", "family_id", "name", "passport", "guest", "contact"}


@dataclass(frozen=True)
class CapabilityRecord:
    supplier_category: str
    city: str
    party_size_band: str
    language: str
    service_tags: tuple[str, ...]
    lead_time_days: int
    fulfilled_on_time: bool
    complaint_count: int
    period: str  # 月份粒度，如 2026-11


def party_size_band(size: int) -> str:
    if size <= 4:
        return "small"
    if size <= 8:
        return "family"
    return "group"


def distill_capability(commitment: Commitment, meta: dict) -> CapabilityRecord:
    """由已履行承诺提炼服务能力；meta 只含服务属性，不含个人资料。"""
    if commitment.fulfillment is None:
        raise ValueError("承诺未履行，不能沉淀能力")
    _assert_no_pii(meta)
    record = CapabilityRecord(
        supplier_category=meta["supplier_category"],
        city=meta["city"],
        party_size_band=party_size_band(meta["party_size"]),
        language=meta["language"],
        service_tags=tuple(sorted(meta.get("service_tags", ()))),
        lead_time_days=meta["lead_time_days"],
        fulfilled_on_time=commitment.fulfillment == "fulfilled",
        complaint_count=meta.get("complaint_count", 0),
        period=str(meta["service_month"]),
    )
    _assert_no_pii(asdict(record))
    return record


def _assert_no_pii(payload: dict) -> None:
    for key in payload:
        if key.lower() in FORBIDDEN_FIELDS:
            raise ValueError(f"能力记录不得包含个人资料字段：{key}")
