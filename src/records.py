"""加载履约资料包（一组分层 JSON）。"""

import json
from pathlib import Path
from typing import Any

# 资料键 -> 文件名；成员关系、证件、偏好、无障碍、授权分文件保存。
BOOKING_FILES = {
    "family": "family.json",
    "documents": "documents.json",
    "preferences": "preferences.json",
    "accessibility": "accessibility.json",
    "consents": "consents.json",
    "suppliers": "suppliers.json",
    "route": "route.json",
    "quotes": "quote_samples.json",
    "plan": "plan_versions.json",
    "contract": "contract_terms.json",
    "settlement": "settlement.json",
    "callbacks": "callbacks.json",
    "arabic": "arabic_content.json",
    "prayer": "prayer_schedule.json",
    "commitments": "commitments.json",
    "events": "event_log.json",
    "itinerary": "guest_itinerary.json",
    "capabilities": "service_capabilities.json",
}


def load_booking(directory: Path) -> dict[str, Any]:
    """读取并解析整个履约资料包。"""
    directory = Path(directory)
    bundle: dict[str, Any] = {}
    for key, filename in BOOKING_FILES.items():
        path = directory / filename
        if not path.exists():
            raise FileNotFoundError(f"履约资料缺少文件: {filename}")
        bundle[key] = json.loads(path.read_text(encoding="utf-8"))
    return bundle
