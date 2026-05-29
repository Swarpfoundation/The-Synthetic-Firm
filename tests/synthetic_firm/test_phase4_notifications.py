from __future__ import annotations

from synthetic_firm.budget_alerts import budget_warning
from synthetic_firm.notification_queue import enqueue_notification, list_notifications, send_notifications
from synthetic_firm.store import Store
from synthetic_firm.telegram_live import TelegramConfig


def test_notification_dry_run_no_network(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    enqueue_notification(store, notification_type="daily_report", body="The Synthetic Firm daily report.", dry_run=True)

    sent = send_notifications(store, dry_run=True)

    assert sent[0].status == "dry_run_sent"
    store.close()


def test_live_send_is_mocked_and_token_not_stored(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    enqueue_notification(
        store,
        notification_type="runtime_status",
        body="The Synthetic Firm runtime is active.",
        chat_id="123",
        dry_run=False,
    )
    calls: list[tuple[str, str]] = []
    config = TelegramConfig(
        enabled=True,
        bot_token="sensitive-bot-token",
        allowed_chat_ids=frozenset({"123"}),
        mode="polling",
    )

    sent = send_notifications(store, dry_run=False, config=config, sender=lambda chat, body: calls.append((chat, body)))
    db_text = "\n".join(str(row) for row in store.connection.iterdump())

    assert sent[0].status == "sent"
    assert calls == [("123", "The Synthetic Firm runtime is active.")]
    assert "sensitive-bot-token" not in db_text
    store.close()


def test_live_send_can_retry_dry_run_human_task_notification(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    enqueue_notification(store, notification_type="human_task", body="Safe HumanTask notification.", dry_run=True)
    calls: list[tuple[str, str]] = []
    config = TelegramConfig(
        enabled=True,
        bot_token="sensitive-bot-token",
        allowed_chat_ids=frozenset({"123"}),
        mode="bounded_polling",
    )

    sent = send_notifications(
        store,
        dry_run=False,
        config=config,
        sender=lambda chat, body: calls.append((chat, body)),
        include_dry_run_notifications=True,
    )

    assert sent[0].status == "sent"
    assert calls == [("123", "Safe HumanTask notification.")]
    store.close()


def test_live_send_blocks_approval_notifications(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    enqueue_notification(
        store,
        notification_type="approval_request",
        body="Approve this action.",
        chat_id="123",
        dry_run=False,
    )
    calls: list[tuple[str, str]] = []
    config = TelegramConfig(
        enabled=True,
        bot_token="sensitive-bot-token",
        allowed_chat_ids=frozenset({"123"}),
        mode="bounded_polling",
    )

    sent = send_notifications(store, dry_run=False, config=config, sender=lambda chat, body: calls.append((chat, body)))
    row = store.connection.execute("SELECT status FROM notification_queue").fetchone()

    assert sent == []
    assert calls == []
    assert row["status"] == "blocked"
    store.close()


def test_budget_warning_thresholds():
    assert "50%" in budget_warning(5.0, 10.0)
    assert "80%" in budget_warning(8.0, 10.0)
    assert "95%" in budget_warning(9.5, 10.0)
    assert "100%" in budget_warning(10.0, 10.0)
    assert "unknown" in budget_warning(None, 10.0).lower()
