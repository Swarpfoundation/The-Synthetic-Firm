from __future__ import annotations

import json

import pytest

from synthetic_firm.autonomous_workday import (
    AutonomousWorkdayError,
    close_workday,
    create_daily_plan,
    get_current_workday,
    get_latest_plan,
    run_agent_turn,
    run_cycle,
    start_workday,
)
from synthetic_firm.cli import main
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.store import Store
from synthetic_firm.telegram_live import handle_control_command
from synthetic_firm.telegram_adapter import parse_telegram_command
from synthetic_firm.telegram_live import TelegramConfig
from synthetic_firm.truthfulness_guard import evaluate_public_claims


def test_start_workday_idempotent_and_plan_uses_real_state(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_task(
        title="Existing real task",
        objective="Use persisted state.",
        created_by_agent_id="atlas",
        plain_english_summary="Existing real task is persisted evidence.",
    )

    first = start_workday(store)
    second = start_workday(store)
    plan = get_latest_plan(store, first.workday_id)

    assert first.workday_id == second.workday_id
    assert first.status == "active"
    assert plan is not None
    assert plan.created_by_agent_id == "atlas"
    assert any("persisted task" in item for item in plan.real_data_sources_used)
    assert all("assumption" not in item.lower() for item in plan.real_data_sources_used)
    store.close()


def test_close_workday(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    workday = start_workday(store)

    closed = close_workday(store)

    assert closed.workday_id == workday.workday_id
    assert closed.status == "closed"
    assert closed.closed_at is not None
    store.close()


def test_paused_and_killed_runtime_block_cycles(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    start_workday(store)
    store.set_runtime_status("paused")

    with pytest.raises(AutonomousWorkdayError):
        run_cycle(store)

    store.set_runtime_status("killed")
    with pytest.raises(AutonomousWorkdayError):
        run_cycle(store)
    store.close()


def test_run_cycle_creates_real_tasks_messages_human_tasks_and_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)
    store = Store()

    result = run_cycle(store)

    assert "completed" in result["summary"]
    assert store.list_tasks()
    assert store.list_messages()
    assert store.list_human_tasks()
    assert store.list_daily_reports()
    public = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(public)
    assert public["autonomousWorkday"]["cycleCount"] == 1
    assert public["publicDailyReport"]["truthfulness"] == "Based on real TSF runtime data. No mock data. No fabricated progress."
    assert "privateDetailsRedacted" not in dumped
    assert "Private Founder Report" not in dumped
    store.close()


def test_agent_turn_missing_provider_creates_blocker_and_human_task(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.delenv("TSF_KIMI_CODE_API_KEY", raising=False)
    monkeypatch.delenv("TSF_KIMI_API_KEY", raising=False)
    store = Store()
    start_workday(store)

    result = run_agent_turn(store, agent_id="forge")
    human_tasks = store.list_human_tasks()

    assert result["human_task_id"]
    assert any(task.requested_by_agent_id == "forge" for task in human_tasks)
    assert any(task.status == "blocked" for task in store.list_tasks())
    store.close()


def test_forge_provider_ready_fallback_uses_valid_channel(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    monkeypatch.setattr("synthetic_firm.autonomous_workday._provider_reasoning_turn", lambda *args, **kwargs: None)
    monkeypatch.setattr("synthetic_firm.autonomous_workday._provider_ready", lambda: "kimi-code")
    store = Store()
    start_workday(store)

    result = run_agent_turn(store, agent_id="forge")
    messages = store.list_messages(channel="forge")

    assert result["summary"] == "Forge detected provider route kimi-code."
    assert messages
    assert messages[0].channel == "forge"
    store.close()


def test_truthfulness_guard_blocks_fake_claims():
    result = evaluate_public_claims("We made $1000 revenue and signed 5 customers.", evidence=[])

    assert result.allowed is False
    assert "revenue" in result.unsupported_claims
    assert "customers" in result.safe_text


def test_max_cycles_enforced(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    workday = start_workday(store)
    store.connection.execute("UPDATE workdays SET cycle_count = ? WHERE workday_id = ?", (6, workday.workday_id))
    store.connection.commit()

    with pytest.raises(AutonomousWorkdayError):
        run_cycle(store)

    store.close()


def test_public_report_empty_state_remains_truthful(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    start_workday(store)

    snapshot = build_control_room_snapshot(store, audience="public")

    assert snapshot["publicDailyReport"]["emptyState"]["completed"] == "No completed tasks today."
    assert "No fabricated progress" in snapshot["publicDailyReport"]["truthfulness"]
    store.close()


def test_telegram_human_task_inbox_includes_generated_task(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"founder"}), mode="dry_run")
    start_workday(store)
    run_agent_turn(store, agent_id="scout")

    response = handle_control_command(store, parse_telegram_command("/human_tasks"), chat_id="founder", config=config)

    assert "HT-" in response
    assert "pending" in response.lower() or "task" in response.lower()
    store.close()


def test_cli_autonomous_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))

    assert main(["start-workday"]) == 0
    started = json.loads(capsys.readouterr().out)
    assert started["workday"]["status"] == "active"

    assert main(["autonomous-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["workday"]["status"] == "active"

    assert main(["run-agent-turn", "sentinel"]) == 0
    assert "Sentinel" in capsys.readouterr().out or "sentinel" in capsys.readouterr().out


def test_audit_entries_written_and_verified(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    run_cycle(store)
    actions = {
        row["action"]
        for row in store.connection.execute("SELECT action FROM audit_log ORDER BY sequence_number").fetchall()
    }

    assert "workday_start" in actions
    assert "daily_plan_create" in actions
    assert "agent_turn_start" in actions
    assert "public_report_generation" in actions
    assert store.verify_audit()[0] is True
    store.close()
