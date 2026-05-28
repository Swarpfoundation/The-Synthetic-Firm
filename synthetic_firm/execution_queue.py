"""Persistent execution queue for approved TSF actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from synthetic_firm.approval_signing import action_hash, verify_signed_decision
from synthetic_firm.report import DailyReportInput, generate_daily_report
from synthetic_firm.store import Store
from synthetic_firm.time_utils import utc_iso


QUEUE_STATES = frozenset(
    {
        "queued",
        "approval_required",
        "approved_waiting_adapter",
        "blocked_missing_adapter",
        "executed",
        "failed",
        "cancelled",
        "expired",
    }
)
SAFE_EXECUTABLE_ACTIONS = frozenset(
    {
        "create_task",
        "create_message",
        "generate_daily_report",
        "budget_check",
        "status_check",
        "create_approval_request",
    }
)


class ExecutionQueueError(ValueError):
    """Raised when queued execution fails closed."""


@dataclass(frozen=True)
class ExecutionQueueItem:
    queue_id: str
    task_id: str
    agent_id: str
    action: str
    payload: dict[str, Any]
    external_effect: bool
    approval_id: str | None
    approval_decision_id: str | None
    action_hash: str
    status: str
    result_summary: str | None
    created_at: str
    updated_at: str


def enqueue_action(
    store: Store,
    *,
    task_id: str,
    agent_id: str,
    action: str,
    payload: dict[str, Any] | None = None,
    external_effect: bool = False,
    approval_id: str | None = None,
) -> ExecutionQueueItem:
    store.get_task(task_id)
    status = "approval_required" if external_effect and not approval_id else "queued"
    queue_id = f"queue_{uuid4().hex[:12]}"
    now = utc_iso()
    store.connection.execute(
        """
        INSERT INTO execution_queue VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            queue_id,
            task_id,
            agent_id,
            action,
            json.dumps(payload or {}, sort_keys=True),
            int(external_effect),
            approval_id,
            None,
            action_hash(action),
            status,
            None,
            now,
            now,
        ),
    )
    store.connection.commit()
    _audit_transition(store, queue_id, status, f"Queued action {action}.", external_effect)
    return get_queue_item(store, queue_id)


def get_queue_item(store: Store, queue_id: str) -> ExecutionQueueItem:
    row = store.connection.execute("SELECT * FROM execution_queue WHERE queue_id = ?", (queue_id,)).fetchone()
    if not row:
        raise ExecutionQueueError(f"Queue item not found: {queue_id}")
    return _item_from_row(row)


def list_queue(store: Store) -> list[ExecutionQueueItem]:
    rows = store.connection.execute("SELECT * FROM execution_queue ORDER BY created_at, queue_id").fetchall()
    return [_item_from_row(row) for row in rows]


def process_queue_item(store: Store, queue_id: str, *, dry_run: bool = True) -> ExecutionQueueItem:
    item = get_queue_item(store, queue_id)
    if item.status in {"executed", "failed", "cancelled", "expired", "blocked_missing_adapter"}:
        return item
    if item.external_effect:
        decision = store.latest_approval_decision(item.approval_id or "")
        if decision is None:
            return _transition(store, item, "approval_required", "External-effect action still needs approval.")
        if _decision_consumed(store, decision.decision_id, excluding_queue_id=item.queue_id):
            raise ExecutionQueueError("Signed approval decision was already consumed")
        if not verify_signed_decision(decision, requested_action=item.action):
            return _transition(store, item, "failed", "Signed approval did not verify for queued action.")
        return _transition(
            store,
            item,
            "blocked_missing_adapter",
            "External-effect adapter is not implemented in Phase 4.",
            approval_decision_id=decision.decision_id,
        )
    if item.action not in SAFE_EXECUTABLE_ACTIONS:
        return _transition(store, item, "failed", f"Unsafe queued action blocked: {item.action}")
    if dry_run:
        return _transition(store, item, "queued", f"Dry-run would execute safe action {item.action}.")
    summary = _execute_safe_action(store, item)
    return _transition(store, item, "executed", summary)


