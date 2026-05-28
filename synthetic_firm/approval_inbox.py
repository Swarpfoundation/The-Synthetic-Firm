"""Persistent approval inbox for founder decisions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from synthetic_firm.approval import ApprovalRequest
from synthetic_firm.approval_signing import SignedApprovalDecision, sign_approval_decision
from synthetic_firm.store import Store, StoreError
from synthetic_firm.time_utils import utc_iso, utc_now


class ApprovalInboxError(ValueError):
    """Raised when approval inbox actions fail closed."""


def approval_expires_at(approval: ApprovalRequest) -> datetime:
    return approval.created_at.astimezone(timezone.utc) + timedelta(hours=24)


def list_pending_approvals(store: Store) -> list[ApprovalRequest]:
    rows = store.connection.execute(
        "SELECT * FROM approval_requests WHERE status = 'pending' ORDER BY created_at, approval_id"
    ).fetchall()
    return [store.get_approval(row["approval_id"]) for row in rows]


def format_approval_detail(approval: ApprovalRequest) -> str:
    effect = "yes" if approval.external_effect else "no"
    sentinel = approval.guardian_review or "No Sentinel review attached yet."
    return "\n".join(
        [
            "The Synthetic Firm approval detail",
            f"Approval: {approval.approval_id}",
            f"Task: {approval.task_id}",
            f"Agent: {approval.agent_id}",
            f"Action: {approval.requested_action}",
            f"Risk: {approval.risk_level}",
            f"External effect: {effect}",
            f"Created: {approval.created_at.isoformat()}",
            f"Expires: {approval_expires_at(approval).isoformat()}",
            f"Status: {approval.status}",
            "",
            f"Request: {approval.plain_english_request}",
            f"Sentinel: {sentinel}",
        ]
    )


def decide_pending_approval(
    store: Store,
    approval_id: str,
    *,
    decision: str,
    decided_by: str,
    live: bool = True,
) -> SignedApprovalDecision:
    approval = store.get_approval(approval_id)
    latest = store.latest_approval_decision(approval_id)
    if latest:
        return latest
    if approval.status != "pending":
        raise ApprovalInboxError(f"Approval is {approval.status} and cannot be decided")
    now = utc_now()
    expires_at = approval_expires_at(approval)
    if now > expires_at:
        store.update_approval_status(approval_id, "expired")
        raise ApprovalInboxError("Approval is expired and cannot be decided")
    signed = sign_approval_decision(
        approval_id=approval.approval_id,
        task_id=approval.task_id,
        requested_action=approval.requested_action,
        decision=decision,
        decided_by=decided_by,
        expires_at=expires_at,
        dry_run=not live,
        now=now,
    )
    store.persist_approval_decision(signed)
    store.append_audit(
        actor_type="control",
        actor_id=decided_by,
        action="approval_decision",
        target_type="approval",
        target_id=approval_id,
        risk_level=approval.risk_level,
        external_effect=approval.external_effect,
        summary=f"Approval {approval_id} was {decision}.",
        metadata={"decision_id": signed.decision_id, "expires_at": utc_iso(expires_at)},
    )
    return signed


def approval_to_inbox_dict(approval: ApprovalRequest) -> dict[str, object]:
    return {
        "approval_id": approval.approval_id,
        "task_id": approval.task_id,
        "agent_id": approval.agent_id,
        "requested_action": approval.requested_action,
        "risk_level": approval.risk_level,
        "external_effect": approval.external_effect,
        "plain_english_request": approval.plain_english_request,
        "sentinel_review": approval.guardian_review,
        "created_at": approval.created_at.isoformat(),
        "expires_at": approval_expires_at(approval).isoformat(),
        "status": approval.status,
    }


def require_approval(store: Store, approval_id: str) -> ApprovalRequest:
    try:
        return store.get_approval(approval_id)
    except StoreError as exc:
        raise ApprovalInboxError(str(exc)) from exc
