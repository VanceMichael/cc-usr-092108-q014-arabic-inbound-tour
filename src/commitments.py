"""承诺台账与行程单一致性：每项承诺可追溯到确认人与履行结果。"""

from typing import Any


def verify_commitments(bundle: dict) -> list[str]:
    """返回一致性错误列表；空列表表示台账完整可信。"""
    errors: list[str] = []
    commitments = bundle["commitments"]["commitments"]
    event_ids = {e["event_id"] for e in bundle["events"]["events"]}
    itinerary_commitments = {
        item["commitment_id"] for item in bundle["itinerary"]["items"] if "commitment_id" in item
    }
    ledger_ids = {c["commitment_id"] for c in commitments}

    for cid in itinerary_commitments - ledger_ids:
        errors.append(f"行程单承诺 {cid} 在台账中不存在")
    for c in commitments:
        if not c.get("confirmed_by") or not c.get("confirmed_at"):
            errors.append(f"{c['commitment_id']}: 缺少确认人或确认时间")
        if c["outcome"] in ("fulfilled", "partial", "fulfilled_with_replacement") and not c.get("fulfilled_at"):
            errors.append(f"{c['commitment_id']}: 已履行但缺少履行时间")
        for ev in c.get("evidence", []):
            if ev.startswith("EVT-") and ev not in event_ids:
                errors.append(f"{c['commitment_id']}: 证据事件 {ev} 不在事件链中")
        if c["outcome"] == "fulfilled_with_replacement" and not c.get("outcome_note"):
            errors.append(f"{c['commitment_id']}: 平替履行必须记录说明")
    return errors


def traceable_commitments(bundle: dict) -> dict[str, dict]:
    """按承诺编号索引台账，供客人行程单逐项反查。"""
    return {c["commitment_id"]: c for c in bundle["commitments"]["commitments"]}
