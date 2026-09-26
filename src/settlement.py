"""依合同结算：定金、取消、部分参加与替换供应商。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Money


@dataclass(frozen=True)
class CancellationTier:
    min_days_before: int
    refund_ratio: float


@dataclass(frozen=True)
class ContractTerms:
    deposit_ratio: float = 0.30
    cancellation_tiers: tuple[CancellationTier, ...] = (
        CancellationTier(30, 0.95),
        CancellationTier(15, 0.50),
        CancellationTier(0, 0.0),
    )
    partial_refund_ratio: float = 0.60
    partial_notice_hours: int = 48


def deposit_due(total: Money, terms: ContractTerms) -> Money:
    """签约应付定金。"""
    return Money(round(total.amount * terms.deposit_ratio, 2), total.currency)


def cancellation_refund(
    paid: Money, days_before_departure: int, terms: ContractTerms
) -> Money:
    """按出发前剩余天数适用取消档位，退还已付金额的相应比例。"""
    for tier in sorted(terms.cancellation_tiers, key=lambda t: t.min_days_before, reverse=True):
        if days_before_departure >= tier.min_days_before:
            return Money(round(paid.amount * tier.refund_ratio, 2), paid.currency)
    return Money(0.0, paid.currency)


def partial_participation_refund(
    per_person_per_day: Money,
    days_missed: int,
    notice_hours: float,
    terms: ContractTerms,
) -> Money:
    """部分参加：达到提前通知时限，按未使用服务天数退还约定比例。"""
    if notice_hours < terms.partial_notice_hours:
        return Money(0.0, per_person_per_day.currency)
    amount = per_person_per_day.amount * days_missed * terms.partial_refund_ratio
    return Money(round(amount, 2), per_person_per_day.currency)


class ReplacementCause(str, Enum):
    SUPPLIER_FAULT = "supplier_fault"
    GUEST_REQUEST = "guest_request"


@dataclass(frozen=True)
class ReplacementSettlement:
    guest_pays: Money
    agency_absorbs: Money
    refund_to_guest: Money


def supplier_replacement(
    old_price: Money, new_price: Money, cause: ReplacementCause
) -> ReplacementSettlement:
    """替换供应商：供应商违约时差额由旅行社承担；客人主动要求时多退少补。"""
    zero = Money(0.0, old_price.currency)
    diff = round(new_price.amount - old_price.amount, 2)
    if cause is ReplacementCause.SUPPLIER_FAULT:
        return ReplacementSettlement(
            guest_pays=old_price,
            agency_absorbs=Money(max(diff, 0.0), old_price.currency),
            refund_to_guest=Money(max(-diff, 0.0), old_price.currency),
        )
    if diff >= 0:
        return ReplacementSettlement(guest_pays=new_price, agency_absorbs=zero,
                                     refund_to_guest=zero)
    return ReplacementSettlement(guest_pays=new_price, agency_absorbs=zero,
                                 refund_to_guest=Money(-diff, old_price.currency))
