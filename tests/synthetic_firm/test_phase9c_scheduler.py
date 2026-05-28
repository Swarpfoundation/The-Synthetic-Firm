from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.scheduler import (
    acquire_scheduler_lock,
    evaluate_checkpoint_now,
    enqueue_new_human_task_notifications,
    release_scheduler_lock,
    run_checkpoint_once,
    scheduler_dry_run_plan,
    scheduler_lock_status,
    scheduler_status,
)
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso, utc_now

PARIS = ZoneInfo("Europe/Paris")


def _dt(hour: int, minute: int = 0, *, day: int = 1) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=PARIS)


def test_scheduler_plan_uses_paris_workday():
    plan = scheduler_dry_run_plan(now=_dt(9, 30))

    assert plan["timezone"] == "Europe/Paris"
    assert plan["hours"] == "10:00-16:00"
    assert plan["checkpoints"][0]["time"] == "10:00"
    assert plan["checkpoints"][-1]["time"] == "16:00"


def test_checkpoint_evaluation_windows_and_weekend(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    assert evaluate_checkpoint_now(_dt(9, 59), store=store).due is False
    assert evaluate_checkpoint_now(_dt(10, 0), store=store).checkpoint_type == "start_workday"
    assert evaluate_checkpoint_now(_dt(11, 0), store=store).checkpoint_type == "cycle_1100"
    assert evaluate_checkpoint_now(_dt(16, 0), store=store).checkpoint_type == "close_workday"
    assert evaluate_checkpoint_now(datetime(2026, 6, 6, 11, 0, tzinfo=PARIS), store=store).due is False
    store.close()


def test_scheduler_lock_prevents_overlap_and_expires(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    lock = acquire_scheduler_lock(store, owner="test")
    assert lock is not None
    assert acquire_scheduler_lock(store, owner="test") is None

    expired_at = utc_iso(utc_now() - timedelta(seconds=10))
    store.connection.execute("UPDATE scheduler_locks SET expires_at = ? WHERE lock_id = ?", (expired_at, lock.lock_id))
    store.connection.commit()
    stale_replacement = acquire_scheduler_lock(store, owner="test")

    assert stale_replacement is not None
    status = scheduler_lock_status(store)
    assert status["lock"]["status"] == "active"
    release_scheduler_lock(store, stale_replacement.lock_id)
    assert store.verify_audit()[0] is True
    store.close()


def test_checkpoint_starts_workday_and_blocks_repeat(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    first = run_checkpoint_once(store, now=_dt(10, 0))
    second = run_checkpoint_once(store, now=_dt(10, 15))

    assert first["status"] == "completed"
    assert first["evaluation"]["checkpoint_type"] == "start_workday"
    assert second["status"] == "skipped"
    assert "already completed" in second["summary"]
    assert store.connection.execute("SELECT COUNT(*) AS c FROM workdays").fetchone()["c"] == 1
    store.close()


def test_checkpoint_runs_cycle_creates_human_task_notification(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)
    store = Store()
    run_checkpoint_once(store, now=_dt(10, 0))

    result = run_checkpoint_once(store, now=_dt(11, 0))
    notifications = store.connection.execute("SELECT * FROM notification_queue").fetchall()

    assert result["status"] == "completed"
    assert result["evaluation"]["checkpoint_type"] == "cycle_1100"
    assert store.list_human_tasks()
    assert notifications
    body = "\n".join(row["body"] for row in notifications)
    assert "/done HT-" in body
    assert "secret" not in body.lower()
    assert store.verify_audit()[0] is True
    store.close()


def test_human_task_notification_dedupes(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_human_task(
        requested_by_agent_id="atlas",
        title="Founder task",
        plain_english_request="Confirm the public positioning.",
        reason="Atlas needs owner clarification.",
        public_summary="Founder clarification task pending.",
    )

    first = enqueue_new_human_task_notifications(store)
    second = enqueue_new_human_task_notifications(store)

    assert len(first) == 1
    assert second == []
    store.close()


def test_paused_and_killed_runtime_block_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.set_runtime_status("paused")
    paused = run_checkpoint_once(store, now=_dt(10, 0))
    assert paused["status"] == "failed"
    assert "paused" in paused["summary"]

    store.set_runtime_status("killed")
    killed = run_checkpoint_once(store, now=_dt(11, 0))
    assert killed["status"] == "failed"
    assert "killed" in killed["summary"]
    store.close()


def test_failed_audit_verification_blocks_cycle(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_task(title="Tamper target", objective="Create audit row.", created_by_agent_id="atlas")
    store.connection.execute("UPDATE audit_log SET summary = 'tampered' WHERE sequence_number = 1")
    store.connection.commit()

    result = run_checkpoint_once(store, now=_dt(11, 0))

    assert result["status"] == "failed"
    assert "Audit verification failed" in result["summary"]
    store.close()


def test_public_snapshot_includes_scheduler_status(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    run_checkpoint_once(store, now=_dt(10, 0))

    snapshot = build_control_room_snapshot(store, audience="public")

    assert snapshot["scheduler"]["status"] in {"completed", "skipped", "failed"}
    assert snapshot["scheduler"]["workdayWindow"] == "10:00-16:00 Europe/Paris"
    assert "scheduler" in snapshot
    store.close()


def test_scheduler_internal_cli_status(monkeypatch, tmp_path, capsys):
    from synthetic_firm.cli import main

    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["scheduler-dry-run-plan"]) == 0
    assert "10:00-16:00" in capsys.readouterr().out

    assert main(["scheduler-status"]) == 0
    assert "Autonomous scheduler status loaded" in capsys.readouterr().out
