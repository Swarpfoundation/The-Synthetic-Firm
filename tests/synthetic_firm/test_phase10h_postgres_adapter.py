from __future__ import annotations

import json
import os
import sqlite3
import sys

import pytest

from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.deployment import save_deployment_record
from synthetic_firm.migrations import initialize_schema
from synthetic_firm.notification_queue import enqueue_notification
from synthetic_firm.postgres_connection import translate_sql
from synthetic_firm.render_runtime import scheduler_render_readiness
from synthetic_firm.scheduler import acquire_scheduler_lock
from synthetic_firm.store import Store, StoreError
from synthetic_firm.store_backend import db_status, db_verify
from synthetic_firm.vercel_adapter import create_vercel_deployment_plan


def test_postgres_extra_is_optional_and_missing_driver_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@private.db.example:5432/tsf")
    monkeypatch.setitem(sys.modules, "psycopg", None)

    status = db_status()

    assert status["backend"] == "postgres"
    assert status["connected"] is False
    assert "Postgres driver is unavailable" in status["safeSummary"]
    assert "secret" not in json.dumps(status)
    assert "private.db.example" not in json.dumps(status)
    with pytest.raises(StoreError) as exc:
        Store()
    assert "Install with: pip install -e '.[postgres]'" in str(exc.value)


def test_postgres_sql_translation_keeps_parameterized_commands():
    assert translate_sql("SELECT * FROM tasks WHERE task_id = ?") == "SELECT * FROM tasks WHERE task_id = %s"
    assert "ON CONFLICT (task_id)" in translate_sql("REPLACE INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    assert "created_at::date = CURRENT_DATE" in translate_sql("SELECT * FROM budget_usage WHERE date(created_at) = date('now')")
    assert translate_sql("BEGIN IMMEDIATE") == "BEGIN"
    assert "information_schema.tables" in translate_sql("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")


def test_selected_backend_store_facade_routes_core_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@private.db.example:5432/tsf")

    def fake_connect():
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        initialize_schema(connection)
        connection.execute("INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, 'now')")
        connection.execute("INSERT OR IGNORE INTO runtime_status (singleton_id, status, updated_at) VALUES (1, 'active', 'now')")
        connection.commit()
        return connection

    monkeypatch.setattr("synthetic_firm.postgres_repositories.connect_postgres", fake_connect)
    monkeypatch.setattr("synthetic_firm.postgres_repositories.PostgresStore._ensure_schema", lambda self: None)

    store = Store()

    assert store.__class__.__name__ == "PostgresStore"
    task = store.create_task(
        title="Postgres facade task",
        objective="Persist through the selected backend facade.",
        created_by_agent_id="atlas",
        assigned_agent_id="forge",
        plain_english_summary="Postgres facade task persisted.",
    )
    store.create_message(sender_agent_id="atlas", channel="company", task_id=task.task_id, content="Selected backend message.")
    approval = store.create_approval(
        task_id=task.task_id,
        agent_id="forge",
        requested_action="status_check",
        risk_level="medium",
        external_effect=False,
        plain_english_request="Check status without mutation.",
    )
    store.record_budget_usage(amount_usd=0.25, loop_steps=1, tool_calls=1, summary="Selected backend budget.")
    report_id = store.save_daily_report(
        report_date="2026-05-29",
        content="The Synthetic Firm - Daily Public Report\nSelected backend report.",
        telegram_summary="Selected backend report.",
    )
    human_task = store.create_human_task(
        requested_by_agent_id="forge",
        title="Configure Render Postgres",
        plain_english_request="Configure the shared database URL in Render.",
        reason="The API and scheduler need shared state.",
        public_summary="Founder database setup task pending.",
    )
    founder_message = store.create_founder_message(content="Private founder note", source="telegram")
    lock = acquire_scheduler_lock(store)
    notification = enqueue_notification(store, notification_type="human_task", body="Safe HumanTask notification.", dry_run=True)
    deployment = save_deployment_record(store, plan=create_vercel_deployment_plan(environment="preview"))

    snapshot = build_control_room_snapshot(store, audience="public")

    assert store.get_task(task.task_id).task_id == task.task_id
    assert store.get_approval(approval.approval_id).approval_id == approval.approval_id
    assert store.list_messages(task_id=task.task_id)
    assert store.list_daily_reports()[0]["report_id"] == report_id
    assert store.get_human_task(human_task.human_task_id).human_task_id == human_task.human_task_id
    assert store.list_founder_messages()[0].message_id == founder_message.message_id
    assert lock is not None
    assert notification.notification_id
    assert deployment.deployment_id
    assert snapshot["tasks"][0]["id"] == task.task_id
    assert "Private founder note" not in json.dumps(snapshot)
    assert store.verify_audit()[0] is True
    store.close()


def test_postgres_db_verify_uses_live_schema_status(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@private.db.example:5432/tsf")
    monkeypatch.setattr(
        "synthetic_firm.store_backend.check_postgres_connectivity",
        lambda url: {"connected": True, "summary": "Postgres connectivity verified."},
    )
    monkeypatch.setattr(
        "synthetic_firm.store_backend.inspect_postgres_schema",
        lambda url: {"connected": True, "schemaReady": True, "schemaVersion": 1, "missingTables": [], "summary": "Postgres schema verified."},
    )

    status = db_status()
    verified = db_verify()

    assert status["publicStatus"] == "postgres_ready"
    assert status["repositoryMode"] == "postgres_active"
    assert verified["verified"] is True
    assert "secret" not in json.dumps(status)


def test_render_readiness_creates_human_task_when_postgres_driver_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setenv("TSF_STORE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@private.db.example:5432/tsf")
    monkeypatch.setitem(sys.modules, "psycopg", None)

    result = scheduler_render_readiness()
    advisory_store = Store(tmp_path / "state" / "synthetic-firm.sqlite3")
    tasks = advisory_store.list_human_tasks(status="pending")
    dumped = json.dumps([task.__dict__ for task in tasks])

    assert result["ready"] is False
    assert any("Install the TSF Postgres extra" in item for item in result["missingRequirements"])
    assert any("Install the TSF Postgres extra" in task.plain_english_request for task in tasks)
    assert "secret" not in dumped
    assert "private.db.example" not in dumped
    advisory_store.close()


@pytest.mark.skipif("TSF_TEST_POSTGRES_URL" not in os.environ, reason="live Postgres smoke requires explicit test URL")
def test_live_postgres_placeholder():
    # Live Postgres execution is intentionally opt-in through environment-driven
    # smoke commands, not unit tests. This placeholder keeps the test plan
    # explicit without making network/database access part of normal CI.
    assert True
