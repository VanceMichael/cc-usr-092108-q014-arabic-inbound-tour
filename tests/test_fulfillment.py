import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.records import load_booking
from src.documents import verification_gate
from src.privacy import supplier_view, active_grants
from src.pricing import quote_status, quote_total, diff_between, availability_gaps, expired_quotes
from src.schedule import detect_conflicts
from src.orders import process_callbacks, idempotency_key
from src.content import review_gate_errors, content_for_guest
from src.commitments import verify_commitments
from src.evidence import verify_event_chain, complaint_evidence
from src.itinerary import verify_guest_itinerary
from src.capabilities import scan_for_pii

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "booking"


class BookingFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_booking(FIXTURE)

    def test_eight_members_with_guardianship(self):
        members = self.bundle["family"]["members"]
        self.assertEqual(len(members), 8)
        minors = [m for m in members if m["minor"]]
        self.assertEqual({m["guest_id"] for m in minors}, {"G5", "G6", "G7", "G8"})
        for m in minors:
            self.assertEqual(set(m["guardian_ids"]), {"G3", "G4"})

    def test_document_gate_blocks_then_passes_after_remedy(self):
        # 终态：G7 换照、G8 补出生证明后全部放行
        gate = verification_gate(self.bundle["documents"])
        self.assertTrue(gate["ticketing_allowed"])
        self.assertIn("G7", gate["exception_resolved"])
        self.assertEqual(gate["blocked_guests"], [])
        # 历史中必须保留 G7 曾被阻断的记录（先失败后闭环）
        g7 = next(r for r in self.bundle["documents"]["records"] if r["guest_id"] == "G7")
        self.assertEqual(g7["history"][0]["result"], "fail")

    def test_verbal_quote_expires_without_flight_confirmation(self):
        q = self.bundle["quotes"]["quote_samples"][0]
        self.assertEqual(quote_status(q, datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc)), "valid")
        self.assertEqual(quote_status(q, datetime(2026, 4, 30, tzinfo=timezone.utc)), "expired")
        # 锁定报价不因时间流逝失效
        locked = next(q for q in self.bundle["quotes"]["quote_samples"] if q["status"] == "confirmed_locked")
        self.assertEqual(quote_status(locked, datetime(2027, 1, 1, tzinfo=timezone.utc)), "confirmed_locked")

    def test_plan_revisions_show_price_and_availability_changes(self):
        changes = diff_between(self.bundle, 2, 3)
        fields = {c["field"] for c in changes}
        self.assertIn("return_flight", fields)
        self.assertIn("accessible_rooms", fields)
        air_change = next(c for c in changes if c["field"] == "components.international_air")
        self.assertEqual(air_change["after"] - air_change["before"], 1540)
        v3 = next(v for v in self.bundle["plan"]["versions"] if v["version"] == 3)
        self.assertEqual(availability_gaps(v3), [])
        v1 = next(v for v in self.bundle["plan"]["versions"] if v["version"] == 1)
        self.assertIn("return_flight", availability_gaps(v1))
        # 合计金额等于组件之和
        for q in self.bundle["quotes"]["quote_samples"]:
            self.assertEqual(quote_total(q), sum(c["amount"] for c in q["price_components"]))

    def test_minimum_disclosure_to_suppliers(self):
        meal = supplier_view(self.bundle, "SUP-MEAL")
        flat = str(meal)
        self.assertNotIn("display_name", flat)       # 餐饮方不收姓名
        self.assertNotIn("passport", flat)           # 不收证件
        codes = {c for b in meal["disclosures"] for r in b["recipients"] for c in r.get("meal_code", [])}
        self.assertIn("HALAL", codes)
        self.assertIn("NUT-FREE", codes)  # G8 坚果过敏必须传到厨房

        hotel = supplier_view(self.bundle, "SUP-HTL")
        hotel_flat = str(hotel)
        self.assertIn("rooming", hotel_flat)
        self.assertNotIn("allergy", hotel_flat)      # 酒店不需要过敏信息

        vehicle = supplier_view(self.bundle, "SUP-VEH")
        catering_purpose = [b for b in vehicle["disclosures"] if b["purpose"] == "transport_arrangement"]
        self.assertEqual(catering_purpose[0]["headcount"], 8)  # 只要人数与设备，不要姓名

        # 营销授权被明确拒绝：任何供应商视图都不含 marketing
        for view in (meal, hotel, vehicle):
            self.assertFalse(any(b["purpose"] == "marketing" for b in view["disclosures"]))

    def test_grant_expiry_scoping(self):
        grants = active_grants(self.bundle["consents"], "SUP-ACT")
        purposes = {g["purpose"] for g in grants}
        self.assertIn("activities", purposes)
        self.assertNotIn("air_ticketing", purposes)

    def test_duplicate_callbacks_across_timezones_create_one_order(self):
        result = process_callbacks(self.bundle["callbacks"])
        self.assertEqual(result["order_count"], 2)           # 机票1单 + 酒店1单
        self.assertEqual(result["suppressed_events"], ["CB-7702", "CB-7703"])
        self.assertIn("ORD-AIR-2610-18", result["orders"])
        # 三次回调同一幂等键
        keys = {idempotency_key(cb) for cb in self.bundle["callbacks"]["callbacks"] if cb["callback_id"] == "AIR-CKGDXB-1610-CONF"}
        self.assertEqual(len(keys), 1)

    def test_arabic_content_review_gate(self):
        self.assertEqual(review_gate_errors(self.bundle["arabic"]), [])
        itin = content_for_guest(self.bundle["arabic"], "AR-ITIN-01")
        self.assertEqual(itin["status"], "approved")
        # 主麻误译曾在第一轮被拦截
        first_round = itin["review_rounds"][0]
        self.assertEqual(first_round["verdict"], "changes_requested")
        self.assertIn("主麻", first_round["issues"][0]["problem"])
        with self.assertRaises(PermissionError):
            content_for_guest(self.bundle["arabic"], "AR-NOT-EXIST")

    def test_prayer_meal_conflicts_detected_in_advance(self):
        conflicts = detect_conflicts(self.bundle["prayer"])
        days = {c["date"] for c in conflicts}
        self.assertIn("2026-10-15", days)  # 午餐与晌礼重叠
        self.assertIn("2026-10-16", days)  # 主麻与大足行程
        fri = next(c for c in conflicts if c["date"] == "2026-10-16" and c["kind"] == "jumuah")
        self.assertEqual(fri["prayer"], "jumuah_khutbah")
        # 样例中每个冲突日期都给了提前解决方案
        resolved = {c["date"] for c in self.bundle["prayer"]["known_conflicts_demo"]}
        self.assertTrue(days.issubset(resolved))

    def test_commitment_ledger_and_guest_itinerary_consistent(self):
        self.assertEqual(verify_commitments(self.bundle), [])
        self.assertEqual(verify_guest_itinerary(self.bundle), [])
        # 行程单上每个承诺编号都能反查到确认人
        from src.commitments import traceable_commitments
        ledger = traceable_commitments(self.bundle)
        committed_items = [i for i in self.bundle["itinerary"]["items"] if "commitment_id" in i]
        self.assertTrue(committed_items)
        for item in committed_items:
            self.assertIn(item["commitment_id"], ledger)
            self.assertTrue(ledger[item["commitment_id"]]["confirmed_by"])

    def test_complaint_evidence_traceable(self):
        self.assertEqual(verify_event_chain(self.bundle["events"]), [])
        evidence = complaint_evidence(self.bundle["events"], "EVT-1015-04")
        self.assertEqual(evidence["commitment_id"], "CMT-003")
        self.assertTrue(evidence["resolutions"])
        self.assertEqual(evidence["root_event"]["type"], "incident")

    def test_settlement_rules_applied(self):
        types = {e["type"] for e in self.bundle["settlement"]["entries"]}
        self.assertIn("deposit", types)
        self.assertIn("supplier_replacement", types)
        replacement = next(e for e in self.bundle["settlement"]["entries"] if e["type"] == "supplier_replacement")
        self.assertEqual(replacement["price_delta"]["borne_by"], "agency")  # 平替差价旅行社承担
        self.assertIn("halal_cert_valid", replacement["replacement_checks"])

    def test_capability_library_has_no_pii(self):
        self.assertEqual(scan_for_pii(self.bundle["capabilities"]), [])

    def test_scan_detects_synthetic_pii(self):
        findings = scan_for_pii({"note": "客人 OMAR_AL_MANSOURI_S 护照 P-AE-****0977 订单 ORD-AIR-2610-18"})
        self.assertTrue(findings)


if __name__ == "__main__":
    unittest.main()
