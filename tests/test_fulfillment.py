import json
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.audit import AuditLog, Commitment, CommitmentLedger
from src.callbacks import OrderRegistry, Quote
from src.capability import CapabilityRecord, distill_capability
from src.conflicts import TimeWindow, detect_conflicts
from src.itinerary import (
    ItineraryBook,
    ItineraryItem,
    ItineraryVersion,
    diff_versions,
)
from src.models import Currency, Money
from src.privacy import MemberProfile, MemberVault, document_warnings
from src.review import ArabicContent, ReviewStatus, approve, publish_blockers, reject, submit
from src.settlement import (
    ContractTerms,
    ReplacementCause,
    cancellation_refund,
    deposit_due,
    partial_participation_refund,
    supplier_replacement,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_version(raw: dict) -> ItineraryVersion:
    items = [
        ItineraryItem(
            item_id=row["item_id"],
            day=row["day"],
            title=row["title"],
            supplier_id=row["supplier_id"],
            start=datetime.fromisoformat(row["start"]),
            end=datetime.fromisoformat(row["end"]),
            price=Money(row["price"]["amount"], Currency(row["price"]["currency"])),
            available=row["available"],
        )
        for row in raw["items"]
    ]
    return ItineraryVersion(
        version=raw["version"],
        items=items,
        created_at=datetime.fromisoformat(raw["created_at"]),
    )


class PrivacyTest(unittest.TestCase):
    def setUp(self):
        family = load("family.json")
        self.members = {row["member_id"]: row for row in family["members"]}

    def test_minimum_disclosure_hotel_omits_documents(self):
        row = self.members["m3"]  # 坐轮椅的祖父
        vault = MemberVault()
        vault.store(MemberProfile("m3", **{k: row[k] for k in
                     ("relation", "document_check", "preferences",
                      "accessibility", "authorizations")}))
        bundle = vault.disclose("m3", "hotel")
        # 酒店只拿到排房与无障碍需要，看不到证件与饮食细节
        self.assertNotIn("document_check", bundle)
        self.assertIn("轮椅通道", bundle["accessibility"]["needs"])
        self.assertNotIn("dietary", bundle.get("preferences", {}))

    def test_halal_supplier_sees_allergies_only(self):
        row = self.members["m6"]  # 坚果过敏儿童
        vault = MemberVault()
        vault.store(MemberProfile("m6", **{k: row[k] for k in
                     ("relation", "document_check", "preferences",
                      "accessibility", "authorizations")}))
        bundle = vault.disclose("m6", "halal_meals")
        self.assertEqual(bundle["preferences"]["allergies"], ["坚果"])
        self.assertNotIn("document_check", bundle)

    def test_unauthorized_purpose_is_refused(self):
        row = self.members["m5"]  # 家长未授权活动用途
        vault = MemberVault()
        vault.store(MemberProfile("m5", **{k: row[k] for k in
                     ("relation", "document_check", "preferences",
                      "accessibility", "authorizations")}))
        with self.assertRaises(PermissionError):
            vault.disclose("m5", "activities")
        with self.assertRaises(PermissionError):
            vault.disclose("m5", "unknown_purpose")

    def test_document_warnings_for_expiry_and_visa(self):
        row = self.members["m8"]  # 证件 2027-02 到期、签证 pending
        profile = MemberProfile("m8", **{k: row[k] for k in
                          ("relation", "document_check", "preferences",
                           "accessibility", "authorizations")})
        warnings = document_warnings(profile, date(2026, 11, 10))
        self.assertTrue(any("不足 6 个月" in w for w in warnings))
        self.assertTrue(any("签证核验未完成" in w for w in warnings))


class ItineraryTest(unittest.TestCase):
    def test_version_diff_shows_price_and_availability_changes(self):
        v1 = build_version(load("itinerary_v1.json"))
        v2 = build_version(load("itinerary_v2.json"))
        self.assertAlmostEqual(v1.total(Currency.CNY).amount, 19300.0)
        # 不可用项目不计入合计
        self.assertAlmostEqual(v2.total(Currency.CNY).amount, 19500.0)
        diff = diff_versions(v1, v2, Currency.CNY)
        kinds = {change.item_id: change.kind for change in diff.changes}
        self.assertEqual(kinds["d1-hotel"], "price_changed")
        self.assertEqual(kinds["d4-activity"], "availability_changed")
        self.assertEqual(kinds["d4-activity-b"], "added")
        self.assertAlmostEqual(diff.price_delta.amount, 200.0)

    def test_guest_view_always_points_to_single_confirmed_version(self):
        v1 = build_version(load("itinerary_v1.json"))
        v2 = build_version(load("itinerary_v2.json"))
        book = ItineraryBook()
        book.add_version(v1)
        book.add_version(v2)
        book.confirm(1, datetime(2026, 9, 27, 12, tzinfo=timezone.utc))
        self.assertEqual(book.guest_view().version, 1)
        book.confirm(2, datetime(2026, 9, 28, 2, tzinfo=timezone.utc))
        self.assertEqual(book.guest_view().version, 2)
        self.assertEqual(v1.status, "superseded")
        with self.assertRaises(KeyError):
            book.confirm(9, datetime(2026, 9, 28, 3, tzinfo=timezone.utc))


class CallbackTest(unittest.TestCase):
    T0 = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)

    def test_duplicate_callback_does_not_create_double_order(self):
        registry = OrderRegistry()
        first, created1 = registry.confirm_callback("sup-hotel", "cb-77", {"rooms": 4}, self.T0)
        second, created2 = registry.confirm_callback("sup-hotel", "cb-77", {"rooms": 4}, self.T0)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first.order_id, second.order_id)
        self.assertEqual(registry.count(), 1)

    def test_same_key_from_different_suppliers_are_distinct(self):
        registry = OrderRegistry()
        registry.confirm_callback("sup-a", "k1", {}, self.T0)
        _, created = registry.confirm_callback("sup-b", "k1", {}, self.T0)
        self.assertTrue(created)
        self.assertEqual(registry.count(), 2)

    def test_quote_validity_judged_in_utc_across_timezones(self):
        raw = load("quote.json")
        quote = Quote(
            quote_id=raw["quote_id"],
            issued_at=datetime.fromisoformat(raw["issued_at"]),
            valid_until=datetime.fromisoformat(raw["valid_until"]),
            pending_conditions=tuple(raw["pending_conditions"]),
        )
        # 迪拜时间 20:00（UTC+4）即 UTC 16:00，恰在有效期边界内
        dubai = timezone(timedelta(hours=4))
        self.assertTrue(quote.is_actionable(datetime(2026, 9, 28, 20, 0, tzinfo=dubai)))
        # 重庆时间 2026-09-29 00:30（UTC+8）即 UTC 16:30，报价已失效
        chongqing = timezone(timedelta(hours=8))
        self.assertFalse(quote.is_actionable(datetime(2026, 9, 29, 0, 30, tzinfo=chongqing)))
        with self.assertRaises(ValueError):
            quote.confirm(datetime(2026, 9, 29, 0, 30, tzinfo=chongqing))

    def test_naive_datetime_rejected(self):
        registry = OrderRegistry()
        with self.assertRaises(ValueError):
            registry.confirm_callback("sup-a", "k", {}, datetime(2026, 9, 27, 12, 0))


