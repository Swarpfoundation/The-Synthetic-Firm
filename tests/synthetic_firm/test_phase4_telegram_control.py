from __future__ import annotations

import pytest

from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import parse_telegram_command
from synthetic_firm.telegram_live import (
    TelegramConfig,
    TelegramLiveError,
    TelegramUpdate,
    confirm_kill,
    create_kill_confirmation,
    handle_control_command,
    load_telegram_config,
    poll_once,
    send_pending_notifications,
    telegram_founder_smoke,
    telegram_status,
    validate_chat,
)


def test_telegram_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TSF_TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("TSF_TELEGRAM_BOT_TOKEN", raising=False)

    config = load_telegram_config()

    assert config.enabled is False
    assert config.mode == "dry_run"
    assert telegram_status(config)["bot_token_configured"] is False


def test_missing_bot_token_fails_closed_in_live_mode():
    config = TelegramConfig(enabled=True, bot_token=None, allowed_chat_ids=frozenset({"123"}), mode="polling")

    with pytest.raises(TelegramLiveError):
        config.require_live_ready()


def test_unknown_chat_id_rejected_and_audited(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"123"}), mode="dry_run")

    with pytest.raises(TelegramLiveError):
        validate_chat(store, config, "999")

    rows = store.connection.execute("SELECT action FROM audit_log").fetchall()
    assert rows[0]["action"] == "telegram_reject_chat"
    target = store.connection.execute("SELECT target_id FROM audit_log").fetchone()["target_id"]
    assert target == "unknown_chat"
    store.close()


def test_allowed_chat_id_accepts_status(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"123"}), mode="dry_run")

    response = handle_control_command(store, parse_telegram_command("/status"), chat_id="123", config=config)

    assert "runtime is active" in response
    store.close()


def test_start_command_is_safe_help_alias():
    parsed = parse_telegram_command("/start")

    assert parsed.command == "help"


def test_pause_resume_and_two_step_kill(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"123"}), mode="dry_run")

    assert "paused" in handle_control_command(store, parse_telegram_command("/pause"), chat_id="123", config=config)
    assert store.runtime_status() == "paused"
    assert "active" in handle_control_command(store, parse_telegram_command("/resume"), chat_id="123", config=config)
    code = create_kill_confirmation(store, "123")
    assert "killed" in confirm_kill(store, chat_id="123", code=code)
    assert store.runtime_status() == "killed"
    store.close()


def test_missing_allowed_chat_ids_fails_closed_in_live_mode():
    config = TelegramConfig(enabled=True, bot_token="token", allowed_chat_ids=frozenset(), mode="bounded_polling")

    with pytest.raises(TelegramLiveError):
        config.require_live_ready()


def test_founder_inbox_live_mode_blocks_remote_control_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=True, bot_token="token", allowed_chat_ids=frozenset({"123"}), mode="bounded_polling")

    for text in ("/approve appr_1", "/deny appr_1", "/pause", "/resume", "/kill", "/deploy", "/run whoami"):
        with pytest.raises(TelegramLiveError):
            handle_control_command(store, parse_telegram_command(text), chat_id="123", config=config)

    actions = [row["action"] for row in store.connection.execute("SELECT action FROM audit_log").fetchall()]
    assert "telegram_command_blocked" in actions
    store.close()


def test_founder_inbox_live_mode_allows_human_task_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_human_task(
        requested_by_agent_id="scout",
        title="Research setup",
        plain_english_request="Approve a safe research source.",
        reason="Scout needs founder-approved source configuration.",
        public_summary="Autonomous research capability setup is pending.",
    )
    config = TelegramConfig(enabled=True, bot_token="token", allowed_chat_ids=frozenset({"123"}), mode="bounded_polling")

    listing = handle_control_command(store, parse_telegram_command("/human_tasks"), chat_id="123", config=config)
    done = handle_control_command(store, parse_telegram_command(f"/done {task.human_task_id}"), chat_id="123", config=config)

    assert task.human_task_id in listing
    assert "marked done" in done
    store.close()


def test_poll_once_with_injected_allowed_update_queues_founder_message(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=True, bot_token="token", allowed_chat_ids=frozenset({"123"}), mode="bounded_polling")

    result = poll_once(store, config=config, fetch_update=lambda: TelegramUpdate(chat_id="123", text="Founder note"))

    assert "queued for Atlas" in result
    assert store.list_founder_messages()[0].content == "Founder note"
    store.close()


def test_send_pending_notifications_dry_run_marks_without_network(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.connection.execute(
        "INSERT INTO notification_queue VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("note_test", "human_task", None, "Safe notification", "queued", 1, "2026-01-01T00:00:00+00:00", None),
    )
    store.connection.commit()

    result = send_pending_notifications(store, config=TelegramConfig(False, None, frozenset({"123"}), "dry_run"))

    assert result["sent"] == 1
    assert "Safe notification" in store.connection.execute("SELECT body FROM notification_queue").fetchone()["body"]
    store.close()


def test_telegram_founder_smoke_reports_no_secret_values():
    config = TelegramConfig(enabled=True, bot_token="secret-token-value", allowed_chat_ids=frozenset({"123"}), mode="bounded_polling")

    result = telegram_founder_smoke(config=config, live=True)
    dumped = str(result)

    assert result["token_present"] is True
    assert result["allowed_chat_count"] == 1
    assert "secret-token-value" not in dumped
    assert "123" not in dumped