def process_execution_queue(store: Store, *, dry_run: bool = True) -> list[ExecutionQueueItem]:
    return [process_queue_item(store, item.queue_id, dry_run=dry_run) for item in list_queue(store)]


def _execute_safe_action(store: Store, item: ExecutionQueueItem) -> str:
    payload = item.payload
    if item.action == "create_task":
        task = store.create_task(
            title=str(payload.get("title") or "Queued task"),
            objective=str(payload.get("objective") or "Created from execution queue."),
            created_by_agent_id=item.agent_id,
            plain_english_summary=str(payload.get("summary") or "Queued task was created."),
        )
        return f"Created task {task.task_id}."
    if item.action == "create_message":
        message = store.create_message(
            sender_agent_id=item.agent_id,
            channel=str(payload.get("channel") or "company"),
            task_id=item.task_id,
            content=str(payload.get("content") or "Queued internal message."),
        )
        return f"Created message {message.message_id}."
    if item.action == "generate_daily_report":
        report = generate_daily_report(DailyReportInput())
        report_id = store.save_daily_report(report_date=utc_iso()[:10], content=report, telegram_summary=_summary(report))
        return f"Generated daily report {report_id}."
    if item.action == "budget_check":
        return "Budget check queued action completed."
    if item.action == "status_check":
        return f"Runtime status is {store.runtime_status()}."
    if item.action == "create_approval_request":
        approval = store.create_approval(
            task_id=item.task_id,
            agent_id=item.agent_id,
            requested_action=str(payload.get("requested_action") or "internal_note"),
            risk_level=str(payload.get("risk_level") or "medium"),
            external_effect=bool(payload.get("external_effect", False)),
            plain_english_request=str(payload.get("request") or "Queued approval request."),
        )
        return f"Created approval {approval.approval_id}."
    raise ExecutionQueueError(f"Unsupported safe action: {item.action}")


def _transition(
    store: Store,
    item: ExecutionQueueItem,
    status: str,
    summary: str,
    *,
    approval_decision_id: str | None = None,
) -> ExecutionQueueItem:
    if status not in QUEUE_STATES:
        raise ExecutionQueueError(f"Invalid queue status: {status}")
    store.connection.execute(
        """
        UPDATE execution_queue
        SET status = ?, result_summary = ?, approval_decision_id = COALESCE(?, approval_decision_id), updated_at = ?
        WHERE queue_id = ?
        """,
        (status, summary, approval_decision_id, utc_iso(), item.queue_id),
    )
    store.connection.commit()
    _audit_transition(store, item.queue_id, status, summary, item.external_effect)
    return get_queue_item(store, item.queue_id)


def _decision_consumed(store: Store, decision_id: str, *, excluding_queue_id: str) -> bool:
    row = store.connection.execute(
        """
        SELECT queue_id FROM execution_queue
        WHERE approval_decision_id = ? AND queue_id != ?
        LIMIT 1
        """,
        (decision_id, excluding_queue_id),
    ).fetchone()
    return row is not None


def _audit_transition(store: Store, queue_id: str, status: str, summary: str, external_effect: bool) -> None:
    store.append_audit(
        actor_type="orchestrator",
        actor_id="execution_queue",
        action="execution_queue_transition",
        target_type="execution_queue",
        target_id=queue_id,
        risk_level="high" if external_effect else "low",
        external_effect=external_effect,
        summary=summary,
        metadata={"status": status},
    )


def _item_from_row(row) -> ExecutionQueueItem:
    return ExecutionQueueItem(
        queue_id=row["queue_id"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        action=row["action"],
        payload=json.loads(row["payload_json"]),
        external_effect=bool(row["external_effect"]),
        approval_id=row["approval_id"],
        approval_decision_id=row["approval_decision_id"],
        action_hash=row["action_hash"],
        status=row["status"],
        result_summary=row["result_summary"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def queue_item_to_dict(item: ExecutionQueueItem) -> dict[str, Any]:
    return item.__dict__.copy()


def _summary(report: str) -> str:
    lines = [line.strip() for line in report.splitlines() if line.strip()]
    return "\n".join(lines[:10])
