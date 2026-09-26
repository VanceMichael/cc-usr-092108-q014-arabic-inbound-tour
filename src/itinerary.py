"""客人一致行程的校验：客人副本、路线与承诺台账三方一致。"""

from typing import Any


def verify_guest_itinerary(bundle: dict) -> list[str]:
    """返回不一致项；空列表表示客人持有的行程与履约侧完全一致。"""
    errors: list[str] = []
    itinerary = bundle["itinerary"]
    route_items = {
        item["item_id"]
        for day in bundle["route"]["days"]
        for item in day["items"]
    }
    ledger_ids = {c["commitment_id"] for c in bundle["commitments"]["commitments"]}
    route_dates = {
        item["item_id"]: day["date"]
        for day in bundle["route"]["days"]
        for item in day["items"]
    }

    if itinerary["arabic_review_status"] != "approved":
        errors.append("阿语版本未通过审校，不得作为客人一致行程发出")
    for item in itinerary["items"]:
        iid = item["item_id"]
        if iid not in route_items:
            errors.append(f"行程单项目 {iid} 不在路线中")
        elif route_dates[iid] != item["date"]:
            errors.append(f"行程单项目 {iid} 日期与路线不一致: {item['date']} != {route_dates[iid]}")
        cid = item.get("commitment_id")
        if cid and cid not in ledger_ids:
            errors.append(f"行程单承诺 {cid} 在台账中不存在")
    history = itinerary.get("revision_history", [])
    current = [h for h in history if not h["voided"]]
    if len(current) != 1 or current[0]["version"] != itinerary["version"]:
        errors.append("改版历史中应恰有一个未作废版本且等于当前版本")
    return errors
