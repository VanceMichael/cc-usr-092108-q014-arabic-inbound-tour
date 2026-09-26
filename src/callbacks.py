"""供应商回调的幂等登记与跨时区报价确认。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import to_utc


@dataclass(frozen=True)
class ServiceOrder:
    order_id: str
    supplier_id: str
    idempotency_key: str
    payload: dict
    created_at: datetime  # UTC


class OrderRegistry:
    """按（供应商, 幂等键）登记订单；重复回调返回原单，绝不生成双单。"""

    def __init__(self) -> None:
        self._orders: dict[tuple[str, str], ServiceOrder] = {}
        self._seq = 0

    def confirm_callback(
        self,
        supplier_id: str,
        idempotency_key: str,
        payload: dict,
        received_at: datetime,
    ) -> tuple[ServiceOrder, bool]:
        """返回（订单, 是否新建）。重复回调拿到原订单且 created=False。"""
        key = (supplier_id, idempotency_key)
        existing = self._orders.get(key)
        if existing is not None:
            return existing, False
        self._seq += 1
        order = ServiceOrder(
            order_id=f"ord-{self._seq:04d}",
            supplier_id=supplier_id,
            idempotency_key=idempotency_key,
            payload=dict(payload),
            created_at=to_utc(received_at),
        )
        self._orders[key] = order
        return order, True

    def count(self) -> int:
        return len(self._orders)


@dataclass(frozen=True)
class Quote:
    """报价：现场口头报价在关键条件（如回程航班）确认前可能失效，有效期一律按 UTC 判定。"""

    quote_id: str
    issued_at: datetime
    valid_until: datetime
    pending_conditions: tuple[str, ...]

    def is_actionable(self, at: datetime) -> bool:
        return to_utc(at) <= to_utc(self.valid_until)

    def confirm(self, at: datetime) -> None:
        if not self.is_actionable(at):
            raise ValueError("报价已失效，需重新询价")
