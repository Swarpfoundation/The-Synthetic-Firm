from __future__ import annotations

import sqlite3

import pytest

from synthetic_firm.budget import BudgetPolicy
from synthetic_firm.store import Store, StoreError, default_db_path, init_store


def test_store_initializes_under_tsf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    store = init_store()

    assert default_db_path() == tmp_path / "state" / "synthetic-firm.sqlite3"
    assert store.path.exists()
    assert "tasks" in store.status()["tables"]
    store.close()


def test_migrations_are_idempotent_and_data_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Persist task",
        objective="Verify reload",
        created_by_agent_id="atlas",
        plain_english_summary="Persist task for reload verification.",
    )
    store.close()

    reloaded = Store()
    assert reloaded.get_task(task.task_id).title == "Persist task"
    assert reloaded.status()["schema_version"] == 1
    reloaded.close()


def test_task_transitions_persist_and_write_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Move task",
        objective="Verify audit",
        created_by_agent_id="atlas",
        plain_english_summary="Move task through accepted state.",
    )

    store.update_task_status(task.task_id, "accepted")

    assert store.get_task(task.task_id).status == "accepted"
    rows = store.connection.execute("SELECT action FROM audit_log ORDER BY sequence_number").fetchall()
    assert [row["action"] for row in rows] == ["task_create", "task_status_update"]
    store.close()


def test_invalid_transition_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Invalid transition",
        objective="Reject unsafe state jump",
        created_by_agent_id="atlas",
        plain_english_summary="Invalid transition should be rejected.",
    )

    with pytest.raises(ValueError):
        store.complete_task(task.task_id)
    store.close()


def test_messages_persist_and_validate_channel(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Message task",
        objective="Route through store",
        created_by_agent_id="atlas",
        plain_english_summary="Message routing should be persisted.",
    )

    message = store.create_message(
        sender_agent_id="atlas",
        channel="company",
        task_id=task.task_id,
        content="Scout should inspect this opportunity.",
    )

    assert store.list_messages(task_id=task.task_id)[0].message_id == message.message_id
    with pytest.raises(StoreError):
        store.create_message(sender_agent_id="atlas", channel="outside", content="No route")
    store.close()


def test_audit_hash_chain_detects_tampering(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_task(
        title="Audit task",
        objective="Detect tampering",
        created_by_agent_id="atlas",
        plain_english_summary="Audit chain should verify.",
    )

    assert store.verify_audit()[0] is True
    store.connection.execute("UPDATE audit_log SET summary = ? WHERE sequence_number = 1", ("tampered",))
    store.connection.commit()

    assert store.verify_audit()[0] is False
    store.close()


def test_runtime_pause_and_kill(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    store.set_runtime_status("paused")
    assert store.runtime_status() == "paused"
    store.set_runtime_status("active")
    store.set_runtime_status("killed")

    with pytest.raises(StoreError):
        store.set_runtime_status("active")
    store.close()


def test_budget_usage_persists_and_limits_apply(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_task(
        title="Budget persistence",
        objective="Enforce persisted totals",
        created_by_agent_id="atlas",
        plain_english_summary="Budget usage should persist and enforce limits.",
    )
    store.record_budget_usage(
        agent_id="atlas",
        task_id=task.task_id,
        amount_usd=3.0,
        loop_steps=1,
        tool_calls=1,
        summary="Recorded safe model usage.",
    )

    allowed = store.evaluate_persisted_budget(
        agent_id="atlas",
        task_id=task.task_id,
        policy=BudgetPolicy(10.0, 5.0, 20.0, 5, 5),
    )
    blocked = store.evaluate_persisted_budget(
        agent_id="atlas",
        task_id=task.task_id,
        policy=BudgetPolicy(10.0, 2.0, 20.0, 5, 5),
    )

    assert allowed.allowed is True
    assert blocked.allowed is False
    assert "task budget exceeded" in blocked.reason
    store.close()
