"""成员资料分库存储、按服务目的最小披露与证件预警。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MemberProfile:
    """同一成员的各类资料按类别分开保存：关系、证件核验、偏好、无障碍、授权。"""

    member_id: str
    relation: dict
    document_check: dict
    preferences: dict
    accessibility: dict
    authorizations: dict


# 各服务目的允许披露的（分库, 字段）清单——合作方只收到完成服务所需的信息
DISCLOSURE_MATRIX: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "visa": (
        ("document_check", ("passport_valid", "expires_on", "visa_status", "result")),
        ("relation", ("role", "guardian_of")),
    ),
    "hotel": (
        ("relation", ("age_band", "room_with")),
        ("accessibility", ("needs",)),
    ),
    "halal_meals": (
        ("preferences", ("dietary", "allergies", "meal_notes")),
    ),
    "guide": (
        ("preferences", ("language",)),
        ("accessibility", ("needs",)),
    ),
    "activities": (
        ("relation", ("age_band",)),
        ("accessibility", ("needs",)),
        ("preferences", ("interests",)),
    ),
}


class MemberVault:
    """分库保存成员资料；披露按服务目的裁剪，并受成员授权范围约束。"""

    def __init__(self) -> None:
        self._stores: dict[str, dict[str, dict]] = {
            "relation": {},
            "document_check": {},
            "preferences": {},
            "accessibility": {},
            "authorizations": {},
        }

    def store(self, profile: MemberProfile) -> None:
        self._stores["relation"][profile.member_id] = dict(profile.relation)
        self._stores["document_check"][profile.member_id] = dict(profile.document_check)
        self._stores["preferences"][profile.member_id] = dict(profile.preferences)
        self._stores["accessibility"][profile.member_id] = dict(profile.accessibility)
        self._stores["authorizations"][profile.member_id] = dict(profile.authorizations)

    def disclose(self, member_id: str, purpose: str) -> dict:
        """按服务目的返回裁剪后的资料；目的未知或成员未授权时拒绝。"""
        if purpose not in DISCLOSURE_MATRIX:
            raise PermissionError(f"未知服务目的：{purpose}")
        grants = self._stores["authorizations"].get(member_id, {}).get("data_sharing", {})
        if not grants.get(purpose, False):
            raise PermissionError(f"成员 {member_id} 未授权 {purpose} 用途的资料共享")
        bundle: dict[str, dict] = {}
        for store_name, fields in DISCLOSURE_MATRIX[purpose]:
            record = self._stores[store_name].get(member_id, {})
            picked = {key: record[key] for key in fields if key in record}
            if picked:
                bundle[store_name] = picked
        return bundle


def document_warnings(
    profile: MemberProfile, departure: date, min_valid_months: int = 6
) -> list[str]:
    """出发前检查证件核验结果，提前给出预警。"""
    warnings: list[str] = []
    check = profile.document_check
    expiry = date.fromisoformat(check["expires_on"])
    month = departure.month + min_valid_months
    year = departure.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    threshold = date(year, month, min(departure.day, 28))
    if expiry < threshold:
        warnings.append(f"{profile.member_id} 证件有效期不足 {min_valid_months} 个月")
    if check.get("visa_status") != "verified":
        warnings.append(f"{profile.member_id} 签证核验未完成")
    return warnings
