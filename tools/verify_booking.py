"""端到端校验履约资料包：用法 python -m tools.verify_booking [目录]。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.records import load_booking
from src.documents import verification_gate
from src.privacy import views_for_all_suppliers
from src.pricing import diff_between, expired_quotes, plan_version, availability_gaps, quote_status
from src.schedule import detect_conflicts, conflict_dates_resolved
from src.orders import process_callbacks
from src.content import review_gate_errors
from src.commitments import verify_commitments
from src.evidence import verify_event_chain
from src.itinerary import verify_guest_itinerary
from src.capabilities import scan_for_pii

from datetime import datetime, timezone


def verify(directory: Path) -> list[str]:
    bundle = load_booking(directory)
    errors: list[str] = []

    gate = verification_gate(bundle["documents"])
    if not gate["ticketing_allowed"]:
        errors.append(f"证件核验未通过，阻断成员: {gate['blocked_guests']}")

    errors.extend(f"阿语审校: {e}" for e in review_gate_errors(bundle["arabic"]))
    errors.extend(f"承诺台账: {e}" for e in verify_commitments(bundle))
    errors.extend(f"事件链: {e}" for e in verify_event_chain(bundle["events"]))
    errors.extend(f"行程一致: {e}" for e in verify_guest_itinerary(bundle))
    errors.extend(f"能力沉淀: {e}" for e in scan_for_pii(bundle["capabilities"]))

    conflicts = detect_conflicts(bundle["prayer"])
    resolved = conflict_dates_resolved(bundle["prayer"])
    for c in conflicts:
        if c["date"] not in resolved:
            errors.append(f"未解决的礼拜/餐饮冲突: {c}")

    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    expired = expired_quotes(bundle["quotes"], now)
    v3 = plan_version(bundle, 3)
    if availability_gaps(v3):
        errors.append(f"最终方案仍有未确认资源: {availability_gaps(v3)}")
    diff_between(bundle, 2, 3)  # 改版差异可算且合计自洽，否则抛异常

    result = process_callbacks(bundle["callbacks"])
    if result["order_count"] == 0 or result["suppressed_events"] != ["CB-7702", "CB-7703"]:
        errors.append(f"回调幂等结果异常: {result}")

    views = views_for_all_suppliers(bundle)
    if "display_name" in str(views.get("SUP-MEAL")):
        errors.append("餐饮供应商视图不应包含姓名")

    return errors, {"expired_quotes": [q["quote_id"] for q in expired], "conflicts": conflicts, "orders": result}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/booking")
    errs, summary = verify(target)
    print("校验摘要:", summary)
    if errs:
        print("发现问题:")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    print("履约资料包全部规则通过。")
