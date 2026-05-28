from __future__ import annotations

from datetime import timedelta

import pytest

from synthetic_firm.approval_signing import (
    ApprovalSigningError,
    default_expiry,
    sign_approval_decision,
    verify_signed_decision,
)
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_now


def test_signed_approval_verifies_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "test-signing-secret")
    store = Store()
    task = store.create_task(
        title="Approval task",
        objective="Sign a decision",
        created_by_agent_id="atlas",
        plain_english_summary="Approval signing should persist.",
    )
    approval = store.create_approval(
        task_id=task.task_id,
        agent_id="forge",
        requested_action="internal_note",
        risk_level="medium",
        external_effect=False,
        plain_english_request="Allow Forge to write an internal note.",
    )

    decision = sign_approval_decision(
        approval_id=approval.approval_id,
        task_id=task.task_id,
        requested_action="internal_note",
        decision="approved",
        decided_by="founder",
        expires_at=default_expiry(),
    )
    store.persist_approval_decision(decision)

    latest = store.latest_approval_decision(approval.approval_id)
    assert latest is not None
    assert verify_signed_decision(latest, requested_action="internal_note") is True
    assert store.get_approval(approval.approval_id).status == "approved"
    store.close()


def test_tampered_expired_and_wrong_action_fail(monkeypatch):
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "test-signing-secret")
    decision = sign_approval_decision(
        approval_id="appr_1",
        task_id="task_1",
        requested_action="internal_note",
        decision="approved",
        decided_by="founder",
        expires_at=default_expiry(),
    )

    tampered = decision.__class__(
        decision_id=decision.decision_id,
        payload={**decision.payload, "decision": "denied"},
        signature=decision.signature,
        dry_run=decision.dry_run,
        executable=decision.executable,
    )
    assert verify_signed_decision(tampered, requested_action="internal_note") is False
    assert verify_signed_decision(decision, requested_action="create_task") is False
    assert (
        verify_signed_decision(
            decision,
            requested_action="internal_note",
            now=utc_now() + timedelta(days=2),
        )
        is False
    )


def test_missing_signing_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("TSF_APPROVAL_SIGNING_SECRET", raising=False)

    with pytest.raises(ApprovalSigningError):
        sign_approval_decision(
            approval_id="appr_1",
            task_id="task_1",
            requested_action="internal_note",
            decision="approved",
            decided_by="founder",
            expires_at=default_expiry(),
        )


def test_dry_run_approval_is_non_executable():
    decision = sign_approval_decision(
        approval_id="appr_1",
        task_id="task_1",
        requested_action="internal_note",
        decision="approved",
        decided_by="founder",
        expires_at=default_expiry(),
        dry_run=True,
    )

    assert decision.dry_run is True
    assert decision.executable is False
    assert verify_signed_decision(decision, requested_action="internal_note", secret="test") is False
