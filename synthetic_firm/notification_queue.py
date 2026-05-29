"""Safe outgoing Telegram notification queue."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from synthetic_firm.provider_auth_redaction import redact_auth_text
from synthetic_firm.store import Store
from synthetic_firm.telegram_live import TelegramConfig, TelegramLiveError
from synthetic_firm.time_utils import utc_iso

NOTIFICATION_TYPES = frozenset(
    {
        "daily_report",
        "approval_request",
        "approval_decision",
        "runtime_status",
        "budget_warning",
        "risk_warning",
        "task_summary",
        "human_task",
        "provider_blocker",
    }
)


class NotificationQueueError(ValueError):
    """Raised when notification handling fails closed."""


@dataclass(frozen=True)
class Notification:
    notification_id: str
    notification_type: str
    chat_id: str | None
    body: str
    status: str
    dry_run: bool
    created_at: str
    sent_at: str | None


def enqueue_notification(
    store: Store,
    *,
    notification_type: str,
    body: str,
    chat_id: str | None = None,
    dry_run: bool = True,
) -> Notification:
    if notification_type not in NOTIFICATION_TYPES:
        raise NotificationQueueError(f"Unsupported notification type: {notification_type}")
    safe_body = _plain(body)
    notification_id = f"note_{uuid4().hex[:12]}"
    store.connection.execute(
        "INSERT INTO notification_queue VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (notification_id, notification_type, chat_id, safe_body, "queued", int(dry_run), utc_iso(), None),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="notification_queue",
        action="notification_queue",
        target_type="notification",
        target_id=notification_id,
        summary=f"Queued {notification_type} notification.",
    )
    return get_notification(store, notification_id)


def get_notification(store: Store, notification_id: str) -> Notification:
    row = store.connection.execute(
        "SELECT * FROM notification_queue WHERE notification_id = ?", (notification_id,)
    ).fetchone()
    if not row:
        raise NotificationQueueError(f"Notification not found: {notification_id}")
    return _notification_from_row(row)


def list_notifications(store: Store) -> list[Notification]:
    rows = store.connection.execute("SELECT * FROM notification_queue ORDER BY created_at").fetchall()
    return [_notification_from_row(row) for row in rows]


def send_notifications(
    store: Store,
    *,
    dry_run: bool = True,
    config: TelegramConfig | None = None,
    sender: Callable[[str, str], None] | None = None,
    include_dry_run_notifications: bool = False,
) -> list[Notification]:
    sent: list[Notification] = []
    for notification in list_notifications(store):
        if notification.status != "queued":
            continue
        if dry_run or (notification.dry_run and not include_dry_run_notifications):
            _mark(store, notification, "dry_run_sent")
            sent.append(get_notification(store, notification.notification_id))
            continue
        if config is None or sender is None:
            raise NotificationQueueError("Live notification send requires Telegram config and sender")
        if not config.enabled:
            raise TelegramLiveError("Telegram live send is disabled")
        chat_id = notification.chat_id or config.default_chat_id()
        sender(chat_id, notification.body)
        _mark(store, notification, "sent")
        sent.append(get_notification(store, notification.notification_id))
    return sent


def notification_to_dict(notification: Notification) -> dict[str, object]:
    return notification.__dict__.copy()


def _mark(store: Store, notification: Notification, status: str) -> None:
    store.connection.execute(
        "UPDATE notification_queue SET status = ?, sent_at = ? WHERE notification_id = ?",
        (status, utc_iso(), notification.notification_id),
    )
    store.connection.commit()
    store.append_audit(
        actor_type="orchestrator",
        actor_id="notification_queue",
        action="notification_send_attempt",
        target_type="notification",
        target_id=notification.notification_id,
        summary=f"Notification marked {status}.",
    )


def _notification_from_row(row) -> Notification:
    return Notification(
        notification_id=row["notification_id"],
        notification_type=row["notification_type"],
        chat_id=row["chat_id"],
        body=row["body"],
        status=row["status"],
        dry_run=bool(row["dry_run"]),
        created_at=row["created_at"],
        sent_at=row["sent_at"],
    )


def _plain(body: str) -> str:
    text = redact_auth_text(str(body or "").replace("\n\n\n", "\n\n")).strip()
    return text[:3500]
