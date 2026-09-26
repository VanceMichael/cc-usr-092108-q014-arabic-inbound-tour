"""供应商回调的幂等处理：跨时区重复回调不得生成双单。"""

from typing import Any


def idempotency_key(callback: dict) -> str:
    """幂等键：资源 + 供应商 + 回调标识；与接收时区、接收顺序无关。"""
    return "|".join([
        callback["resource"],
        callback["supplier_ref"],
        callback["callback_id"],
    ])


def process_callbacks(callbacks: dict) -> dict[str, Any]:
    """按事件原始时间戳排序处理；重复键一律抑制，不产生第二张订单。"""
    events = sorted(callbacks["callbacks"], key=lambda c: c["source_timestamp"])
    orders: dict[str, str] = {}   # idempotency_key -> order_id
    suppressed: list[str] = []
    for cb in events:
        key = idempotency_key(cb)
        if key in orders:
            suppressed.append(cb["event_id"])
            continue
        if cb["effect"] == "create_order_once":
            orders[key] = cb["result_order_id"]
    return {
        "orders": sorted(orders.values()),
        "suppressed_events": suppressed,
        "order_count": len(orders),
    }
