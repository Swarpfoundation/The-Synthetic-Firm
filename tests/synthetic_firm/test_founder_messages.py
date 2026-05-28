from __future__ import annotations

import json

from synthetic_firm.autonomous_workday import run_agent_turn, start_workday
from synthetic_firm.control_room_export import build_control_room_snapshot
from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import parse_telegram_command
from synthetic_firm.telegram_live import (
    TelegramConfig,
    handle_control_command,
    handle_founder_telegram_text,
)


def _config() -> TelegramConfig:
    return TelegramConfig(enabled=False, bot_token=None, allowed_chat_ids=frozenset({"founder"}), mode="dry_run")


def test_founder_telegram_message_creates_queued_atlas_message(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    response = handle_founder_telegram_text(store, "Please remember the pricing constraint.", chat_id="founder", config=_config())
    messages = store.list_founder_messages()

    assert "queued for Atlas review" in response
    assert len(messages) == 1
    assert messages[0].target_agent == "atlas"
    assert messages[0].priority == "normal"
    assert messages[0].message_type == "note"
    assert messages[0].status == "queued"
    store.close()


def test_urgent_founder_message_is_flagged_and_audited(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()

    response = handle_control_command(
        store,
        parse_telegram_command("/urgent Stop any public claim about revenue."),
        chat_id="founder",
        config=_config(),
    )
    message = store.list_founder_messages()[0]
    audit_actions = [row["action"] for row in store.connection.execute("SELECT action FROM audit_log").fetchall()]

    assert "urgent message queued" in response
    assert message.priority == "urgent"
    assert message.message_type == "urgent_override"
    assert "urgent_founder_message" in audit_actions
    store.close()


def test_atlas_reviews_queued_founder_messages_during_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    start_workday(store)
    store.create_founder_message(content="Founder says use conservative pricing language.")

    result = run_agent_turn(store, agent_id="atlas")
    reviewed = store.list_founder_messages(status="reviewed")

    assert reviewed[0].reviewed_by_agent_id == "atlas"
    assert "reviewed 1 founder message" in result["summary"]
    store.close()


def test_human_task_done_blocked_and_note_updates_create_founder_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    task = store.create_human_task(
        requested_by_agent_id="atlas",
        title="Connect provider",
        plain_english_request="Connect the approved provider account.",
        reason="Provider access requires founder account ownership.",
        public_summary="Founder provider connection task pending.",
    )

    handle_control_command(store, parse_telegram_command(f"/note {task.human_task_id} Done after billing review"), chat_id="founder", config=_config())
    handle_control_command(store, parse_telegram_command(f"/blocked {task.human_task_id}"), chat_id="founder", config=_config())
    blocked = store.get_human_task(task.human_task_id)
    handle_control_command(store, parse_telegram_command(f"/done {task.human_task_id}"), chat_id="founder", config=_config())
    done = store.get_human_task(task.human_task_id)
    messages = store.list_founder_messages()

    assert blocked.status == "blocked"
    assert done.status == "done"
    assert done.founder_note == "Done after billing review"
    assert len(messages) == 3
    assert all(message.target_agent == "atlas" for message in messages)
    assert any(message.related_human_task_id == task.human_task_id for message in messages)
    store.close()


def test_public_export_excludes_private_founder_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("TSF_HOME", str(tmp_path))
    store = Store()
    store.create_founder_message(
        content="Private founder note includes private@example.com and token sk-private-founder-value."
    )

    snapshot = build_control_room_snapshot(store, audience="public")
    dumped = json.dumps(snapshot)

    assert snapshot["founderMessageSummary"]["queuedCount"] == 1
    assert "Private founder note" not in dumped
    assert "private@example.com" not in dumped
    assert "sk-private-founder-value" not in dumped
    store.close()


def test_readme_presents_cli_as_internal_developer_utility():
    readme = open("README.md", encoding="utf-8").read()

    assert "Internal Developer Setup" in readme
    assert "not the product interface" in readme
