"""Approval request objects and Telegram-ready formatting."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


APPROVAL_STATUSES = frozenset({"pending", "approved", "denied", "expired", "cancelled"})


@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    task_id: str
    agent_id: str
    requested_action: str
    risk_level: str
    external_effect: bool
    plain_english_request: str
    guardian_review: str | None
    status: str
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalError(ValueError):
    """Raised for invalid approval metadata."""


def create_approval_request(
    *,
    task_id: str,
    agent_id: str,
    requested_action: str,
    risk_level: str,
    external_effect: bool,
    plain_english_request: str,
    guardian_review: str | None = None,
    approval_id: str | None = None,
    now: datetime | None = None,
) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=approval_id or f"appr_{uuid4().hex[:10]}",
        task_id=_required(task_id, "task_id"),
        agent_id=_required(agent_id, "agent_id").lower(),
        requested_action=_required(requested_action, "requested_action"),
        risk_level=_risk(risk_level),
        external_effect=bool(external_effect),
        plain_english_request=_required(plain_english_request, "plain_english_request"),
        guardian_review=_optional_str(guardian_review),
        status="pending",
        created_at=now or datetime.now(timezone.utc),
    )


def decide_approval(request: ApprovalRequest, status: str, *, now: datetime | None = None) -> ApprovalRequest:
    target = str(status).strip().lower()
    if target not in APPROVAL_STATUSES - {"pending"}:
        raise ApprovalError(f"Invalid approval decision: {status!r}")
    if request.status != "pending":
        raise ApprovalError(f"Approval is already {request.status}")
    return replace(request, status=target, decided_at=now or datetime.now(timezone.utc))


def format_telegram_approval(request: ApprovalRequest) -> str:
    effect = "Yes" if request.external_effect else "No"
    guardian = request.guardian_review or "Sentinel review not yet attached."
    return "\n".join(
        [
            "The Synthetic Firm approval request",
            f"ID: {request.approval_id}",
            f"Task: {request.task_id}",
            f"Agent: {request.agent_id}",
            f"Risk: {request.risk_level}",
            f"External effect: {effect}",
            "",
            f"Request: {request.plain_english_request}",
            f"Sentinel: {guardian}",
            "",
            f"/approve {request.approval_id}",
            f"/deny {request.approval_id}",
            "/status",
            "/pause",
            "/budget",
        ]
    )


def approval_to_dict(request: ApprovalRequest) -> dict[str, Any]:
    result = request.__dict__.copy()
    result["created_at"] = request.created_at.isoformat()
    result["decided_at"] = request.decided_at.isoformat() if request.decided_at else None
    return result


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApprovalError(f"{name} is required")
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _risk(value: Any) -> str:
    risk = str(value or "low").strip().lower()
    if risk not in {"low", "medium", "high", "critical"}:
        raise ApprovalError(f"Invalid risk level: {value!r}")
    return risk
