"""服务能力沉淀的去标识化检查：能力库不得含可重新识别个人的信息。"""

import re
from typing import Any

# 能力库禁止出现的模式：真实姓名样式、证件号、电话、订单号、精确日期等。
FORBIDDEN_PATTERNS = {
    "person_name_token": re.compile(r"\b[A-Z]{3,}_[A-Z]{3,}\b"),          # 样例成员代号形如 OMAR_AL_MANSOURI_S
    "passport_like": re.compile(r"P-AE-\*+\d+"),
    "phone_like": re.compile(r"\+\d{2}-\d{2,}-[\dX-]{4,}"),
    "order_id": re.compile(r"\bORD-[A-Z]+-\d+"),
    "event_id": re.compile(r"\bEVT-\d{4}-\d{2}\b"),
    "exact_date": re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    "family_id": re.compile(r"\bFAM-\d{4}-[A-Z]{3}\b"),
    "email_like": re.compile(r"[\w.]+@[\w.]+"),
}


def _walk_strings(node: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, str):
        found.append((path, node))
    elif isinstance(node, dict):
        for key, value in node.items():
            found.extend(_walk_strings(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(_walk_strings(value, f"{path}[{i}]"))
    return found


def scan_for_pii(capabilities: dict) -> list[str]:
    """返回能力库中所有疑似个人信息；空列表表示可安全沉淀。"""
    findings: list[str] = []
    for path, text in _walk_strings(capabilities):
        for name, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path}: 命中禁止模式 {name}: {text[:60]}")
    return findings
