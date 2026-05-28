"""HMAC approval signing for exact-action authorization."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from synthetic_firm.time_utils import parse_utc_iso, utc_iso, utc_now

SIGNING_ENV = "TSF_APPROVAL_SIGNING_SECRET"
APPROVAL_VERSION = "phase3.v1"


class ApprovalSigningError(ValueError):
    """Raised when approval signing or verification fails closed."""


@dataclass(frozen=True)
class SignedApprovalDecision:
    decision_id: str
    payload: dict[str, Any]
    signature: str | None
    dry_run: bool
    executable: bool


def action_hash(requested_action: str) -> str:
    return hashlib.sha256(str(requested_action).encode("utf-8")).hexdigest()


def sign_approval_decision(
    *,
    approval_id: str,
    task_id: str,
    requested_action: str,
    decision: str,
    decided_by: str,
    expires_at: datetime,
    dry_run: bool = False,
    now: datetime | None = None,
    secret: str | None = None,
) -> SignedApprovalDecision:
    normalized = _decision(decision)
    decided_at = now or utc_now()
    payload = {
        "approval_id": _required(approval_id, "approval_id"),
        "task_id": _required(task_id, "task_id"),
        "requested_action": _required(requested_action, "requested_action"),
        "decision": normalized,
        "decided_by": _required(decided_by, "decided_by"),
        "decided_at": utc_iso(decided_at),
        "expires_at": utc_iso(expires_at),
        "approval_version": APPROVAL_VERSION,
        "action_hash": action_hash(requested_action),
    }
    if dry_run:
        return SignedApprovalDecision(
            decision_id=f"decision_{uuid4().hex[:12]}",
            payload={**payload, "dry_run": True},
            signature=None,
            dry_run=True,
            executable=False,
        )
    signing_secret = secret if secret is not None else os.environ.get(SIGNING_ENV)
    if not signing_secret:
        raise ApprovalSigningError("Approval signing secret is required for live approval decisions")
    signature = _signature(payload, signing_secret)
    return SignedApprovalDecision(
        decision_id=f"decision_{uuid4().hex[:12]}",
        payload=payload,
        signature=signature,
        dry_run=False,
        executable=normalized == "approved",
    )


def verify_signed_decision(
    decision: SignedApprovalDecision,
    *,
    requested_action: str,
    now: datetime | None = None,
    secret: str | None = None,
) -> bool:
    if decision.dry_run or not decision.executable:
        return False
    signing_secret = secret if secret is not None else os.environ.get(SIGNING_ENV)
    if not signing_secret:
        raise ApprovalSigningError("Approval signing secret is required for verification")
    payload = dict(decision.payload)
    if payload.get("action_hash") != action_hash(requested_action):
        return False
    if payload.get("requested_action") != requested_action:
        return False
    expires_at = parse_utc_iso(str(payload.get("expires_at")))
    if (now or utc_now()).astimezone(timezone.utc) > expires_at:
        return False
    expected = _signature(payload, signing_secret)
    return hmac.compare_digest(expected, str(decision.signature or ""))


def default_expiry(now: datetime | None = None) -> datetime:
    return (now or utc_now()) + timedelta(hours=24)


def decision_to_json(decision: SignedApprovalDecision) -> str:
    return json.dumps(
        {
            "decision_id": decision.decision_id,
            "payload": decision.payload,
            "signature": decision.signature,
            "dry_run": decision.dry_run,
            "executable": decision.executable,
        },
        sort_keys=True,
    )


def decision_from_json(value: str) -> SignedApprovalDecision:
    raw = json.loads(value)
    return SignedApprovalDecision(
        decision_id=str(raw["decision_id"]),
        payload=dict(raw["payload"]),
        signature=raw.get("signature"),
        dry_run=bool(raw["dry_run"]),
        executable=bool(raw["executable"]),
    )


def _signature(payload: dict[str, Any], secret: str) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def _decision(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"approved", "denied"}:
        raise ApprovalSigningError("Approval decision must be approved or denied")
    return normalized


def _required(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ApprovalSigningError(f"{name} is required")
    return text
