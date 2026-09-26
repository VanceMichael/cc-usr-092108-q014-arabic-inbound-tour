"""阿拉伯语内容审校门禁：未通过审校的阿语内容不得对外发出。"""

from typing import Any


def approved_content(arabic: dict) -> dict[str, dict]:
    return {c["content_id"]: c for c in arabic["items"] if c["status"] == "approved"}


def review_gate_errors(arabic: dict) -> list[str]:
    """校验审校流程本身：机翻草稿必须有人工审校轮次；通过必须落在最后一轮。"""
    errors = []
    for item in arabic["items"]:
        rounds = item.get("review_rounds", [])
        if item["translation_mode"] == "mt_draft_then_human_review" and not rounds:
            errors.append(f"{item['content_id']}: 机翻草稿缺少人工审校")
        if item["status"] == "approved":
            if not rounds or rounds[-1]["verdict"] != "approved":
                errors.append(f"{item['content_id']}: 状态为 approved 但最后一轮未通过")
            else:
                for r in rounds:
                    if r["verdict"] == "changes_requested" and not r.get("issues"):
                        errors.append(f"{item['content_id']}: 要求修改却未记录问题")
    return errors


def content_for_guest(arabic: dict, content_id: str) -> dict[str, Any]:
    """客人侧只能拿到 approved 内容。"""
    approved = approved_content(arabic)
    if content_id not in approved:
        raise PermissionError(f"阿语内容 {content_id} 未通过审校，不得对客发出")
    return approved[content_id]
