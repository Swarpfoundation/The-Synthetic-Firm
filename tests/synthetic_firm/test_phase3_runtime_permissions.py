from __future__ import annotations

import pytest

from synthetic_firm.budget import BudgetPolicy, BudgetUsage
from synthetic_firm.approval_signing import default_expiry, sign_approval_decision
from synthetic_firm.runtime_permissions import RuntimeAction, RuntimePermissionError, evaluate_runtime_action
from synthetic_firm.store import Store


def _policy() -> BudgetPolicy:
    return BudgetPolicy(10.0, 10.0, 25.0, 5, 5)


def _usage() -> BudgetUsage:
    return BudgetUsage(1.0, 1.0, 2.0, 1, 1)


def test_safe_internal_action_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Permission task",
        objective="Allow safe action",
        created_by_agent_id="atlas",
        plain_english_summary="Safe actions should pass runtime policy.",
    )

    decision = evaluate_runtime_action(
        store,
        RuntimeAction(agent_id="atlas", task_id=task.task_id, action="internal_note"),
        _policy(),
        _usage(),
    )

    assert decision.allowed is True
    store.close()


@pytest.mark.parametrize(
    "action",
    ["email_send", "policy_modify", "permission_escalate", "secret_read", "active_worker_create"],
)
def test_forbidden_actions_blocked(monkeypatch, tmp_path, action):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Forbidden action task",
        objective="Block unsafe action",
        created_by_agent_id="atlas",
        plain_english_summary="Forbidden actions should fail closed.",
    )

    with pytest.raises(RuntimePermissionError):
        evaluate_runtime_action(
            store,
            RuntimeAction(agent_id="atlas", task_id=task.task_id, action=action),
            _policy(),
            _usage(),
        )
    store.close()


def test_budget_failure_blocks_action(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Budget task",
        objective="Fail when budget unknown",
        created_by_agent_id="atlas",
        plain_english_summary="Unknown budget should block.",
    )

    with pytest.raises(RuntimePermissionError):
        evaluate_runtime_action(
            store,
            RuntimeAction(agent_id="atlas", task_id=task.task_id, action="internal_note"),
            _policy(),
            BudgetUsage(None, 1.0, 2.0, 1, 1),
        )
    store.close()


def test_paused_blocks_agent_work(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Paused task",
        objective="Block during pause",
        created_by_agent_id="atlas",
        plain_english_summary="Paused runtime should block agent work.",
    )
    store.set_runtime_status("paused")

    with pytest.raises(RuntimePermissionError):
        evaluate_runtime_action(
            store,
            RuntimeAction(agent_id="atlas", task_id=task.task_id, action="internal_note"),
            _policy(),
            _usage(),
        )
    store.close()


def test_approved_external_action_still_non_executable_in_phase3(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_APPROVAL_SIGNING_SECRET", "test-signing-secret")
    store = Store()
    task = store.create_task(
        title="External action task",
        objective="Keep execution disabled",
        created_by_agent_id="atlas",
        plain_english_summary="External-effect execution should remain disabled.",
    )
    decision = sign_approval_decision(
        approval_id="appr_external",
        task_id=task.task_id,
        requested_action="create_approval_request",
        decision="approved",
        decided_by="founder",
        expires_at=default_expiry(),
    )

    with pytest.raises(RuntimePermissionError, match="disabled in Phase 3"):
        evaluate_runtime_action(
            store,
            RuntimeAction(
                agent_id="atlas",
                task_id=task.task_id,
                action="create_approval_request",
                external_effect=True,
                approval_decision=decision,
            ),
            _policy(),
            _usage(),
        )
    store.close()
