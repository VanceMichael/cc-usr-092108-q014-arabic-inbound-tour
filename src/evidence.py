"""事件链与投诉证据追溯。"""

from typing import Any


def verify_event_chain(events: dict) -> list[str]:
    """事件只追加、编号唯一；投诉必须挂接事件，赔付必须挂接投诉处理。"""
    errors: list[str] = []
    seen: set[str] = set()
    by_id: dict[str, dict] = {}
    for e in events["events"]:
        eid = e["event_id"]
        if eid in seen:
            errors.append(f"事件 {eid} 重复，违反 append-only")
        seen.add(eid)
        by_id[eid] = e
        if e["type"] == "complaint" and not e.get("linked_event"):
            errors.append(f"投诉 {eid} 未挂接事件，证据不可追溯")
        if e["type"] == "complaint_resolution" and not e.get("linked_event"):
            errors.append(f"处理记录 {eid} 未挂接投诉")
    for e in events["events"]:
        linked = e.get("linked_event")
        if linked and linked not in by_id:
            errors.append(f"{e['event_id']} 引用了不存在的事件 {linked}")
    return errors


def complaint_evidence(events: dict, complaint_event_id: str) -> dict[str, Any]:
    """汇总一条投诉的完整证据链：起因事件、处理记录、承诺关联。"""
    by_id = {e["event_id"]: e for e in events["events"]}
    complaint = by_id.get(complaint_event_id)
    if not complaint or complaint["type"] != "complaint":
        raise KeyError(f"不是投诉事件: {complaint_event_id}")
    root = by_id[complaint["linked_event"]]
    resolutions = [
        e for e in events["events"]
        if e["type"] == "complaint_resolution" and e.get("linked_event") == complaint_event_id
    ]
    return {
        "complaint": complaint,
        "root_event": root,
        "resolutions": resolutions,
        "commitment_id": root.get("commitment_id"),
    }
