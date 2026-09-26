"""阿拉伯语内容审校：未经审校通过的内容不得面向客人发布。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ArabicContent:
    content_id: str
    author: str
    text: str
    status: ReviewStatus = ReviewStatus.DRAFT
    reviewer: str | None = None
    note: str | None = None


def submit(content: ArabicContent) -> None:
    content.status = ReviewStatus.SUBMITTED


def _reviewable(content: ArabicContent, reviewer: str) -> None:
    if content.status is not ReviewStatus.SUBMITTED:
        raise ValueError("内容未送审")
    if reviewer == content.author:
        raise PermissionError("审校人不能是作者本人")


def approve(content: ArabicContent, reviewer: str) -> None:
    """审校须由作者以外的人完成。"""
    _reviewable(content, reviewer)
    content.status = ReviewStatus.APPROVED
    content.reviewer = reviewer


def reject(content: ArabicContent, reviewer: str, note: str) -> None:
    _reviewable(content, reviewer)
    content.status = ReviewStatus.REJECTED
    content.reviewer = reviewer
    content.note = note


def guest_safe(content: ArabicContent) -> bool:
    return content.status is ReviewStatus.APPROVED


def publish_blockers(contents: list[ArabicContent]) -> list[str]:
    """返回仍未通过审校、阻止发布的内容编号。"""
    return [c.content_id for c in contents if not guest_safe(c)]