class SettlementTest(unittest.TestCase):
    TERMS = ContractTerms()
    CNY = Currency.CNY

    def test_deposit_and_cancellation_tiers(self):
        total = Money(10000.0, self.CNY)
        self.assertAlmostEqual(deposit_due(total, self.TERMS).amount, 3000.0)
        self.assertAlmostEqual(cancellation_refund(total, 40, self.TERMS).amount, 9500.0)
        self.assertAlmostEqual(cancellation_refund(total, 20, self.TERMS).amount, 5000.0)
        self.assertAlmostEqual(cancellation_refund(total, 3, self.TERMS).amount, 0.0)

    def test_partial_participation_requires_notice(self):
        per_day = Money(500.0, self.CNY)
        self.assertAlmostEqual(
            partial_participation_refund(per_day, 2, 72, self.TERMS).amount, 600.0)
        self.assertAlmostEqual(
            partial_participation_refund(per_day, 2, 12, self.TERMS).amount, 0.0)

    def test_supplier_fault_absorbs_price_difference(self):
        old = Money(2800.0, self.CNY)
        new = Money(3300.0, self.CNY)
        result = supplier_replacement(old, new, ReplacementCause.SUPPLIER_FAULT)
        self.assertAlmostEqual(result.agency_absorbs.amount, 500.0)
        self.assertAlmostEqual(result.guest_pays.amount, 2800.0)

    def test_guest_request_settles_the_difference(self):
        old = Money(2800.0, self.CNY)
        cheaper = Money(2200.0, self.CNY)
        result = supplier_replacement(old, cheaper, ReplacementCause.GUEST_REQUEST)
        self.assertAlmostEqual(result.refund_to_guest.amount, 600.0)
        pricier = Money(3000.0, self.CNY)
        result2 = supplier_replacement(old, pricier, ReplacementCause.GUEST_REQUEST)
        self.assertAlmostEqual(result2.guest_pays.amount, 3000.0)

    def test_currency_mismatch_blocks_addition(self):
        with self.assertRaises(ValueError):
            Money(100.0, Currency.CNY).plus(Money(100.0, Currency.AED))
        converted = Money(100.0, Currency.AED).convert(1.95, Currency.CNY)
        self.assertEqual(converted.currency, Currency.CNY)
        self.assertAlmostEqual(converted.amount, 195.0)


