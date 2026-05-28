from __future__ import annotations

import pytest

from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import parse_telegram_command
from synthetic_firm.telegram_live import (
    TelegramConfig,
    TelegramLiveError,
    confirm_kill,
    create_kill_confirmation,
    handle_control_command,
    load_telegram_config,
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
    store.close()


def test_allowed_chat_id_accepts_status(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    config = TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"123"}), mode="dry_run")

    response = handle_control_command(store, parse_telegram_command("/status"), chat_id="123", config=config)

    assert "runtime is active" in response
    store.close()


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
