"""授权范围与供应商最小披露。

合作方只收到完成服务所必需的字段；未授权（含明确拒绝营销）不产生任何披露。
"""

from typing import Any

# 抽象字段名 -> 如何从成员资料中取值（拿不到就不披露，而不是造假字段）。
def _resolve_field(field: str, member: dict, bundle: dict) -> Any:
    gid = member["guest_id"]
    household = bundle["preferences"]["household"]
    prefs = next((p for p in bundle["preferences"]["guest_preferences"] if p["guest_id"] == gid), {})
    doc = next((d for d in bundle["documents"]["records"] if d["guest_id"] == gid), {})
    need = next((n for n in bundle["accessibility"]["needs"] if n["guest_id"] == gid), None)
    room = next((r for r in household.get("rooming", []) if gid in r["guest_ids"]), None)

    if field == "display_name":
        return member["display_name"]
    if field == "sex":
        return member["sex"]
    if field == "dob":
        return {"birth_year": member["birth_year"]}
    if field == "age_band":
        return member["age_band"]
    if field == "passport_ref":
        return doc.get("replacement_doc_ref_masked", doc.get("doc_ref_masked"))
    if field == "birth_cert_ref":
        return "birth_certificate_on_file" if doc.get("doc_type", "").startswith("child") else None
    if field == "minor_guardian_relation":
        return {"minor": member["minor"], "guardian_ids": member.get("guardian_ids", [])} if member["minor"] else None
    if field == "rooming":
        return {"room": room["room"], "bed": room["bed"], "crib": room.get("crib", False)} if room else None
    if field == "accessible_room_flag":
        return bool(need and any(
            tag in " ".join(need.get("mitigations", [])) + need.get("condition", "")
            for tag in ("wheelchair", "elevator_only")
        ))
    if field == "alcohol_free":
        return household.get("alcohol_free_rooms")
    if field in ("accessibility_equipment", "accessibility_needs", "medical_notes"):
        if not need:
            return None
        if field == "medical_notes":
            return {"condition": need["condition"], "severity": need["severity"]}
        return need["mitigations"]
    if field == "child_seat":
        return "child_safety_seat" if gid == "G8" else None
    if field == "headcount":
        return None  # 按团聚合，不按人给
    if field == "dietary_tags":
        return prefs.get("dietary_tags", [])
    if field == "allergy":
        return prefs.get("allergies", [])
    if field == "meal_code":
        return _meal_codes(prefs)
    if field == "language":
        return household.get("languages")
    if field == "prayer_times_tips":
        return ["每日五时提醒", "主麻窗口"] if household.get("prayer_facility_required") else None
    if field == "photo_policy":
        return household.get("photo_policy")
    if field in ("seat_request", "bassinet_request", "emergency_contact", "contact"):
        return None  # 样例中未采集或不在本资料包
    return None


def _meal_codes(prefs: dict) -> list[str]:
    tags = prefs.get("dietary_tags", [])
    codes = ["HALAL"]
    if "gluten_free" in tags:
        codes.append("GF")
    if "tree_nut" in prefs.get("allergies", []):
        codes.append("NUT-FREE")
    if "soft_food" in tags:
        codes.append("SOFT")
    return codes


def active_grants(consents: dict, supplier_id: str) -> list[dict]:
    """返回对某供应商生效的授权（明确拒绝的不返回）。"""
    return [
        g for g in consents["grants"]
        if g.get("granted") and g["recipient_supplier_id"] in (supplier_id, "ANY")
    ]


def supplier_view(bundle: dict, supplier_id: str) -> dict:
    """生成发给某供应商的最小资料视图。"""
    members = {m["guest_id"]: m for m in bundle["family"]["members"]}
    blocks = []
    for grant in active_grants(bundle["consents"], supplier_id):
        recipients = []
        for gid in grant["guest_scope"]:
            projection = {"guest_ref": f"party/{gid}"}  # 稳定但非真实姓名的团内代号
            for field in grant["fields"]:
                value = _resolve_field(field, members[gid], bundle)
                if value is not None and value != []:
                    projection[field] = value
            recipients.append(projection)
        blocks.append({
            "purpose": grant["purpose"],
            "grant_id": grant["grant_id"],
            "basis": grant["basis"],
            "expires_at": grant["expires_at"],
            "recipients": recipients,
            "headcount": len(grant["guest_scope"]) if "headcount" in grant["fields"] else None,
        })
    return {"supplier_id": supplier_id, "disclosures": [b for b in blocks if b["recipients"]]}


def views_for_all_suppliers(bundle: dict) -> dict[str, dict]:
    return {s["supplier_id"]: supplier_view(bundle, s["supplier_id"]) for s in bundle["suppliers"]}