class ReviewAndConflictTest(unittest.TestCase):
    def test_arabic_content_requires_independent_review(self):
        content = ArabicContent("c1", "阿语编辑A", "مرحبا بكم في تشونغتشينغ")
        self.assertIn("c1", publish_blockers([content]))
        submit(content)
        with self.assertRaises(PermissionError):
            approve(content, "阿语编辑A")
        approve(content, "阿语审校B")
        self.assertEqual(publish_blockers([content]), [])
        rejected = ArabicContent("c2", "阿语编辑A", "نص آخر")
        submit(rejected)
        reject(rejected, "阿语审校B", "拼写错误")
        self.assertEqual(rejected.status, ReviewStatus.REJECTED)
        self.assertIn("c2", publish_blockers([rejected]))

    def test_prayer_and_meal_conflicts_detected_beforehand(self):
        # 2026-11-11 重庆（UTC+8）：索道 14:00–16:00 与 Asr 15:50–16:20 重叠
        cst = timezone(timedelta(hours=8))
        raw = load("chongqing_windows.json")["dates"]["2026-11-11"]
        windows = [
            TimeWindow(w["name"], kind,
                       datetime.fromisoformat(f"2026-11-11T{w['start']}:00").replace(tzinfo=cst),
                       datetime.fromisoformat(f"2026-11-11T{w['end']}:00").replace(tzinfo=cst))
            for kind in ("prayer", "meal") for w in raw[kind]
        ]
        items = build_version(load("itinerary_v1.json")).items
        day2 = [item for item in items if item.day == 2]
        conflicts = detect_conflicts(day2, windows, buffer_minutes=10)
        kinds = {(c.item_id, c.window_name) for c in conflicts}
        self.assertIn(("d2-activity", "Asr"), kinds)
        self.assertFalse(any(item_id == "d2-guide" for item_id, _ in kinds))
        self.assertTrue(all(c.kind in {"prayer", "meal"} for c in conflicts))


