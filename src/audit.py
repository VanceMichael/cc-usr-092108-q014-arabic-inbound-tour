"""承诺台账与证据链：每项承诺的确认人、履行结果、突发联络与投诉均可追溯。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from .models import to_utc


@dataclass
class AuditEvent:
    seq: int
    kind: str
    actor: str
    at: datetime  # UTC
    refs: dict
    detail: str
    prev_hash: str
    digest: str


class AuditLog:
    """只增不改的证据日志，条目间以摘要链接，篡改可被发现。"""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @staticmethod
    def _digest(seq: int, kind: str, actor: str, at: datetime,
                refs: dict, detail: str, prev_hash: str) -> str:
        payload = json.dumps(
            {"seq": seq, "kind": kind, "actor": actor, "at": at.isoformat(),
             "refs": refs, "detail": detail, "prev": prev_hash},
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def record(self, kind: str, actor: str, at: datetime,
               refs: dict, detail: str) -> AuditEvent:
        prev = self._events[-1].digest if self._events else "0" * 64
        seq = len(self._events) + 1
        moment = to_utc(at)
        digest = self._digest(seq, kind, actor, moment, refs, detail, prev)
        event = AuditEvent(seq, kind, actor, moment, dict(refs), detail, prev, digest)
        self._events.append(event)
        return event

    def trace(self, key: str, value: str) -> list[AuditEvent]:
        """按引用追溯全部相关证据，如某承诺或某投诉的完整经过。"""
        return [event for event in self._events if event.refs.get(key) == value]

    def verify(self) -> bool:
        prev = "0" * 64
        for event in self._events:
            if event.prev_hash != prev:
                return False
            if self._digest(event.seq, event.kind, event.actor, event.at,
                            event.refs, event.detail, event.prev_hash) != event.digest:
                return False
            prev = event.digest
        return True


@dataclass
class Commitment:
    commitment_id: str
    promise: str
    supplier_id: str
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    fulfillment: str | None = None  # fulfilled / partial / failed
    fulfillment_note: str | None = None


class CommitmentLedger:
    """每项承诺都记录确认人与履行结果，并同步写入证据日志。"""

    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit
        self._commitments: dict[str, Commitment] = {}

    def add(self, commitment: Commitment, actor: str, at: datetime) -> None:
        self._commitments[commitment.commitment_id] = commitment
        self._audit.record("commitment_added", actor, at,
                           {"commitment_id": commitment.commitment_id},
                           commitment.promise)

    def confirm(self, commitment_id: str, confirmed_by: str, at: datetime) -> None:
        commitment = self._commitments[commitment_id]
        commitment.confirmed_by = confirmed_by
        commitment.confirmed_at = to_utc(at)
        self._audit.record("commitment_confirmed", confirmed_by, at,
                           {"commitment_id": commitment_id}, commitment.promise)

    def record_fulfillment(self, commitment_id: str, result: str, note: str,
                           actor: str, at: datetime) -> None:
        commitment = self._commitments[commitment_id]
        if commitment.confirmed_by is None:
            raise ValueError("承诺尚未确认，不能登记履行结果")
        commitment.fulfillment = result
        commitment.fulfillment_note = note
        self._audit.record("fulfillment_recorded", actor, at,
                           {"commitment_id": commitment_id}, f"{result}：{note}")

    def get(self, commitment_id: str) -> Commitment:
        return self._commitments[commitment_id]

    def all(self) -> list[Commitment]:
        return list(self._commitments.values())
