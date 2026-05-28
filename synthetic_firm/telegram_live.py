"""Telegram founder interface adapter with dry-run defaults."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable

from synthetic_firm.approval_inbox import (
    approval_to_inbox_dict,
    decide_pending_approval,
    format_approval_detail,
    list_pending_approvals,
)
from synthetic_firm.budget_alerts import budget_warning
from synthetic_firm.human_tasks import format_human_task_for_telegram
from synthetic_firm.store import Store
from synthetic_firm.telegram_adapter import TelegramCommand
from synthetic_firm.time_utils import parse_utc_iso, utc_iso, utc_now


class TelegramLiveError(ValueError):
    """Raised when Telegram founder-interface checks fail closed."""


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    bot_token: str | None
    allowed_chat_ids: frozenset[str]
    mode: str

    def require_live_ready(self) -> None:
        if not self.enabled:
            raise TelegramLiveError("Telegram live mode is disabled")
        if self.mode not in {"dry_run", "polling"}:
            raise TelegramLiveError("Telegram mode must be dry_run or polling")
        if not self.bot_token:
            raise TelegramLiveError("Telegram bot token is required for live mode")
        if not self.allowed_chat_ids:
            raise TelegramLiveError("Allowed Telegram chat ids are required")

    def default_chat_id(self) -> str:
        if not self.allowed_chat_ids:
            raise TelegramLiveError("No allowed Telegram chat id configured")
        return sorted(self.allowed_chat_ids)[0]


@dataclass(frozen=True)
class TelegramUpdate:
    chat_id: str
    text: str


def load_telegram_config() -> TelegramConfig:
    enabled = os.environ.get("TSF_TELEGRAM_ENABLED", "false").strip().lower() == "true"
    mode = os.environ.get("TSF_TELEGRAM_MODE", "dry_run").strip().lower() or "dry_run"
    allowed = frozenset(
        item.strip() for item in os.environ.get("TSF_TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if item.strip()
    )
    return TelegramConfig(
        enabled=enabled,
        bot_token=os.environ.get("TSF_TELEGRAM_BOT_TOKEN"),
        allowed_chat_ids=allowed,
        mode=mode,
    )


def telegram_status(config: TelegramConfig | None = None) -> dict[str, object]:
    cfg = config or load_telegram_config()
    return {
        "enabled": cfg.enabled,
        "mode": cfg.mode,
        "allowed_chat_count": len(cfg.allowed_chat_ids),
        "bot_token_configured": bool(cfg.bot_token),
        "summary": "Telegram founder interface is configured for dry-run."
        if not cfg.enabled
        else "Telegram founder interface is enabled.",
    }


def validate_chat(store: Store, config: TelegramConfig, chat_id: str) -> None:
    if chat_id not in config.allowed_chat_ids:
        store.append_audit(
            actor_type="telegram",
            actor_id="unknown_chat",
            action="telegram_reject_chat",
            target_type="chat",
            target_id=str(chat_id),
            risk_level="high",
            summary="Rejected Telegram command from unknown chat id.",
        )
        raise TelegramLiveError("Telegram chat id is not allowed")


def handle_control_command(
    store: Store,
    command: TelegramCommand,
    *,
    chat_id: str,
    config: TelegramConfig | None = None,
) -> str:
    cfg = config or load_telegram_config()
    validate_chat(store, cfg, chat_id)
    runtime = store.runtime_status()
    human_task_commands = {"human_tasks", "human_task", "done", "blocked", "note"}
    if runtime == "killed" and command.command not in {"status", "help", *human_task_commands}:
        raise TelegramLiveError("Runtime is killed; only status, help, and founder human-task inbox commands are available")
    if runtime == "paused" and command.command not in {
        "status",
        "report",
        "approvals",
        "approval",
        "budget",
        "resume",
        "kill",
        "help",
        "founder_message",
        *human_task_commands,
    }:
        raise TelegramLiveError("Runtime is paused; command is blocked")

    if command.command == "founder_message":
        if not command.message:
            raise TelegramLiveError("Founder message content is required")
        message = queue_founder_message(
            store,
            command.message,
            priority=command.priority,
            message_type=command.message_type or "note",
        )
        urgency = "urgent " if message.priority == "urgent" else ""
        return f"Founder {urgency}message queued for Atlas review as {message.message_id}."
    if command.command == "status":
        return f"The Synthetic Firm runtime is {runtime}."
    if command.command == "help":
        return _help_text()
    if command.command == "report":
        reports = store.list_daily_reports()
        if not reports:
            return "No daily report is available yet."
        return str(reports[0]["telegram_summary"])
    if command.command == "budget":
        totals = store.budget_totals()
        return budget_warning(float(totals["spend"]), None)
    if command.command == "approvals":
        pending = list_pending_approvals(store)
        if not pending:
            return "No pending approvals."
        return "\n".join(_approval_line(approval_to_inbox_dict(item)) for item in pending)
    if command.command == "approval":
        if not command.approval_id:
            raise TelegramLiveError("Approval id is required")
        return format_approval_detail(store.get_approval(command.approval_id))
    if command.command in {"approve", "deny"}:
        if not command.approval_id:
            raise TelegramLiveError("Approval id is required")
        decision = "approved" if command.command == "approve" else "denied"
        signed = decide_pending_approval(store, command.approval_id, decision=decision, decided_by="founder", live=True)
        return f"Approval {command.approval_id} recorded as {signed.payload['decision']}."
    if command.command == "pause":
        store.set_runtime_status("paused")
        return "The Synthetic Firm runtime is paused."
    if command.command == "resume":
        store.set_runtime_status("active")
        return "The Synthetic Firm runtime is active."
    if command.command == "kill":
        if command.approval_id:
            return confirm_kill(store, chat_id=chat_id, code=command.approval_id)
        code = create_kill_confirmation(store, chat_id)
        return f"Kill confirmation required. Send /kill {code} within 10 minutes."
    if command.command == "tasks":
        tasks = store.list_tasks()
        if not tasks:
            return "No tasks are currently stored."
        return "\n".join(f"{task.task_id}: {task.status} - {task.title}" for task in tasks[:20])
    if command.command == "human_tasks":
        tasks = store.list_human_tasks(status="pending")
        if not tasks:
            return "No founder human tasks are pending."
        return "\n".join(f"{task.human_task_id}: {task.priority} - {task.public_summary}" for task in tasks[:20])
    if command.command == "human_task":
        if not command.human_task_id:
            raise TelegramLiveError("Human task id is required")
        return format_human_task_for_telegram(store.get_human_task(command.human_task_id))
    if command.command in {"done", "blocked"}:
        if not command.human_task_id:
            raise TelegramLiveError("Human task id is required")
        status = "done" if command.command == "done" else "blocked"
        task = store.update_human_task(command.human_task_id, status=status)
        queue_founder_message(
            store,
            f"Founder marked human task {task.human_task_id} {task.status}.",
            message_type="human_task_done",
            related_human_task_id=task.human_task_id,
        )
        return f"Human task {task.human_task_id} marked {task.status}."
    if command.command == "note":
        if not command.human_task_id or not command.message:
            raise TelegramLiveError("Human task id and note are required")
        task = store.update_human_task(command.human_task_id, founder_note=command.message)
        queue_founder_message(
            store,
            command.message,
            message_type="note",
            related_human_task_id=task.human_task_id,
        )
        return f"Founder note recorded for human task {task.human_task_id}."
    raise TelegramLiveError(f"Unsupported Telegram command: {command.command}")


def queue_founder_message(
    store: Store,
    text: str,
    *,
    priority: str = "normal",
    message_type: str = "note",
    related_human_task_id: str | None = None,
    related_task_id: str | None = None,
):
    return store.create_founder_message(
        source="telegram",
        sender="founder",
        target_agent="atlas",
        priority=priority,
        message_type=message_type,
        content=text,
        related_human_task_id=related_human_task_id,
        related_task_id=related_task_id,
    )


def handle_founder_telegram_text(
    store: Store,
    text: str,
    *,
    chat_id: str,
    config: TelegramConfig | None = None,
) -> str:
    cfg = config or load_telegram_config()
    validate_chat(store, cfg, chat_id)
    stripped = str(text or "").strip()
    if not stripped:
        raise TelegramLiveError("Telegram message is empty")
    if stripped.startswith("/"):
        from synthetic_firm.telegram_adapter import parse_telegram_command

        return handle_control_command(store, parse_telegram_command(stripped), chat_id=chat_id, config=cfg)
    message = queue_founder_message(store, stripped)
    return f"Founder message queued for Atlas review as {message.message_id}."


def create_kill_confirmation(store: Store, chat_id: str) -> str:
    code = secrets.token_hex(3)
    store.connection.execute(
        "INSERT INTO kill_confirmations VALUES (?, ?, ?, ?, ?, ?)",
        (f"kill_{secrets.token_hex(6)}", chat_id, code, utc_iso(utc_now() + timedelta(minutes=10)), 0, utc_iso()),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="telegram",
        actor_id=chat_id,
        action="kill_confirmation_create",
        target_type="runtime_status",
        target_id="company",
        risk_level="high",
        summary="Created kill confirmation code.",
    )
    return code


def confirm_kill(store: Store, *, chat_id: str, code: str) -> str:
    row = store.connection.execute(
        """
        SELECT * FROM kill_confirmations
        WHERE chat_id = ? AND code = ? AND used = 0
        ORDER BY created_at DESC LIMIT 1
        """,
        (chat_id, code),
    ).fetchone()
    if not row:
        raise TelegramLiveError("Kill confirmation code is invalid")
    if utc_now() > parse_utc_iso(row["expires_at"]):
        raise TelegramLiveError("Kill confirmation code expired")
    store.connection.execute("UPDATE kill_confirmations SET used = 1 WHERE confirmation_id = ?", (row["confirmation_id"],))
    store.connection.commit()
    store.set_runtime_status("killed")
    return "The Synthetic Firm runtime is killed."


def poll_once(
    store: Store,
    *,
    config: TelegramConfig | None = None,
    fetch_update: Callable[[], TelegramUpdate | None] | None = None,
) -> str:
    cfg = config or load_telegram_config()
    if cfg.mode == "dry_run":
        return "Dry-run polling cycle completed without network access."
    cfg.require_live_ready()
    if fetch_update is None:
        raise TelegramLiveError("Polling requires an injected update fetcher in Phase 4")
    update = fetch_update()
    if update is None:
        return "No Telegram command received."
    return handle_founder_telegram_text(store, update.text, chat_id=update.chat_id, config=cfg)


def _approval_line(item: dict[str, object]) -> str:
    effect = "external" if item["external_effect"] else "internal"
    return (
        f"{item['approval_id']}: {item['risk_level']} {effect} action "
        f"{item['requested_action']} for task {item['task_id']}."
    )


def _help_text() -> str:
    return "\n".join(
        [
            "The Synthetic Firm founder human-task inbox:",
            "/human_tasks",
            "/human_task HUMAN_TASK_ID",
            "/done HUMAN_TASK_ID",
            "/blocked HUMAN_TASK_ID",
            "/note HUMAN_TASK_ID MESSAGE",
            "/urgent MESSAGE",
            "/clarify MESSAGE",
            "/constraint MESSAGE",
            "",
            "Read-only status commands:",
            "/status",
            "/report",
            "/budget",
            "/tasks",
            "/help",
        ]
    )
