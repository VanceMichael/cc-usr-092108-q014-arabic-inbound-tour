"""行程版本管理：每次改版给出价格与可用性变化，客人始终持有一份一致行程。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Currency, Money, to_utc


@dataclass(frozen=True)
class ItineraryItem:
    item_id: str
    day: int
    title: str
    supplier_id: str
    start: datetime
    end: datetime
    price: Money
    available: bool = True


@dataclass
class ItineraryVersion:
    version: int
    items: list[ItineraryItem]
    created_at: datetime
    status: str = "draft"  # draft → confirmed → superseded

    def total(self, currency: Currency) -> Money:
        """当前可用项目的合计价格。"""
        amount = sum(
            item.price.amount
            for item in self.items
            if item.available and item.price.currency == currency
        )
        return Money(round(amount, 2), currency)


@dataclass(frozen=True)
class ItemChange:
    item_id: str
    title: str
    kind: str  # price_changed / availability_changed / added / removed
    before: str
    after: str


@dataclass(frozen=True)
class VersionDiff:
    from_version: int
    to_version: int
    price_delta: Money
    changes: tuple[ItemChange, ...]

    def changes_of(self, kind: str) -> tuple[ItemChange, ...]:
        return tuple(change for change in self.changes if change.kind == kind)


def _describe(item: ItineraryItem) -> str:
    state = "可用" if item.available else "不可用"
    return f"{item.price.amount:.2f} {item.price.currency.value}（{state}）"


def diff_versions(
    old: ItineraryVersion, new: ItineraryVersion, currency: Currency
) -> VersionDiff:
    """比较两版行程，列出价格差额与逐项价格、可用性变化。"""
    before = {item.item_id: item for item in old.items}
    after = {item.item_id: item for item in new.items}
    changes: list[ItemChange] = []
    for item_id, item in after.items():
        if item_id not in before:
            changes.append(ItemChange(item_id, item.title, "added", "-", _describe(item)))
            continue
        previous = before[item_id]
        if previous.price != item.price:
            changes.append(
                ItemChange(item_id, item.title, "price_changed",
                           _describe(previous), _describe(item))
            )
        if previous.available != item.available:
            changes.append(
                ItemChange(item_id, item.title, "availability_changed",
                           "可用" if previous.available else "不可用",
                           "可用" if item.available else "不可用")
            )
    for item_id, item in before.items():
        if item_id not in after:
            changes.append(ItemChange(item_id, item.title, "removed", _describe(item), "-"))
    delta = new.total(currency).minus(old.total(currency))
    return VersionDiff(old.version, new.version, delta, tuple(changes))


class ItineraryBook:
    """行程版本簿：客人视图永远指向当前确认版本，任一时刻只有一份一致行程。"""

    def __init__(self) -> None:
        self._versions: list[ItineraryVersion] = []
        self._current: int | None = None

    def add_version(self, version: ItineraryVersion) -> None:
        self._versions.append(version)

    def confirm(self, version_no: int, at: datetime) -> VersionDiff | None:
        """确认新版本：旧确认版转为 superseded，返回相对上一确认版的差异。"""
        to_utc(at)
        target = next((v for v in self._versions if v.version == version_no), None)
        if target is None:
            raise KeyError(f"行程版本不存在：{version_no}")
        previous = self._versions[self._current] if self._current is not None else None
        if previous is not None:
            previous.status = "superseded"
        target.status = "confirmed"
        self._current = self._versions.index(target)
        if previous is None:
            return None
        currency = target.items[0].price.currency if target.items else Currency.CNY
        return diff_versions(previous, target, currency)

    def guest_view(self) -> ItineraryVersion:
        """客人始终持有且仅持有一份一致的当前行程。"""
        if self._current is None:
            raise LookupError("尚无已确认的行程版本")
        return self._versions[self._current]