class AuditAndCapabilityTest(unittest.TestCase):
    TZ = timezone.utc

    def _ledger(self):
        audit = AuditLog()
        ledger = CommitmentLedger(audit)
        return audit, ledger

    def test_commitment_carries_confirmer_and_fulfillment(self):
        audit, ledger = self._ledger()
        c = Commitment("cm-1", "提供阿拉伯语向导全程", "sup-guide")
        ledger.add(c, "业务负责人", datetime(2026, 9, 27, 8, tzinfo=self.TZ))
        ledger.confirm("cm-1", "执行人员-李", datetime(2026, 9, 28, 2, tzinfo=self.TZ))
        ledger.record_fulfillment("cm-1", "fulfilled", "向导按时上岗，客人满意",
                                  "执行人员-李", datetime(2026, 11, 15, 8, tzinfo=self.TZ))
        self.assertEqual(ledger.get("cm-1").confirmed_by, "执行人员-李")
        trace = audit.trace("commitment_id", "cm-1")
        self.assertEqual([e.kind for e in trace],
                         ["commitment_added", "commitment_confirmed", "fulfillment_recorded"])
        self.assertTrue(audit.verify())

    def test_unconfirmed_commitment_cannot_record_fulfillment(self):
        _, ledger = self._ledger()
        ledger.add(Commitment("cm-2", "X", "sup-x"),
                   "业务负责人", datetime(2026, 9, 27, 8, tzinfo=self.TZ))
        with self.assertRaises(ValueError):
            ledger.record_fulfillment("cm-2", "fulfilled", "-",
                                      "执行人员", datetime(2026, 11, 15, tzinfo=self.TZ))

    def test_complaint_and_emergency_contact_are_traceable(self):
        audit, _ = self._ledger()
        audit.record("emergency_contact", "值班经理",
                     datetime(2026, 11, 13, 10, 5, tzinfo=self.TZ),
                     {"incident_id": "inc-7"}, "祖父需就近无障碍厕所，已协调酒店")
        audit.record("complaint_filed", "客人(户主)",
                     datetime(2026, 11, 13, 12, 0, tzinfo=self.TZ),
                     {"incident_id": "inc-7", "supplier_id": "sup-activities"},
                     "武隆车辆无轮椅固定装置")
        audit.record("complaint_resolved", "业务负责人",
                     datetime(2026, 11, 13, 15, 30, tzinfo=self.TZ),
                     {"incident_id": "inc-7"}, "更换无障碍车辆并补偿当日活动")
        events = audit.trace("incident_id", "inc-7")
        self.assertEqual(len(events), 3)
        self.assertTrue(audit.verify())

    def test_tampering_is_detected(self):
        audit, ledger = self._ledger()
        ledger.add(Commitment("cm-3", "X", "sup-x"),
                   "业务负责人", datetime(2026, 9, 27, 8, tzinfo=self.TZ))
        audit._events[0].detail = "被篡改"
        self.assertFalse(audit.verify())

    def test_distilled_capability_has_no_personal_data(self):
        commitment = Commitment("cm-4", "无障碍车辆 8 人家庭", "sup-activities")
        commitment.confirmed_by = "执行人员-李"
        commitment.fulfillment = "fulfilled"
        record = distill_capability(commitment, {
            "supplier_category": "activities",
            "city": "重庆",
            "party_size": 8,
            "language": "ar",
            "service_tags": ("无障碍车辆", "分龄活动"),
            "lead_time_days": 7,
            "service_month": "2026-11",
        })
        self.assertEqual(record.party_size_band, "family")
        self.assertTrue(record.fulfilled_on_time)
        payload = record.__dict__
        self.assertFalse(any(k in payload for k in
                             ("member_id", "family_id", "name", "passport")))
        with self.assertRaises(ValueError):
            distill_capability(commitment, {
                "supplier_category": "activities", "city": "重庆", "party_size": 8,
                "language": "ar", "lead_time_days": 7,
                "service_month": "2026-11", "member_id": "m1"})


if __name__ == "__main__":
    unittest.main()
