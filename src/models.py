"""共享领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class Currency(str, Enum):
    CNY = "CNY"
    AED = "AED"


@dataclass(frozen=True)
class Money:
    """金额与币种；跨币种折算必须显式给出汇率。"""

    amount: float
    currency: Currency

    def convert(self, rate: float, to: Currency) -> "Money":
        """按 1 单位原币 = rate 单位目标币折算，保留两位小数。"""
        return Money(round(self.amount * rate, 2), to)

    def plus(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(round(self.amount + other.amount, 2), self.currency)

    def minus(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(round(self.amount - other.amount, 2), self.currency)

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("币种不一致，需先按汇率快照折算")


def to_utc(moment: datetime) -> datetime:
    """确认时间一律归一到 UTC；不带时区的裸时间视为数据错误。"""
    if moment.tzinfo is None:
        raise ValueError("时间必须携带时区，禁止裸时间")
    return moment.astimezone(timezone.utc)
