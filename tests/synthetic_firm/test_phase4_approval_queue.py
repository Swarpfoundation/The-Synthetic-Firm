from __future__ import annotations

from datetime import timedelta

import pytest

from synthetic_firm.approval_inbox import (
    ApprovalInboxError,
    decide_pending_approval,
    format_approval_detail,
    list_pending_approvals,
)
from synthetic_firm.approval_signing import sign_approval_decision
from synthetic_firm.execution_queue import (
    ExecutionQueueError,
    enqueue_action,
    get_queue_item,
    process_queue_item,
)
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_now


def _task_and_approval(store: Store, *, external_effect: bool = False, action: str = "internal_note"):
    task = store.create_task(
        title="Approval inbox task",
        objective="Exercise approval inbox",
        created_by_agent_id="atlas",
        plain_english_summary="Approval inbox task should be reviewable.",
    )
    approval = store.create_approval(
        task_id=task.task_id,
        agent_id="forge",
        requested_action=action,
        risk_level="high" if external_effect else "medium",
        external_effect=external_effect,
        plain_english_request="Forge requests founder approval.",
        guardian_review="Sentinel requires founder review.",
    )
    return task, approval


def test_approval_inbox_lists_and_formats_pending(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    _, approval = _task_and_approval(store)

    pending = list_pending_approvals(store)
    detail = format_approval_detail(approval)

    assert pending[0].approval_id == approval.approval_id
    assert "The Synthetic Firm approval detail" in detail
    assert "Sentinel requires founder review" in detail
    store.close()


def test_approve_and_deny_sign_decisions_idempotently(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "phase4-test-secret")
    store = Store()
    _, approval = _task_and_approval(store)

    first = decide_pending_approval(store, approval.approval_id, decision="approved", decided_by="founder")
    second = decide_pending_approval(store, approval.approval_id, decision="approved", decided_by="founder")

    assert first.decision_id == second.decision_id
    assert first.signature
    _, deny_approval = _task_and_approval(store)
    denied = decide_pending_approval(store, deny_approval.approval_id, decision="denied", decided_by="founder")
    assert denied.payload["decision"] == "denied"
    store.close()


def test_missing_signing_secret_fails_closed_for_live_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_APPROVAL_SIGNING_SECRET", raising=False)
    store = Store()
    _, approval = _task_and_approval(store)

    with pytest.raises(ValueError):
        decide_pending_approval(store, approval.approval_id, decision="approved", decided_by="founder")
    store.close()


def test_expired_approval_cannot_be_approved(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "phase4-test-secret")
    store = Store()
    task = store.create_task(
        title="Expired approval",
        objective="Reject stale approval",
        created_by_agent_id="atlas",
        plain_english_summary="Expired approval should fail closed.",
    )
    approval = store.create_approval(
        task_id=task.task_id,
        agent_id="forge",
        requested_action="internal_note",
        risk_level="medium",
        external_effect=False,
        plain_english_request="Old request.",
        now=utc_now() - timedelta(days=2),
    )

    with pytest.raises(ApprovalInboxError):
        decide_pending_approval(store, approval.approval_id, decision="approved", decided_by="founder")
    store.close()


def test_external_effect_queue_blocks_missing_adapter_and_consumes_once(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "phase4-test-secret")
    store = Store()
    task, approval = _task_and_approval(store, external_effect=True, action="create_approval_request")
    decide_pending_approval(store, approval.approval_id, decision="approved", decided_by="founder")

    first = enqueue_action(
        store,
        task_id=task.task_id,
        agent_id="forge",
        action="create_approval_request",
        external_effect=True,
        approval_id=approval.approval_id,
    )
    second = enqueue_action(
        store,
        task_id=task.task_id,
        agent_id="forge",
        action="create_approval_request",
        external_effect=True,
        approval_id=approval.approval_id,
    )

    processed = process_queue_item(store, first.queue_id, dry_run=False)
    assert processed.status == "blocked_missing_adapter"
    with pytest.raises(ExecutionQueueError):
        process_queue_item(store, second.queue_id, dry_run=False)
    store.close()


def test_wrong_action_hash_cannot_execute(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "phase4-test-secret")
    store = Store()
    task, approval = _task_and_approval(store, external_effect=True, action="internal_note")
    decision = sign_approval_decision(
        approval_id=approval.approval_id,
        task_id=task.task_id,
        requested_action="internal_note",
        decision="approved",
        decided_by="founder",
        expires_at=utc_now() + timedelta(hours=1),
    )
    store.persist_approval_decision(decision)
    item = enqueue_action(
        store,
        task_id=task.task_id,
        agent_id="forge",
        action="create_approval_request",
        external_effect=True,
        approval_id=approval.approval_id,
    )

    processed = process_queue_item(store, item.queue_id, dry_run=False)

    assert processed.status == "failed"
    store.close()


def test_safe_internal_queued_action_executes_and_audits(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Queue safe action",
        objective="Execute safe action",
        created_by_agent_id="atlas",
        plain_english_summary="Safe queued action should execute.",
    )
    item = enqueue_action(
        store,
        task_id=task.task_id,
        agent_id="atlas",
        action="create_message",
        payload={"channel": "company", "content": "Safe queued note."},
    )

    processed = process_queue_item(store, item.queue_id, dry_run=False)
    actions = [row["action"] for row in store.connection.execute("SELECT action FROM audit_log").fetchall()]

    assert get_queue_item(store, processed.queue_id).status == "executed"
    assert "execution_queue_transition" in actions
    assert store.verify_audit()[0] is True
    store.close()
