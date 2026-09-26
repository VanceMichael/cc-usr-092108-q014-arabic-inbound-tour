"""证件核验门禁：全部成员通过核验前不得出票/锁单。"""

from typing import Any

BLOCKING_STATUSES = {"pending", "fail"}


def verification_gate(documents: dict) -> dict[str, Any]:
    """汇总每位成员的最终核验状态；任何阻断状态都会阻止出票。"""
    blocked: list[str] = []
    resolved: list[str] = []
    for record in documents["records"]:
        history = record.get("history", [])
        latest = history[-1]["result"] if history else "pending"
        if record["status"] in BLOCKING_STATUSES or latest in BLOCKING_STATUSES:
            blocked.append(record["guest_id"])
        elif record["status"] == "exception_resolved":
            resolved.append(record["guest_id"])
    return {
        "all_verified": not blocked,
        "blocked_guests": blocked,
        "exception_resolved": resolved,
        "ticketing_allowed": not blocked,
    }
